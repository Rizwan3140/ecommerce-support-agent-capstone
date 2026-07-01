"""End-to-end orchestration: triage → retrieve → write → comply → validate → JSON."""

import json
from typing import Any

from agents.compliance_agent import run_compliance
from agents.policy_retriever_agent import run_policy_retriever
from agents.resolution_writer_agent import run_resolution_writer
from agents.triage_agent import run_triage
from tools.mock_apis import merge_order_context, run_mock_tools, summarize_tool_results
from utils.context_sufficiency import (
    is_context_sufficient_for_decision,
    refine_clarifying_questions,
)
from utils.schemas import ResolutionOutput
from utils.validation import fallback_escalation_payload, validate_resolution_payload


def resolve_support_ticket(
    ticket: str,
    order_context: dict[str, Any],
    top_k: int | None = None,
) -> dict[str, Any]:
    """
    Run the multi-agent pipeline and return a JSON-serializable dict
    matching ResolutionOutput (strict schema for API/Streamlit).
    """
    try:
        tool_results = run_mock_tools(ticket, order_context)
        enriched_context = merge_order_context(order_context, tool_results)
        tool_context = summarize_tool_results(tool_results)

        triage = run_triage(ticket, enriched_context)

        refined_qs = refine_clarifying_questions(
            ticket,
            enriched_context,
            triage.clarifying_questions,
            triage.classification,
        )
        sufficient = is_context_sufficient_for_decision(
            ticket,
            enriched_context,
            triage.classification,
        )
        if sufficient:
            refined_qs = []

        if _tool_requires_order_id(tool_results):
            refined_qs = ["Please share your order ID so I can check the latest status."]

        retrieval = run_policy_retriever(
            ticket=ticket,
            classification=triage.classification,
            top_k=top_k,
        )

        writer_out = run_resolution_writer(
            ticket=ticket,
            order_context=enriched_context,
            classification=triage.classification,
            triage_confidence=triage.confidence,
            clarifying_questions_from_triage=refined_qs,
            chunks=retrieval.chunks,
            context_sufficient=sufficient,
            tool_context=tool_context,
        )

        compliance = run_compliance(
            ticket=ticket,
            order_context=enriched_context,
            chunks=retrieval.chunks,
            draft=writer_out,
        )

        final_decision = compliance.decision
        final_rationale = compliance.rationale
        final_citations = compliance.citations
        final_customer = compliance.customer_response
        final_internal = compliance.internal_notes

        out = ResolutionOutput(
            classification=triage.classification,
            confidence=round(float(triage.confidence), 2),
            clarifying_questions=refined_qs[:3],
            decision=final_decision,  # type: ignore[arg-type]
            rationale=final_rationale,
            citations=final_citations,
            customer_response=final_customer,
            internal_notes=final_internal,
            tool_results=tool_results,
        )
        payload = json.loads(out.model_dump_json())

        ok, errs = validate_resolution_payload(payload)
        if not ok:
            payload = fallback_escalation_payload(
                classification=triage.classification,
                confidence=triage.confidence,
                clarifying_questions=refined_qs,
                reason="; ".join(errs)[:500],
            )
            payload["tool_results"] = tool_results
        return payload

    except Exception as e:
        return fallback_escalation_payload(
            classification="other",
            confidence=0.0,
            clarifying_questions=[],
            reason=f"{type(e).__name__}: {e!s}"[:500],
        )


def resolve_support_ticket_json_string(
    ticket: str,
    order_context: dict[str, Any],
    top_k: int | None = None,
) -> str:
    """Same as resolve_support_ticket but returns compact JSON string."""
    return json.dumps(
        resolve_support_ticket(ticket, order_context, top_k=top_k),
        ensure_ascii=False,
    )


def _tool_requires_order_id(tool_results: list[dict[str, Any]]) -> bool:
    for result in tool_results:
        if (
            result.get("tool") == "get_order_status"
            and result.get("ok") is False
            and "Order ID is required" in str(result.get("message", ""))
        ):
            return True
    return False
