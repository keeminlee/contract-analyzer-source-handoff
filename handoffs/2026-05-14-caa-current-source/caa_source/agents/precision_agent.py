from __future__ import annotations

import re
from typing import Any


def _has_valid_citation(finding: dict[str, Any]) -> bool:
    citation = finding.get("citation")
    if not citation:
        return False
    return all(
        key in citation and citation[key] is not None
        for key in ("node_id", "span_start", "span_end")
    )


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", (text or "").lower()))


def _best_chunk_for_finding(finding: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not chunks:
        return None

    citation = finding.get("citation") or {}
    node_id = citation.get("node_id")
    if node_id:
        for chunk in chunks:
            if node_id in chunk.get("node_ids", []):
                return chunk

    message_tokens = _tokenize(str(finding.get("message", "")))
    best_chunk = chunks[0]
    best_overlap = -1
    for chunk in chunks:
        overlap = len(message_tokens & _tokenize(str(chunk.get("excerpt", ""))))
        if overlap > best_overlap:
            best_overlap = overlap
            best_chunk = chunk
    return best_chunk


def run_precision(findings: list[dict[str, Any]], retrieval_chunks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cited_findings = [f for f in findings if _has_valid_citation(f)]
    chunks = retrieval_chunks or []

    summary_lines = []
    for finding in cited_findings:
        chunk = _best_chunk_for_finding(finding, chunks)
        if not chunk:
            continue

        excerpt = str(chunk.get("excerpt", "")).strip().replace("\n", " ")
        excerpt = excerpt[:220] + ("..." if len(excerpt) > 220 else "")
        summary_lines.append(
            (
                f"{finding['message']} Quote: \"{excerpt}\" "
                f"Citation: {chunk.get('chunk_id')} [{chunk.get('span_start')}–{chunk.get('span_end')}]"
            )
        )

    if not summary_lines:
        if chunks:
            summary_lines = [
                (
                    f"Retrieved context citation: {chunk.get('chunk_id')} "
                    f"[{chunk.get('span_start')}–{chunk.get('span_end')}] "
                    f"Quote: \"{str(chunk.get('excerpt', '')).strip().replace(chr(10), ' ')[:220]}\""
                )
                for chunk in chunks[:3]
            ]
        else:
            summary_lines = [
                "No retrieved chunk-backed findings available; no assertion generated."
            ]

    return {
        "mode": "precision",
        "findings": cited_findings,
        "retrieved_chunks": chunks,
        "answer": "\n".join(summary_lines),
        "citation_enforced": True,
    }
