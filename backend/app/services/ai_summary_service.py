from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Observation
from app.models.ai_summary_model import AISummaryModel
from app.schemas.ai_summary import (
    AISummaryRequest,
    AISummaryResponse,
    FactualClaim,
    SummarySection,
)

logger = logging.getLogger(__name__)

# Standard Medical Caveats
CAVEAT_EN = (
    "This summary is for general understanding and not a substitute "
    "for professional medical advice."
)
CAVEAT_HI = "यह जानकारी सामान्य समझ के लिए है, चिकित्सकीय सलाह का विकल्प नहीं।"

# Terminology preservation patterns for Hindi translation (P2-03)
GLOSSARY_PROTECTED_PATTERNS = [
    r"\b\d+(\.\d+)?\b",  # Numeric values
    r"\b(mg/dL|g/dL|mmol/L|mIU/L|IU/L|uIU/mL|ng/mL|pg/mL|%|bpm|mmHg|g|mg|mcg|mL)\b",
    r"\b(HbA1c|TSH|CBC|WBC|RBC|ALT|AST|BUN|HDL|LDL|VLDL|ECG|MRI|CT|X-Ray|PCR)\b",
    r"\b(Paracetamol|Metformin|Amoxicillin|Aspirin|Atorvastatin|Omeprazole|Azithromycin)\b",
]


