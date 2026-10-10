"""Evidence grounding and provenance validator for structured clinical extraction.

Validates extracted clinical entities (observations, medications, diagnoses)
against original source document text to verify page citations, prevent
hallucinations, maintain document boundaries, detect contradictions and negations,
and preserve bilingual (English and Hindi) evidence without unintended translation
or mutation.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Literal
import unicodedata
from uuid import UUID

from app.ai.schemas.nlp import (
    DiagnosisExtract,
    DocumentEntitiesExtract,
    KnownBiomarkerExtract,
    KnownMedicationExtract,
    UnknownBiomarkerExtract,
    UnknownMedicationExtract,
)

logger = logging.getLogger(__name__)

# Section header pattern for page-aware consolidated text
_PAGE_HEADER_RE = re.compile(
    r"---\s*(?:Document\s+([0-9a-fA-F-]+)\s*\|\s*)?Page\s+(\d+)\s*---",
    re.IGNORECASE,
)

# Document break separator in cumulative text
_DOC_BREAK_RE = re.compile(r"\n*---\s*Document\s*---\s*", re.IGNORECASE)

# Discontinuation / cessation keywords (English and Hindi)
_DISCONTINUED_PATTERNS = re.compile(
    r"\b(?:discontinued|stopped|ceased|terminated|withheld|held|no\s+longer\s+taking|off|बंद|रोक\s*दिया|समाप्त)\b",
    re.IGNORECASE,
)

# Historical / prior keywords (English and Hindi)
_HISTORICAL_PATTERNS = re.compile(
    r"\b(?:past|prior|previous|historical|history\s+of|formerly|used\s+to\s+take|पूर्व|पुराना|इतिहास)\b",
    re.IGNORECASE,
)

# Active medication keywords (English and Hindi)
_ACTIVE_PATTERNS = re.compile(
    r"\b(?:currently\s+taking|currently\s+active|active|ongoing|continues\s+on|continue|चालू|वर्तमान\s*में|जारी)\b",
    re.IGNORECASE,
)

# Negation diagnosis keywords (English and Hindi)
_NEGATION_DIAGNOSIS_PATTERNS = re.compile(
    r"\b(?:no\s+evidence\s+of|negative\s+for|rules?\s*out|ruled\s*out|no\s+signs?\s+of|denies|unlikely|without|absent|नहीं\s+है|नकार|बिना\s+किसी)\b",
    re.IGNORECASE,
)

# Provisional / differential diagnosis keywords (English and Hindi)
_PROVISIONAL_DIAGNOSIS_PATTERNS = re.compile(
    r"\b(?:differential|provisional|suspected|possible|probable|rule\s*out|to\s*be\s*confirmed|संभावित|संदेह)\b",
    re.IGNORECASE,
)

# Confirmed diagnosis keywords (English and Hindi)
_CONFIRMED_DIAGNOSIS_PATTERNS = re.compile(
    r"\b(?:confirmed|established|definite|verified|proven|पुष्ट|सत्यापित)\b",
    re.IGNORECASE,
)


def normalize_evidence_text(text: str | None) -> str:
    """Normalize text conservatively for substring comparison across whitespace and Unicode.

    Uses Unicode NFKC decomposition to reconcile composite Devanagari characters,
    nuktas, punctuation, and typographical quotes, while collapsing consecutive
    whitespace characters. Preserves the underlying semantic characters.
    """
    if not text:
        return ""
    # NFKC normalizes compatibility characters, fullwidth forms, composite glyphs
    nfkc = unicodedata.normalize("NFKC", str(text))
    # Collapse multiple whitespace characters (spaces, tabs, newlines) into a single space
    collapsed = re.sub(r"\s+", " ", nfkc).strip()
    return collapsed


# Devanagari numerals translation table to ASCII digits
_DEVANAGARI_DIGITS_TRANS = str.maketrans("०१२३४५६७८९", "0123456789")

# Reference range pattern inside parentheses or brackets or after keywords
_REFERENCE_SPAN_RE = re.compile(
    r"(?:\((?:reference|ref\.?|ref\.?\s*range|reference\s*interval|normal|सामान्य|ref)\s*[:=]?\s*([^)]+)\)"
    r"|\[(?:reference|ref\.?|ref\.?\s*range|normal|सामान्य|ref)?\s*[:=]?\s*([0-9.,\s<>-]+)\]"
    r"|\b(?:reference|ref\.?|ref\.?\s*range|reference\s*interval|normal|सामान्य)\s*[:=]\s*([0-9.,\s<>-]+))",
    re.IGNORECASE,
)

# Numeric token pattern: standalone numbers not embedded in alphanumeric identifiers
_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])([0-9]+(?:[.,][0-9]+)*)(?![A-Za-z0-9_])"
)

# Delimiters separating distinct test items or lines in cumulative snippets
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:\r?\n+|;\s*|\|\s*|,\s*(?=[A-Za-z\u0900-\u097F]))"
)

# Dictionary of clinical unit synonyms and bilingual equivalents
_UNIT_SYNONYMS: dict[str, list[str]] = {
    "mg/dl": ["mg/dl", "mg/d\\ell", "मि.ग्रा./डी.एल.", "मिग्रा/डीएल"],
    "g/dl": ["g/dl", "gm/dl", "g/d\\ell", "ग्रा./डी.एल."],
    "mmol/l": ["mmol/l", "mmol/\\ell"],
    "k/ul": ["k/ul", "k/µl", "10^3/ul", "x10^3/ul", "10^3/µl", "x10^3/µl", "thousand/ul", "k/u\\ell"],
    "/ul": ["/ul", "/µl", "/mm3", "/cu.mm", "/cumm"],
    "u/l": ["u/l", "iu/l", "u/\\ell", "iu/\\ell"],
    "iu/l": ["iu/l", "u/l", "iu/\\ell"],
    "uiu/ml": ["uiu/ml", "µiu/ml", "u\\iu/ml", "microiu/ml"],
    "ug/dl": ["ug/dl", "µg/dl", "mcg/dl"],
    "ng/ml": ["ng/ml", "ng/\\ell"],
    "pg/ml": ["pg/ml"],
    "fl": ["fl", "f\\ell"],
    "%": ["%", "percent", "प्रतिशत", "फीसदी"],
    "mg": ["mg", "मि.ग्रा.", "मिलीग्राम", "मिग्रा"],
    "g": ["g", "gm", "ग्रा.", "ग्राम"],
    "ml": ["ml", "m\\ell", "मि.ली.", "मिलीलीटर"],
    "mcg": ["mcg", "µg", "माइक्रोग्राम"],
    "tablets": ["tablet", "tablets", "tab", "tabs", "गोली", "गोलियां"],
    "capsules": ["capsule", "capsules", "cap", "caps"],
}


def _normalize_numerals(text: str | None) -> str:
    """Normalize text with NFKC and map Devanagari numerals to ASCII digits."""
    if not text:
        return ""
    nfkc = unicodedata.normalize("NFKC", str(text))
    return nfkc.translate(_DEVANAGARI_DIGITS_TRANS)


def _parse_candidate_numbers(token: str) -> list[float]:
    """Parse candidate float values from a numeric string token."""
    token = token.strip()
    if not token:
        return []
    candidates: list[float] = []

    # 1. Pure integer or standard dot decimal: e.g. "110", "14.5", "0.75"
    if re.match(r"^\d+(?:\.\d+)?$", token):
        try:
            candidates.append(float(token))
        except ValueError:
            pass

    # 2. Decimal comma: e.g. "5,8" or "14,5" or "0,75"
    elif re.match(r"^\d+,\d+$", token):
        try:
            candidates.append(float(token.replace(",", ".")))
        except ValueError:
            pass
        # If exactly 3 digits after comma (e.g. "1,500"), could also be thousands
        if re.match(r"^\d{1,3},\d{3}$", token):
            try:
                candidates.append(float(token.replace(",", "")))
            except ValueError:
                pass

    # 3. Standard thousands with commas: e.g. "150,000" or "1,250,000"
    elif re.match(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$", token):
        try:
            candidates.append(float(token.replace(",", "")))
        except ValueError:
            pass

    # 4. European thousands with dots: e.g. "150.000" or "1.500,50"
    elif re.match(r"^\d{1,3}(?:\.\d{3})+,\d+$", token):
        try:
            candidates.append(float(token.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    elif re.match(r"^\d{1,3}(?:\.\d{3})+$", token):
        try:
            candidates.append(float(token.replace(".", "")))
        except ValueError:
            pass
    else:
        try:
            candidates.append(float(token))
        except ValueError:
            pass

    return candidates


def _numbers_match(val1: float, val2: float, tol: float = 1e-4) -> bool:
    """Compare two float values with tolerance."""
    return abs(val1 - val2) <= max(tol, 1e-4 * max(abs(val1), abs(val2)))


def _is_unit_grounded(unit: str | None, text: str) -> bool:
    """Verify if a clinical unit symbol is grounded in the text with boundary checks."""
    if not unit or not str(unit).strip():
        return True
    norm_text = unicodedata.normalize("NFKC", str(text))
    cleaned_unit = str(unit).strip()
    key = cleaned_unit.lower().replace(" ", "")

    variants = [cleaned_unit]
    if key in _UNIT_SYNONYMS:
        variants.extend(_UNIT_SYNONYMS[key])

    for var in variants:
        escaped = re.escape(var)
        # Lookaround boundaries:
        # Before: forbid letters, Devanagari, or '/'
        # After: forbid letters, digits, Devanagari, or '/'
        pat = rf"(?<![A-Za-z/\u0900-\u097F]){escaped}(?![A-Za-z0-9/\u0900-\u097F])"
        if re.search(pat, norm_text, re.IGNORECASE):
            return True
    return False


@dataclass
class PageSegment:
    """A sliced page from a document with provenance metadata."""

    document_id: str | None
    page_number: int
    raw_text: str
    norm_text: str = field(init=False)

    def __post_init__(self):
        self.norm_text = normalize_evidence_text(self.raw_text)


@dataclass
class ValidationOutcome:
    """Result of validating an extracted entity against source text."""

    is_valid: bool
    reason: Literal[
        "verified",
        "provenance_resolved",
        "missing_evidence",
        "hallucinated_evidence",
        "page_mismatch",
        "cross_document_misattribution",
        "ambiguous_multi_page",
        "ambiguous_multi_document",
        "nonexistent_document_id",
        "numeric_value_mismatch",
        "unit_mismatch",
        "value_reference_confusion",
        "multi_test_misassociation",
        "medication_strength_mismatch",
        "validation_error",
    ]
    verified_document_id: str | None = None
    verified_page_number: int | None = None
    matching_pages_count: int = 0
    message: str = ""


@dataclass
class ValidationReport:
    """Summary of batch evidence validation across all entities in an extraction."""

    total_entities: int = 0
    valid_count: int = 0
    flagged_count: int = 0
    outcomes: list[tuple[str, ValidationOutcome]] = field(default_factory=list)


class EvidenceValidator:
    """Validates extracted clinical entities against source document pages."""

    def __init__(self, conservative_mode: bool = True):
        self.conservative_mode = conservative_mode

    def parse_page_segments(
        self,
        cumulative_text: str,
        docs: list[Any] | None = None,
    ) -> list[PageSegment]:
        """Parse source documents or cumulative text into indexed PageSegments."""
        segments: list[PageSegment] = []

        # 1. Prefer structured DocumentModel list if available
        if docs:
            for doc in docs:
                doc_id_str = str(getattr(doc, "id", None)) if getattr(doc, "id", None) else None
                text = str(getattr(doc, "extracted_text", "") or "")
                matches = list(_PAGE_HEADER_RE.finditer(text))
                if matches:
                    for i, m in enumerate(matches):
                        header_doc_id = m.group(1) or doc_id_str
                        page_num = int(m.group(2))
                        start = m.end()
                        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                        content = text[start:end].strip()
                        segments.append(
                            PageSegment(document_id=header_doc_id, page_number=page_num, raw_text=content)
                        )
                elif text.strip():
                    segments.append(
                        PageSegment(document_id=doc_id_str, page_number=1, raw_text=text.strip())
                    )

            if segments:
                return segments

        # 2. Parse from cumulative text with section markers
        matches = list(_PAGE_HEADER_RE.finditer(cumulative_text))
        if matches:
            for i, m in enumerate(matches):
                doc_id = m.group(1)
                page_num = int(m.group(2))
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(cumulative_text)
                content = cumulative_text[start:end]
                # Strip trailing document break marker if present
                content = _DOC_BREAK_RE.sub("", content).strip()
                segments.append(PageSegment(document_id=doc_id, page_number=page_num, raw_text=content))
            return segments

        # 3. Fallback for un-chunked plain text: treat as single page
        clean_text = cumulative_text.strip()
        if clean_text:
            segments.append(PageSegment(document_id=None, page_number=1, raw_text=clean_text))

        return segments

    def find_evidence_occurrences(
        self,
        evidence_text: str,
        segments: list[PageSegment],
    ) -> list[PageSegment]:
        """Find all PageSegments where evidence_text appears (case-insensitive & NFKC-normalized)."""
        norm_ev = normalize_evidence_text(evidence_text).lower()
        if not norm_ev:
            return []
        matches: list[PageSegment] = []
        for seg in segments:
            if norm_ev in seg.norm_text.lower():
                matches.append(seg)
        return matches

    def validate_numeric_and_unit_grounding(
        self, entity: Any, target_snippet: str
    ) -> tuple[bool, str, str]:
        """Verify extracted numeric values, units, and ranges against the evidence snippet.

        Returns (is_valid, reason, message).
        """
        norm_snippet = _normalize_numerals(target_snippet)
        if not norm_snippet.strip():
            return (False, "missing_evidence", "Evidence snippet is empty")

        has_value = getattr(entity, "value", None) is not None
        unit_symbol = getattr(entity, "unit_symbol", None)
        strength = getattr(entity, "strength", None)
        entity_name = str(getattr(entity, "name", getattr(entity, "raw_name", "")) or "")
        entity_slug = str(getattr(entity, "matched_slug", "") or "")

        # Multi-test clause splitting
        clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(norm_snippet) if c.strip()]
        target_clause = norm_snippet
        other_clauses: list[str] = []

        if len(clauses) > 1 and entity_name:
            matching_clauses = [
                c
                for c in clauses
                if entity_name.lower() in c.lower()
                or (entity_slug and entity_slug.replace("-", " ").lower() in c.lower())
            ]
            if matching_clauses:
                target_clause = " ; ".join(matching_clauses)
                other_clauses = [c for c in clauses if c not in matching_clauses]

        # 2. Check Unit Grounding if unit_symbol is present
        if unit_symbol:
            unit_check_text = target_clause if target_clause != norm_snippet else norm_snippet
            if not _is_unit_grounded(unit_symbol, unit_check_text):
                return (
                    False,
                    "unit_mismatch",
                    f"Extracted unit '{unit_symbol}' is not supported by evidence snippet",
                )

        # 3. Check Medication Strength Grounding if strength is present
        if strength and str(strength).strip():
            strength_ascii = _normalize_numerals(str(strength))
            strength_numbers: list[float] = []
            for sm in _NUMERIC_TOKEN_RE.finditer(strength_ascii):
                strength_numbers.extend(_parse_candidate_numbers(sm.group(1)))

            if strength_numbers:
                snippet_numbers: list[float] = []
                for snm in _NUMERIC_TOKEN_RE.finditer(target_clause):
                    snippet_numbers.extend(_parse_candidate_numbers(snm.group(1)))

                strength_matched = any(
                    any(_numbers_match(sn, doc_n) for doc_n in snippet_numbers)
                    for sn in strength_numbers
                )
                if not strength_matched:
                    return (
                        False,
                        "medication_strength_mismatch",
                        f"Medication strength '{strength}' contradicts source evidence snippet",
                    )

        # 4. Check Numeric Value Grounding if value is present
        if has_value:
            entity_val = float(getattr(entity, "value"))

            # Reference range partitioning
            ref_match = _REFERENCE_SPAN_RE.search(target_clause)
            if ref_match:
                ref_span = ref_match.group(0)
                result_clause = (
                    target_clause[: ref_match.start()]
                    + " "
                    + target_clause[ref_match.end() :]
                )
                reference_clause = ref_span
            else:
                result_clause = target_clause
                reference_clause = ""

            # Mask entity name/slug from result_clause to avoid acronym collisions (e.g. HbA1c, Vitamin D3, CA 19-9)
            masked_result = result_clause
            if entity_name:
                masked_result = re.sub(re.escape(entity_name), " ", masked_result, flags=re.IGNORECASE)
            if entity_slug:
                masked_result = re.sub(re.escape(entity_slug), " ", masked_result, flags=re.IGNORECASE)
                masked_result = re.sub(re.escape(entity_slug.replace("-", " ")), " ", masked_result, flags=re.IGNORECASE)

            # Extract numbers from result portion
            result_numbers: list[float] = []
            for m in _NUMERIC_TOKEN_RE.finditer(masked_result):
                result_numbers.extend(_parse_candidate_numbers(m.group(1)))

            val_in_result = any(_numbers_match(entity_val, rn) for rn in result_numbers)

            # Extract numbers from reference clause if present
            ref_numbers: list[float] = []
            if reference_clause:
                for m in _NUMERIC_TOKEN_RE.finditer(reference_clause):
                    ref_numbers.extend(_parse_candidate_numbers(m.group(1)))

            # Verify reference range bounds if explicitly present on entity
            ref_min = getattr(entity, "reference_range_min", None)
            ref_max = getattr(entity, "reference_range_max", None)
            if ref_numbers and (ref_min is not None or ref_max is not None):
                if ref_min is not None and not any(_numbers_match(ref_min, rn) for rn in ref_numbers):
                    return (
                        False,
                        "numeric_value_mismatch",
                        f"Extracted reference_range_min {ref_min} contradicts source snippet range",
                    )
                if ref_max is not None and not any(_numbers_match(ref_max, rn) for rn in ref_numbers):
                    return (
                        False,
                        "numeric_value_mismatch",
                        f"Extracted reference_range_max {ref_max} contradicts source snippet range",
                    )

            if val_in_result:
                return (True, "verified", "Numeric value grounded in observation result")

            # Value was not in result portion. Check if it's solely in reference range
            val_in_ref = any(_numbers_match(entity_val, rn) for rn in ref_numbers)
            if val_in_ref:
                return (
                    False,
                    "value_reference_confusion",
                    f"Extracted value {entity_val} matches reference range bound rather than observation result",
                )

            # Check if it belongs to other clauses of a multi-test snippet
            other_numbers: list[float] = []
            for oc in other_clauses:
                for m in _NUMERIC_TOKEN_RE.finditer(oc):
                    other_numbers.extend(_parse_candidate_numbers(m.group(1)))

            val_in_other = any(_numbers_match(entity_val, on) for on in other_numbers)
            if val_in_other:
                return (
                    False,
                    "multi_test_misassociation",
                    f"Extracted value {entity_val} for '{entity_name}' belongs to a different test in snippet",
                )

            # Value not found anywhere
            return (
                False,
                "numeric_value_mismatch",
                f"Extracted value {entity_val} contradicts source evidence snippet",
            )

        return (True, "verified", "Entity attributes grounded")

    def validate_single_entity(
        self,
        entity: Any,
        segments: list[PageSegment],
    ) -> ValidationOutcome:
        """Validate an entity's evidence_text and page/doc provenance against PageSegments."""
        try:
            ev_text = getattr(entity, "evidence_text", None)
            claimed_page = getattr(entity, "page_number", None)
            claimed_doc = (
                str(getattr(entity, "document_id", None)) if getattr(entity, "document_id", None) else None
            )

            # 1. Missing evidence snippet
            if not ev_text or not str(ev_text).strip():
                self._apply_flag(entity, confidence_cap=0.4)
                return ValidationOutcome(
                    is_valid=False,
                    reason="missing_evidence",
                    message="Entity lacks supporting evidence_text quote from source document",
                )

            occurrences = self.find_evidence_occurrences(str(ev_text), segments)

            # 2. Hallucinated evidence: not found in any page/doc
            if not occurrences:
                self._apply_flag(entity, confidence_cap=0.2)
                return ValidationOutcome(
                    is_valid=False,
                    reason="hallucinated_evidence",
                    message="Extracted evidence_text not found in source document text",
                )

            # 3. Nonexistent document ID check
            known_doc_ids = set(s.document_id.lower() for s in segments if s.document_id)
            if claimed_doc and known_doc_ids and claimed_doc.lower() not in known_doc_ids:
                self._apply_flag(entity, confidence_cap=0.2)
                return ValidationOutcome(
                    is_valid=False,
                    reason="nonexistent_document_id",
                    message=f"Claimed document ID {claimed_doc} does not exist in ingested documents",
                )

            # 4. Multi-document ambiguity check
            distinct_docs = set(s.document_id.lower() for s in occurrences if s.document_id)
            if len(distinct_docs) > 1:
                # Identical evidence appears in multiple distinct documents!
                self._apply_flag(entity, confidence_cap=0.4)
                return ValidationOutcome(
                    is_valid=False,
                    reason="ambiguous_multi_document",
                    matching_pages_count=len(occurrences),
                    message=f"Identical evidence text appears across multiple distinct documents ({len(distinct_docs)} docs)",
                )

            # 5. Cross-document boundary check
            eligible_occurrences = occurrences
            if claimed_doc:
                doc_matches = [
                    s for s in occurrences if s.document_id and s.document_id.lower() == claimed_doc.lower()
                ]
                if not doc_matches and any(s.document_id for s in occurrences):
                    # Evidence exists, but ONLY in a different document
                    self._apply_flag(entity, confidence_cap=0.3)
                    return ValidationOutcome(
                        is_valid=False,
                        reason="cross_document_misattribution",
                        matching_pages_count=len(occurrences),
                        message=f"Evidence belongs to a different document than claimed ({claimed_doc})",
                    )
                if doc_matches:
                    eligible_occurrences = doc_matches

            # 6. Page citation check
            if claimed_page is not None:
                exact_page_matches = [s for s in eligible_occurrences if s.page_number == claimed_page]
                if exact_page_matches:
                    # Evidence is found on the cited page
                    # If identical text appears on multiple pages within the same document, citation is ambiguous
                    if len(eligible_occurrences) > 1:
                        self._apply_flag(entity, confidence_cap=0.5)
                        return ValidationOutcome(
                            is_valid=False,
                            reason="ambiguous_multi_page",
                            verified_document_id=exact_page_matches[0].document_id,
                            verified_page_number=claimed_page,
                            matching_pages_count=len(eligible_occurrences),
                            message="Identical evidence text appears across multiple pages; attribution is ambiguous",
                        )
                    # Unambiguous match on correct page!
                    # Validate numeric and unit grounding against the evidence snippet
                    num_valid, num_reason, num_msg = self.validate_numeric_and_unit_grounding(
                        entity, str(ev_text)
                    )
                    if not num_valid:
                        self._apply_flag(entity, confidence_cap=0.3)
                        return ValidationOutcome(
                            is_valid=False,
                            reason=num_reason,
                            verified_document_id=exact_page_matches[0].document_id,
                            verified_page_number=claimed_page,
                            matching_pages_count=1,
                            message=num_msg,
                        )

                    self._apply_verified(entity, exact_page_matches[0])
                    return ValidationOutcome(
                        is_valid=True,
                        reason="verified",
                        verified_document_id=exact_page_matches[0].document_id,
                        verified_page_number=claimed_page,
                        matching_pages_count=1,
                        message="Evidence verified on exact cited page",
                    )
                else:
                    # Claimed page does NOT contain the evidence
                    self._apply_flag(entity, confidence_cap=0.4)
                    return ValidationOutcome(
                        is_valid=False,
                        reason="page_mismatch",
                        matching_pages_count=len(eligible_occurrences),
                        message=f"Evidence text is not present on cited page {claimed_page}",
                    )

            # 7. Missing page number (page_number is None)
            if len(eligible_occurrences) == 1:
                # Unambiguous single page: resolve provenance safely
                seg = eligible_occurrences[0]
                num_valid, num_reason, num_msg = self.validate_numeric_and_unit_grounding(
                    entity, str(ev_text)
                )
                if not num_valid:
                    self._apply_flag(entity, confidence_cap=0.3)
                    return ValidationOutcome(
                        is_valid=False,
                        reason=num_reason,
                        verified_document_id=seg.document_id,
                        verified_page_number=seg.page_number,
                        matching_pages_count=1,
                        message=num_msg,
                    )

                entity.page_number = seg.page_number
                if not getattr(entity, "document_id", None) and seg.document_id:
                    entity.document_id = seg.document_id
                self._apply_verified(entity, seg)
                return ValidationOutcome(
                    is_valid=True,
                    reason="provenance_resolved",
                    verified_document_id=seg.document_id,
                    verified_page_number=seg.page_number,
                    matching_pages_count=1,
                    message="Provenance resolved to unambiguous source page",
                )
            else:
                # Ambiguous: appears across multiple pages
                self._apply_flag(entity, confidence_cap=0.4)
                return ValidationOutcome(
                    is_valid=False,
                    reason="ambiguous_multi_page",
                    matching_pages_count=len(eligible_occurrences),
                    message="Evidence text appears on multiple pages; page cannot be attributed unambiguously",
                )
        except Exception as err:
            logger.error("Validation error for entity: %s", err)
            self._apply_flag(entity, confidence_cap=0.2)
            return ValidationOutcome(
                is_valid=False,
                reason="validation_error",
                message=f"Validation failed safely with error: {err}",
            )

    def enforce_clinical_caution(self, entity: Any) -> None:
        """Enforce clinical caution rules: reset ungrounded or contradictory statuses."""
        ev_text = str(getattr(entity, "evidence_text", "") or "")

        # 1. Medication status validation
        if hasattr(entity, "status") and entity.status is not None:
            is_discontinued = bool(_DISCONTINUED_PATTERNS.search(ev_text))
            is_historical = bool(_HISTORICAL_PATTERNS.search(ev_text))
            is_active = bool(_ACTIVE_PATTERNS.search(ev_text))

            # Contradictory statements in evidence (e.g. both active and discontinued)
            if is_discontinued and is_active:
                entity.status = None
                self._apply_flag(entity, confidence_cap=0.4)
            elif str(entity.status).upper() == "ACTIVE":
                if is_discontinued:
                    # Contradiction: evidence says discontinued, but entity claims active!
                    entity.status = None
                    self._apply_flag(entity, confidence_cap=0.3)
                elif is_historical and not is_active:
                    # Contradiction: historical medication cannot be marked active!
                    entity.status = None
                    self._apply_flag(entity, confidence_cap=0.3)
                elif not is_active:
                    # Ungrounded: evidence lacks explicit active phrasing
                    entity.status = None
            elif str(entity.status).upper() in ["DISCONTINUED", "STOPPED"]:
                if is_active and not is_discontinued:
                    # Contradiction: evidence says active, entity claims discontinued
                    entity.status = None
                    self._apply_flag(entity, confidence_cap=0.4)
                elif not is_discontinued:
                    # Ungrounded
                    entity.status = None

        # 2. Diagnosis verification status validation
        if hasattr(entity, "verification_status") and entity.verification_status is not None:
            is_negated = bool(_NEGATION_DIAGNOSIS_PATTERNS.search(ev_text))
            is_provisional = bool(_PROVISIONAL_DIAGNOSIS_PATTERNS.search(ev_text))
            is_confirmed = bool(_CONFIRMED_DIAGNOSIS_PATTERNS.search(ev_text))

            # Contradictory statements (e.g. both confirmed and negated, or confirmed and provisional)
            if (is_confirmed and is_negated) or (is_confirmed and is_provisional):
                entity.verification_status = None
                self._apply_flag(entity, confidence_cap=0.3)
            elif is_negated:
                # Contradiction: condition was negated ("no evidence of..."), cannot be confirmed!
                entity.verification_status = None
                if hasattr(entity, "clinical_status") and entity.clinical_status is not None:
                    entity.clinical_status = None
                self._apply_flag(entity, confidence_cap=0.2)
            elif str(entity.verification_status).lower() == "confirmed":
                if is_provisional and not is_confirmed:
                    # Contradiction: differential / provisional cannot be marked confirmed!
                    entity.verification_status = None
                    self._apply_flag(entity, confidence_cap=0.3)
                elif not is_confirmed:
                    # Ungrounded confirmation
                    entity.verification_status = None
            elif str(entity.verification_status).lower() in ["provisional", "differential"]:
                if not is_provisional:
                    entity.verification_status = None

        # 3. Diagnosis clinical_status validation
        if hasattr(entity, "clinical_status") and entity.clinical_status is not None:
            is_negated = bool(_NEGATION_DIAGNOSIS_PATTERNS.search(ev_text))
            is_resolved = bool(re.search(r"\b(?:resolved|cured|remission|ठीक|शांत)\b", ev_text, re.I))
            is_active_condition = bool(re.search(r"\b(?:active|currently|acute|chronic|सक्रिय)\b", ev_text, re.I))

            if is_negated or is_resolved:
                if str(entity.clinical_status).lower() == "active":
                    entity.clinical_status = None
                    self._apply_flag(entity, confidence_cap=0.3)
            elif not is_active_condition and str(entity.clinical_status).lower() == "active":
                entity.clinical_status = None

        # 4. Calibration: review_status must never be set to 'accepted' or 'reviewed' by extraction engine
        if getattr(entity, "review_status", None) in ["accepted", "reviewed"]:
            entity.review_status = "needs_review"
        elif getattr(entity, "review_status", None) is None:
            entity.review_status = "needs_review"

    def _apply_flag(self, entity: Any, confidence_cap: float = 0.4) -> None:
        """Flag entity for review and calibrate confidence downward."""
        if hasattr(entity, "review_status"):
            entity.review_status = "needs_review"
        if hasattr(entity, "confidence"):
            current_conf = getattr(entity, "confidence", None)
            if current_conf is not None:
                entity.confidence = min(current_conf, confidence_cap)
            else:
                entity.confidence = confidence_cap

    def _apply_verified(self, entity: Any, segment: PageSegment) -> None:
        """Apply verified state: retain conservative review_status while establishing provenance."""
        # Core principle: extraction engine never marks human-reviewed; keep conservative review_status
        if hasattr(entity, "review_status"):
            entity.review_status = "needs_review"
        if hasattr(entity, "confidence") and getattr(entity, "confidence", None) is None:
            entity.confidence = 0.9
        if segment.document_id and hasattr(entity, "document_id") and not getattr(entity, "document_id", None):
            entity.document_id = segment.document_id

    def validate_document_entities(
        self,
        parsed_data: DocumentEntitiesExtract,
        cumulative_text: str,
        docs: list[Any] | None = None,
    ) -> ValidationReport:
        """Validate all entities in DocumentEntitiesExtract against source document segments."""
        segments = self.parse_page_segments(cumulative_text, docs)
        report = ValidationReport()

        entity_lists = [
            ("known_biomarker", parsed_data.known_biomarkers),
            ("unknown_biomarker", parsed_data.unknown_biomarkers),
            ("known_medication", parsed_data.known_medications),
            ("unknown_medication", parsed_data.unknown_medications),
            ("structured_diagnosis", parsed_data.structured_diagnoses),
        ]

        for category, entities in entity_lists:
            for entity in entities:
                report.total_entities += 1
                # 1. Enforce clinical caution on attributes
                self.enforce_clinical_caution(entity)
                # 2. Validate evidence and provenance
                outcome = self.validate_single_entity(entity, segments)
                report.outcomes.append(
                    (
                        f"{category}:{getattr(entity, 'name', getattr(entity, 'raw_name', 'item'))}",
                        outcome,
                    )
                )
                if outcome.is_valid:
                    report.valid_count += 1
                else:
                    report.flagged_count += 1

        # Synchronize flat diagnoses string list if structured_diagnoses are present
        if parsed_data.structured_diagnoses and not parsed_data.diagnoses:
            parsed_data.diagnoses = [d.name for d in parsed_data.structured_diagnoses]

        return report
