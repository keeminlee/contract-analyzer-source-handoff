from __future__ import annotations

import re
from typing import Any


INSIGHT_PACKET_SCHEMA_VERSION = "contract_analyzer_insight_answer_packet_v1"
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")


def _allowed_citation_ids(analysis: dict[str, Any]) -> set[str]:
    return {
        str(citation.get("citation_id"))
        for citation in analysis.get("citations", [])
        if isinstance(citation, dict) and citation.get("citation_id")
    }


def _extract_bracket_ids(text: str) -> set[str]:
    return set(re.findall(r"\[([A-Za-z0-9_:\-]+)\]", text or ""))


def _answer_is_fully_cited(answer_text: str, allowed_ids: set[str]) -> bool:
    if not answer_text.strip() or not allowed_ids:
        return False
    cited_ids = _extract_bracket_ids(answer_text)
    if not cited_ids or not cited_ids <= allowed_ids:
        return False
    claim_sentences = [sentence.strip() for sentence in SENTENCE_PATTERN.split(answer_text) if sentence.strip()]
    return all(_extract_bracket_ids(sentence) & allowed_ids for sentence in claim_sentences)


def _default_answer(analysis: dict[str, Any]) -> str:
    findings = analysis.get("findings", [])
    sentences: list[str] = []
    for finding in findings[:5]:
        citation_ids = [str(item) for item in finding.get("citation_ids", []) if item]
        if not citation_ids:
            continue
        summary = str(finding.get("summary", "Cited finding.")).rstrip(".!?")
        sentences.append(f"{summary} [{citation_ids[0]}].")
    return " ".join(sentences)


def build_insight_answer_packet(
    *,
    query: str,
    analysis: dict[str, Any],
    generated_answer: str | None = None,
) -> dict[str, Any]:
    base = {
        "schema_version": INSIGHT_PACKET_SCHEMA_VERSION,
        "query": query,
        "findings": analysis.get("findings", []),
        "citations": analysis.get("citations", []),
        "chunks": analysis.get("chunks", []),
        "source_documents": analysis.get("source_documents", []),
        "confidence": "low",
        "grounding": "not_grounded",
        "answer_text": "",
        "warnings": [],
        "abstention_reason": None,
        "trace_metadata": {
            "analysis_schema_version": analysis.get("schema_version"),
            "analysis_state": analysis.get("analysis_state"),
            "engine": analysis.get("trace", {}).get("engine"),
            "answer_contract": "every non-empty claim sentence must contain an allowed citation id",
        },
    }

    if analysis.get("analysis_state") != "complete":
        return {
            **base,
            "warnings": ["analysis_not_complete"],
            "abstention_reason": analysis.get("baseline_state", {}).get("message", "Analysis did not complete."),
        }

    answer_text = generated_answer if generated_answer is not None else _default_answer(analysis)
    allowed_ids = _allowed_citation_ids(analysis)
    if not _answer_is_fully_cited(answer_text, allowed_ids):
        return {
            **base,
            "warnings": ["uncited_claim_rejected"],
            "abstention_reason": "Answer contained uncited or unsupported claim text.",
        }

    return {
        **base,
        "answer_text": answer_text,
        "confidence": analysis.get("confidence", "medium"),
        "grounding": "grounded",
    }