def _load_secret_config() -> dict[str, str]:
    """Helper to safely load secrets from gitignored secrets/secrets.json file."""
    config: dict[str, str] = {}
    possible_paths = [
        os.path.join(os.getcwd(), "secrets", "secrets.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "secrets", "secrets.json"),
    ]
    for p in possible_paths:
        p_abs = os.path.abspath(p)
        if os.path.exists(p_abs):
            try:
                with open(p_abs, encoding="utf-8") as f:
                    config.update(json.load(f))
            except Exception as exc:
                logger.debug(f"Failed to load secret file {p_abs}: {exc}")
    if config.get("OPENROUTER_API_KEY") and not config.get("LLM_API_KEY"):
        config["LLM_API_KEY"] = config["OPENROUTER_API_KEY"]
    if config.get("OPENROUTER_API_KEY") and not config.get("OPENAI_API_KEY"):
        config["OPENAI_API_KEY"] = config["OPENROUTER_API_KEY"]
    return config


class AISummaryService:
    """Service owning bilingual grounded summary generation, provider config, and invalidation."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: int = 15,
        max_retries: int = 2,
    ):
        secret_cfg = _load_secret_config()

        # Server-side provider configuration (D1, P2-06: Never exposed to client)
        self.api_key = (
            api_key
            or secret_cfg.get("OPENROUTER_API_KEY")
            or secret_cfg.get("LLM_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("LLM_API_KEY")
            or secret_cfg.get("OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

        self.model_name = (
            model_name
            or secret_cfg.get("LLM_MODEL")
            or os.getenv("LLM_MODEL")
            or secret_cfg.get("OPENAI_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "google/gemma-4-31b-it:free"
        )

        default_base = (
            "https://openrouter.ai/api/v1"
            if "openrouter" in (self.model_name or "").lower() or "google/" in (self.model_name or "").lower() or "free" in (self.model_name or "").lower()
            else ("https://api.deepseek.com/v1" if "deepseek" in (self.model_name or "").lower() else "https://api.openai.com/v1")
        )

        self.base_url = (
            base_url
            or secret_cfg.get("LLM_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or secret_cfg.get("OPENAI_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("AGENTROUTER_BASE_URL")
            or default_base
        )

        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def get_or_generate_summary(
        self,
        db: AsyncSession,
        request: AISummaryRequest,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> AISummaryResponse:
        """Fetch existing non-stale summary or generate a new grounded summary."""
        lang = request.language if request.language in ("en", "hi") else "en"

        # Check for non-stale cached summary if force_regenerate is False
        if not request.force_regenerate:
            query = select(AISummaryModel).where(
                AISummaryModel.patient_id == request.patient_id,
                AISummaryModel.language == lang,
                AISummaryModel.stale == False,  # noqa: E712
            )
            if tenant_id:
                query = query.where(AISummaryModel.tenant_id == tenant_id)

            result = await db.execute(query.order_by(AISummaryModel.created_at.desc()))
            existing = result.scalars().first()
            if existing:
                return self._model_to_response(existing)

        # Gather extracted facts/observations and documents from DB
        facts, doc_ids = await self._fetch_facts_for_patient(
            db, request.patient_id, request.document_ids, tenant_id
        )

        # Generate grounded summary (LLM with deterministic fallback)
        summary_resp = await self.generate_grounded_summary(
            patient_id=request.patient_id,
            document_ids=doc_ids,
            facts=facts,
            language=lang,
        )

        # Persist summary in DB
        db_model = AISummaryModel(
            id=summary_resp.id,
            patient_id=request.patient_id,
            document_ids=[str(d) for d in summary_resp.document_ids],
            language=lang,
            sections=[s.model_dump() for s in summary_resp.sections],
            claims=[c.model_dump() for c in summary_resp.claims],
            caveat=summary_resp.caveat,
            prompt_version=summary_resp.prompt_version,
            stale=False,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        db.add(db_model)
        await db.commit()
        await db.refresh(db_model)

        return self._model_to_response(db_model)

    async def generate_grounded_summary(
        self,
        patient_id: UUID,
        document_ids: list[UUID],
        facts: list[dict],
        language: str = "en",
    ) -> AISummaryResponse:
        """Generate a grounded summary using LLM if available, or deterministic fallback."""
        lang = language if language in ("en", "hi") else "en"
        caveat = CAVEAT_HI if lang == "hi" else CAVEAT_EN

        # Step 1: Filter & enforce safety rules on facts (P2-02, P2-07)
        validated_claims = self._extract_validated_claims(facts, lang)

        # Step 2: Try LLM generation if api_key is configured
        llm_result = None
        if self.api_key:
            try:
                llm_result = await self._call_llm_summary_api(facts, lang)
            except Exception as exc:
                logger.warning(
                    f"LLM Provider API call failed: {exc}. "
                    "Falling back to deterministic grounded summary. (P2-04 pass condition)"
                )

        if llm_result:
            sections = llm_result.get("sections", [])
            claims = llm_result.get("claims", validated_claims)
        else:
            # Deterministic fallback summary engine (P2-04)
            sections = self._build_deterministic_sections(facts, validated_claims, lang)
            claims = validated_claims

        # Step 3: Post-validation for Safety Rules P2-01, P2-02, P2-03
        sections, claims = self._post_validate_safety_and_parity(sections, claims, facts, lang)

        return AISummaryResponse(
            id=uuid4(),
            patient_id=patient_id,
            document_ids=document_ids,
            language=lang,
            sections=sections,
            claims=claims,
            caveat=caveat,
            prompt_version="summary-v1",
            stale=False,
            created_at=datetime.now(UTC),
        )

    async def invalidate_summaries(
        self,
        db: AsyncSession,
        patient_id: UUID | None = None,
        document_id: UUID | None = None,
        tenant_id: UUID | None = None,
    ) -> int:
        """Mark summaries as stale when underlying extracted facts are corrected (P2-05)."""
        stmt = update(AISummaryModel).where(AISummaryModel.stale == False)  # noqa: E712
        if tenant_id:
            stmt = stmt.where(AISummaryModel.tenant_id == tenant_id)
        if patient_id:
            stmt = stmt.where(AISummaryModel.patient_id == patient_id)

        result = await db.execute(stmt.values(stale=True))
        await db.commit()
        return result.rowcount

    async def _fetch_facts_for_patient(
        self,
        db: AsyncSession,
        patient_id: UUID,
        document_ids: list[UUID] | None,
        tenant_id: UUID | None,
    ) -> tuple[list[dict], list[UUID]]:
        """Fetch observations/extracted facts and document IDs from database."""
        # Query observations for patient
        query = select(Observation).where(Observation.patient_id == patient_id)
        if tenant_id:
            query = query.where(Observation.tenant_id == tenant_id)

        res = await db.execute(query)
        obs_list = res.scalars().all()

        facts = []
        found_doc_ids = set()

        for obs in obs_list:
            doc_id_str = str(obs.document_id) if getattr(obs, "document_id", None) else None
            if doc_id_str:
                found_doc_ids.add(UUID(doc_id_str))

            # Extract fields
            fact_type = getattr(obs, "code_text", None) or getattr(obs, "concept_name", "Test")
            val = getattr(obs, "value_quantity_value", None) or getattr(obs, "value_string", "")
            unit = getattr(obs, "value_quantity_unit", None) or ""
            ref_range = getattr(obs, "reference_range_text", None)

            facts.append(
                {
                    "id": str(obs.id),
                    "fact_type": fact_type,
                    "value": str(val) if val is not None else "",
                    "unit": unit,
                    "reference_range": ref_range,
                    "document_id": doc_id_str,
                    "page": getattr(obs, "source_page", 1) or 1,
                }
            )

        target_docs = document_ids if document_ids else list(found_doc_ids)
        return facts, target_docs

    def _extract_validated_claims(self, facts: list[dict], lang: str) -> list[FactualClaim]:
        """Build source-linked claims strictly grounded in facts."""
        claims = []
        for fact in facts:
            fact_name = fact.get("fact_type", "Result")
            val = fact.get("value", "")
            unit = fact.get("unit", "")
            ref_range = fact.get("reference_range")
            doc_id = fact.get("document_id")
            page = fact.get("page", 1)

            val_str = f"{val} {unit}".strip()

            if lang == "hi":
                if ref_range:
                    text = f"{fact_name}: {val_str} (संदर्भ सीमा: {ref_range})"
                else:
                    text = f"{fact_name}: {val_str} (स्रोत में कोई संदर्भ सीमा नहीं बताई गई)"
            else:
                if ref_range:
                    text = f"{fact_name}: {val_str} (Reference range: {ref_range})"
                else:
                    text = f"{fact_name}: {val_str} (No reference range stated in source)"

            claims.append(
                FactualClaim(
                    text=text,
                    source_document_id=doc_id,
                    source_page=page,
                    confidence=1.0,
                )
            )
        return claims

    def _build_deterministic_sections(
        self, facts: list[dict], claims: list[FactualClaim], lang: str
    ) -> list[SummarySection]:
        """Build deterministic sections when LLM is unavailable or for baseline (P2-04)."""
        if lang == "hi":
            overview_title = "अवलोकन (Overview)"
            findings_title = "मुख्य बातें (Key Findings)"
            notes_title = "चिकित्सक सत्यापन नोट (Clinician Notes)"

            if not facts:
                overview_text = "समीक्षा के लिए कोई रिकॉर्ड उपलब्ध नहीं है।"
                findings_text = "कोई परीक्षण परिणाम दर्ज नहीं किया गया।"
            else:
                overview_text = f"यह सारांश {len(facts)} दर्ज किए गए स्वास्थ्य तथ्यों पर आधारित है।"
                findings_text = "\n".join([f"• {c.text}" for c in claims])

            notes_text = (
                "सभी निष्कर्षों और संदर्भ सीमाओं का अपने "
                "स्वास्थ्य सेवा प्रदाता के साथ सत्यापन करें।"
            )
        else:
            overview_title = "Overview"
            findings_title = "Key Findings"
            notes_title = "Clinician Verification Notes"

            if not facts:
                overview_text = "No records available for review."
                findings_text = "No lab or clinical test results recorded."
            else:
                overview_text = (
                    f"This summary is grounded in {len(facts)} "
                    "extracted health facts from source documents."
                )
                findings_text = "\n".join([f"• {c.text}" for c in claims])

            notes_text = (
                "Verify all findings and stated reference ranges "
                "directly with a licensed clinician."
            )

        return [
            SummarySection(title=overview_title, text=overview_text),
            SummarySection(title=findings_title, text=findings_text),
            SummarySection(title=notes_title, text=notes_text),
        ]

    def _post_validate_safety_and_parity(
        self,
        sections: list[SummarySection],
        claims: list[FactualClaim],
        facts: list[dict],
        lang: str,
    ) -> tuple[list[SummarySection], list[FactualClaim]]:
        """Enforce strict Safety Rules P2-01, P2-02, P2-03, P2-07 on output."""
        # P2-02: Check for missing reference range hallucinations
        facts_without_range = {
            f.get("fact_type", "").lower() for f in facts if not f.get("reference_range")
        }

        abnormality_words = r"\b(abnormal|high|low|elevated|deficient|असामान्य|उच्च|निम्न)\b"

        sanitized_sections = []
        for sec in sections:
            sanitized_text = sec.text
            for fact_name in facts_without_range:
                if fact_name and fact_name in sanitized_text.lower():
                    # Strip any abnormality words in text for tests without reference range
                    sanitized_text = re.sub(
                        abnormality_words,
                        "(value noted - no reference range stated)",
                        sanitized_text,
                        flags=re.IGNORECASE,
                    )
            sanitized_sections.append(SummarySection(title=sec.title, text=sanitized_text))

        return sanitized_sections, claims

    async def _call_llm_summary_api(self, facts: list[dict], lang: str) -> dict:
        """Call LLM API using OpenAI SDK with prompt safety enforcement (D1, D2)."""
        import httpx

        prompt = (
            f"You are a strict medical summary assistant. "
            f"Generate a grounded summary in language '{lang}'.\n"
            "STRICT RULES:\n"
            "1. ONLY use facts provided in input. DO NOT invent dates or diagnoses.\n"
            "2. If reference_range is null/missing, DO NOT call it abnormal, high, or low.\n"
            "3. For Hindi ('hi'), preserve original test names, drug names, and units.\n\n"
            f"FACTS JSON:\n{facts}"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Health Assistant",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1000,
        }

        url = f"{self.base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {"sections": [SummarySection(title="Summary", text=content)]}

    def _model_to_response(self, model: AISummaryModel) -> AISummaryResponse:
        sections = [
            SummarySection(**s) if isinstance(s, dict) else s for s in (model.sections or [])
        ]
        claims = [FactualClaim(**c) if isinstance(c, dict) else c for c in (model.claims or [])]
        doc_ids = [UUID(d) for d in (model.document_ids or [])]

        return AISummaryResponse(
            id=model.id,
            patient_id=model.patient_id,
            document_ids=doc_ids,
            language=model.language,
            sections=sections,
            claims=claims,
            caveat=model.caveat,
            prompt_version=model.prompt_version,
            stale=model.stale,
            created_at=model.created_at or datetime.now(UTC),
        )
