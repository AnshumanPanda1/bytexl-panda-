"""Shared chat infrastructure (tool assembly, history, SSE mapping).

The reasoning loop itself was replaced by the LangGraph engine
(:mod:`app.ai.graphs.chat_agent`) in Phases 3.2-3.6 and deleted in Phase 8;
what remains here is the shared, engine-agnostic surface:

The loop is an async generator yielding typed ``(kind, data)`` event tuples,
parameterised by ``streaming`` (``astream`` vs ``ainvoke``). It owns the
provider-quirk content dedup, tool execution, HITL-proposal detection, and the
proactive + final saves — so all three callers share identical semantics.

  * Streaming callers (chat + resume) pipe the loop through
    :func:`stream_loop_as_sse` to emit the SSE sentinel vocabulary the frontend
    consumes.
  * The non-streaming caller (``_general_chat``) collects ``("content", …)``
    events into the response dict.

Public surface:
  * :func:`build_chat_tools`     — built-in + integration tool assembly.
  * :func:`reconstruct_history`  — rebuild the in-memory message list.
  * :func:`stream_loop_as_sse`   — event -> SSE-sentinel mapper.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.hitl import (
    _append_assistant_turn_to_history,
)
from app.ai.assistance.attachments import build_multimodal_content, has_images
from app.ai.tools import get_tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool assembly
# ---------------------------------------------------------------------------


def prune_tools_for_query(
    tools: list[Any],
    user_input: str | None = None,
) -> list[Any]:
    """Prune tools down to an optimal, context-aware subset.
    Prevents token bloat (especially with rate-limited or bounded-window LLM endpoints).
    """
    if not tools:
        return []

    text = (user_input or "").lower()

    # Core baseline clinical retrieval tools
    core_names = {
        "get_patient_summary",
        "get_patient_alerts",
        "get_recent_biomarkers",
        "get_biomarker_history",
        "search_available_biomarkers",
        "get_current_medications",
        "get_patient_medication_history",
        "search_medications",
        "get_current_allergies",
        "search_allergens",
        "get_recent_examinations",
        "get_examination_details",
        "get_system_time",
    }

    selected_names = set(core_names)

    # Telemetry
    if any(k in text for k in ["trend", "telemetry", "heart rate", "pulse", "step", "device", "continuous", "monitor"]):
        selected_names.add("get_aggregated_biomarker_trends")

    # Documents
    if any(k in text for k in ["doc", "pdf", "file", "report", "scan", "upload", "attachment", "note"]):
        selected_names.update(["get_patient_documents", "get_document_content"])

    # Clinical Events / Health Journey
    if any(k in text for k in ["event", "journey", "timeline", "surgery", "hospital", "history"]):
        selected_names.update(["get_clinical_events", "get_clinical_event_details"])

    # Catalogs / Relations
    if any(k in text for k in ["relation", "affect", "treat", "contraindicat", "graph", "anatomy"]):
        selected_names.update(["search_catalogs", "explore_catalog_relations"])

    # Proposals / Actions (Write-intent)
    has_write = any(k in text for k in [
        "propose", "prescribe", "record", "add", "create", "new", "log", "draft",
        "order", "dose", "start", "stop", "assign", "schedule", "define"
    ]) or "[hitl" in text or "resume" in text

    if has_write:
        if any(k in text for k in ["med", "drug", "prescribe", "pill", "tablet", "aspirin", "metformin", "dose", "rx"]):
            selected_names.update(["propose_prescribe_medication", "propose_define_medication"])
        elif any(k in text for k in ["biomarker", "lab", "result", "level", "blood", "glucose", "hba1c", "cholesterol", "test", "metric"]):
            selected_names.update(["propose_record_biomarker_result", "propose_define_biomarker"])
        elif any(k in text for k in ["allergy", "allergic", "reaction"]):
            selected_names.update(["propose_record_allergy", "propose_define_allergy"])
        elif any(k in text for k in ["event", "journey", "surgery", "pregnancy"]):
            selected_names.add("propose_create_clinical_event")
        else:
            selected_names.update([
                "propose_prescribe_medication",
                "propose_record_biomarker_result",
                "propose_record_allergy",
            ])

    pruned = [t for t in tools if t.name in selected_names]
    if not pruned:
        pruned = tools[:15]
    return pruned


async def build_chat_tools(
    db: AsyncSession,
    tenant_id: UUID | None,
    patient_id: str | None,
    user_id: UUID | None,
    examination_id: str | None = None,
    label: str = "chat",
    user_input: str | None = None,
) -> list[Any]:
    """Assemble the built-in chatbot tools + any integration tools.

    Returns an empty list when patient/tenant context is missing (the chatbot
    runs tool-less in that case). Integration-tool load failures are logged
    and swallowed — built-ins still work.
    """
    if not (patient_id and tenant_id):
        return []

    exam_id = UUID(examination_id) if examination_id else None
    try:
        tools = get_tools(db, tenant_id, UUID(patient_id), examination_id=exam_id, user_id=user_id)
    except Exception as e:
        logger.warning(f"Failed to load built-in tools for {label}: {e}")
        tools = []
    try:
        from app.ai.tools.aggregator import aggregate as integration_aggregate

        integration_tools = await integration_aggregate(db, user_id, tenant_id, UUID(patient_id))
        tools = tools + integration_tools
    except Exception as e:
        logger.warning(
            f"Failed to load integration tools for {label} (continuing with built-ins): {e}"
        )
    return prune_tools_for_query(tools, user_input=user_input)


# ---------------------------------------------------------------------------
# History reconstruction
# ---------------------------------------------------------------------------


async def reconstruct_history(
    chat_session_service,
    session_id: UUID | None,
    user_id: UUID | None,
    tenant_id: UUID | None,
    system_prompt: str,
    driving_input: str | list[dict[str, Any]],
) -> list[Any]:
    """Build the in-memory LLM message list for a chat turn.

    Layout: ``[SystemMessage(prompt)] + [replayed past turns] + [HumanMessage(driving_input)]``.

    The last persisted message is excluded (it's the just-saved current user
    input / HITL summary, which the caller appends explicitly as the driving
    input). Past assistant turns are replayed via
    :func:`_append_assistant_turn_to_history` so every ``tool_call_id`` is
    followed by a ``ToolMessage`` (OpenAI contract).

    NOTE (behaviour fix in Phase 2): the former ``_general_chat`` reconstructed
    past assistant turns WITHOUT following ToolMessages — a latent OpenAI
    ``400 tool_call_ids did not have response messages`` on non-streaming turns
    that followed a tool-calling turn. Unifying on this helper fixes that.
    """
    current_history: list[Any] = [SystemMessage(content=system_prompt)]
    if session_id:
        try:
            past_messages = await chat_session_service.get_session_messages(
                session_id, user_id, tenant_id
            )
            # Exclude the message we just saved (which is the driving input) to
            # avoid duplication; replay the prior 10 turns.
            for msg in past_messages[:-1][-10:]:
                if msg.role == "user":
                    content_json = msg.content if isinstance(msg.content, dict) else {}
                    if has_images(content_json):
                        current_history.append(
                            HumanMessage(
                                content=build_multimodal_content(
                                    content_json.get("text", ""),
                                    content_json.get("images"),
                                )
                            )
                        )
                    else:
                        current_history.append(HumanMessage(content=content_json.get("text")))
                elif msg.role == "assistant":
                    _append_assistant_turn_to_history(msg, current_history)
        except Exception as exc:
            logger.warning(f"Could not load past chat messages from DB: {exc}")
    current_history.append(HumanMessage(content=driving_input))
    return current_history


# ---------------------------------------------------------------------------
# The reasoning loop (replaces 3 duplicates)
# ---------------------------------------------------------------------------


FLOW_EVENT_PREFIX = "[FLOW_EVENT] "


async def stream_loop_as_sse(
    loop: AsyncIterator[tuple[str, Any]],
    *,
    flow_events: bool = False,
) -> AsyncIterator[str]:
    """Map chat-engine events to the SSE sentinel vocabulary the
    frontend parser consumes (``[TOOL_CALL_*]`` / ``[CITATION]`` /
    ``[HITL_TASK]``). ``("content", delta)`` is yielded verbatim; ``("done",)``
    emits nothing. Used by the streaming chat + resume paths."""
    async for kind, data in loop:
        if kind == "flow_event":
            # Phase 6.2 dual-emit: family events ride as gated additive
            # frames; dropped unless the caller opted in.
            if flow_events:
                yield f"{FLOW_EVENT_PREFIX}{json.dumps(data)}"
            continue
        if kind == "content":
            yield data
        elif kind == "tool_call_start":
            yield f"[TOOL_CALL_START] {data}"
        elif kind == "tool_call_exec":
            yield f"[TOOL_CALL_EXEC] {data}"
        elif kind == "tool_call_result":
            yield f"[TOOL_CALL_RESULT] {json.dumps(data)}"
        elif kind == "citation":
            yield f"[CITATION] {data}"
        elif kind == "hitl_task":
            yield f"[HITL_TASK] {json.dumps(data)}"
        elif kind == "tool_call_finished":
            yield "[TOOL_CALL_FINISHED]"
        # "done" -> no SSE emission
