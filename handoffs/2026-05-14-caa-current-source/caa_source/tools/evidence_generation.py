from __future__ import annotations

from typing import Any

from tools.aida_proxy_client import AiDaProxyClient, AiDaProxyError
from tools.semantic_router import RouteDecision


def build_grounded_prompt(query: str, evidence_packet: dict[str, Any], route: RouteDecision) -> str:
    evidence_rows = evidence_packet.get("evidence", [])
    if not evidence_rows:
        raise ValueError("Cannot build grounded prompt without evidence.")

    evidence_text = "\n".join(
        f"[{row['chunk_id']}] {row['excerpt']}"
        for row in evidence_rows
    )
    return (
        "You are Contract Analyzer. Answer only from the cited evidence below.\n"
        "If the evidence does not support an answer, say so and do not infer.\n"
        f"Mode: {route.mode}\n"
        f"Intent: {route.intent}\n"
        f"Question: {query}\n\n"
        "Evidence:\n"
        f"{evidence_text}\n\n"
        "Return a concise answer and cite chunk IDs in brackets."
    )


def generate_grounded_answer(
    *,
    query: str,
    evidence_packet: dict[str, Any],
    route: RouteDecision,
    client: AiDaProxyClient,
) -> dict[str, Any]:
    evidence_rows = evidence_packet.get("evidence", [])
    citations = [row["chunk_id"] for row in evidence_rows if isinstance(row, dict) and row.get("chunk_id")]
    base = {
        "schema_version": "contract_analyzer_grounded_answer_v1",
        "query": query,
        "mode": route.mode,
        "intent": route.intent,
        "citations": citations,
        "confidence": "low",
        "grounding_state": "not_grounded",
        "answer_text": "",
        "warnings": [],
        "abstention_reason": None,
        "error": None,
    }

    if route.blocked:
        return {
            **base,
            "warnings": ["route_blocked"],
            "abstention_reason": route.blocker or route.clarification or "Route is blocked.",
        }

    if evidence_packet.get("no_evidence") or not evidence_rows:
        return {
            **base,
            "warnings": ["no_supporting_evidence"],
            "abstention_reason": "No retrieved evidence supports this answer.",
        }

    try:
        prompt = build_grounded_prompt(query, evidence_packet, route)
        response = client.generate(prompt)
    except AiDaProxyError as exc:
        return {
            **base,
            "grounding_state": "proxy_error",
            "warnings": ["proxy_failure"],
            "abstention_reason": "LLM proxy failed before a grounded answer could be produced.",
            "error": exc.to_dict(),
        }

    answer_text = response["text"]
    missing_citations = [chunk_id for chunk_id in citations if chunk_id not in answer_text]
    warnings = []
    if missing_citations:
        warnings.append("model_answer_missing_some_chunk_ids")

    return {
        **base,
        "answer_text": answer_text,
        "confidence": "medium",
        "grounding_state": "grounded",
        "warnings": warnings,
        "llm": {"model_path": response["model_path"]},
    }
