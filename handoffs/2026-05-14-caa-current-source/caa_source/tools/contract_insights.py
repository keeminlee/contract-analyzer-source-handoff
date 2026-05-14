from __future__ import annotations

import re
from typing import Any

from tools.comparison_policy import default_baseline_policy
from tools.dynamic_chunker import build_chunks
from tools.spine_types import SpineDoc, SpineNode


INSIGHT_ANALYSIS_SCHEMA_VERSION = "contract_analyzer_insight_analysis_v1"
TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
OBLIGATION_TRIGGERS = ("shall", "must", "will", "agrees to", "required to")
RISK_SIGNALS = {
    "default": "event_of_default",
    "termination": "termination",
    "liability": "liability",
    "indemnity": "indemnity",
    "covenant": "covenant",
    "breach": "breach",
    "penalty": "penalty",
}
MATERIAL_TERMS = {"interest", "default", "termination", "liability", "indemnity", "covenant", "fee", "payment"}


def _tokens(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall((text or "").lower()))


def _normalized_text(spine_doc: SpineDoc) -> str:
    return " ".join(" ".join(node.text.lower().split()) for node in spine_doc.nodes if node.text)


def _source_document(spine_doc: SpineDoc, role: str) -> dict[str, Any]:
    source = dict(spine_doc.meta.get("source", {})) if isinstance(spine_doc.meta.get("source"), dict) else {}
    return {
        "role": role,
        "analysis_id": spine_doc.meta.get("analysis_id"),
        "source": source,
    }


def _chunk_lookup(spine_doc: SpineDoc) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for chunk in build_chunks(spine_doc.nodes).chunks:
        chunk_dict = chunk.to_dict()
        for node_id in chunk.node_ids:
            lookup[node_id] = chunk_dict
    return lookup


def _citation_for_node(
    *,
    role: str,
    node: SpineNode,
    spine_doc: SpineDoc,
    chunk_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    chunk = chunk_lookup.get(node.node_id)
    chunk_id = chunk["chunk_id"] if chunk else f"node_{node.node_id}"
    analysis_id = spine_doc.meta.get("analysis_id")
    # Prefer chunk-level page range (covers all member nodes), fall back to node.
    page_start = chunk.get("page_start") if chunk else node.page_start
    page_end = chunk.get("page_end") if chunk else node.page_end
    return {
        "citation_id": f"{role}_{chunk_id}_{node.node_id}",
        "document_role": role,
        "analysis_id": analysis_id,
        "chunk_id": chunk_id,
        "source_node_ids": chunk.get("node_ids", [node.node_id]) if chunk else [node.node_id],
        "span_start": chunk.get("span_start", node.span_start) if chunk else node.span_start,
        "span_end": chunk.get("span_end", node.span_end) if chunk else node.span_end,
        "excerpt": chunk.get("excerpt", node.text) if chunk else node.text,
        "source_document": spine_doc.meta.get("source", {}),
        "page_start": page_start,
        "page_end": page_end,
        "pdf_url": f"/api/v1/analyses/{analysis_id}/pdf" if analysis_id else None,
    }


def _add_citation(citations: dict[str, dict[str, Any]], citation: dict[str, Any]) -> str:
    citation_id = citation["citation_id"]
    citations[citation_id] = citation
    return citation_id


def _best_match(node: SpineNode, candidates: list[SpineNode]) -> tuple[SpineNode | None, float]:
    node_tokens = _tokens(node.text)
    best_node: SpineNode | None = None
    best_score = 0.0
    for candidate in candidates:
        candidate_tokens = _tokens(candidate.text)
        if not node_tokens or not candidate_tokens:
            continue
        overlap = len(node_tokens & candidate_tokens) / max(1, len(node_tokens | candidate_tokens))
        title_bonus = 0.08 if node.title and node.title.lower() == candidate.title.lower() else 0.0
        score = min(1.0, overlap + title_bonus)
        if score > best_score:
            best_node = candidate
            best_score = score
    return best_node, round(best_score, 6)


def _has_material_delta(primary: SpineNode, baseline: SpineNode, similarity: float) -> bool:
    if similarity < 0.7:
        return True
    primary_tokens = _tokens(primary.text)
    baseline_tokens = _tokens(baseline.text)
    if (primary_tokens | baseline_tokens) & MATERIAL_TERMS and primary_tokens != baseline_tokens:
        return True
    return set(NUMBER_PATTERN.findall(primary.text)) != set(NUMBER_PATTERN.findall(baseline.text))


def _comparison_findings(
    *,
    primary_spine: SpineDoc,
    baseline_spine: SpineDoc,
    citations: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if _normalized_text(primary_spine) == _normalized_text(baseline_spine):
        return []

    primary_chunks = _chunk_lookup(primary_spine)
    baseline_chunks = _chunk_lookup(baseline_spine)
    primary_nodes = [node for node in primary_spine.nodes if node.text.strip()]
    baseline_nodes = [node for node in baseline_spine.nodes if node.text.strip()]
    findings: list[dict[str, Any]] = []

    for index, baseline_node in enumerate(baseline_nodes, start=1):
        primary_node, similarity = _best_match(baseline_node, primary_nodes)
        baseline_citation_id = _add_citation(
            citations,
            _citation_for_node(
                role="baseline",
                node=baseline_node,
                spine_doc=baseline_spine,
                chunk_lookup=baseline_chunks,
            ),
        )

        if primary_node is None:
            findings.append(
                {
                    "finding_id": f"comparison_missing_{index}",
                    "finding_type": "comparison_missing_baseline_term",
                    "severity": "high",
                    "summary": "A baseline term has no matching primary contract evidence.",
                    "citation_ids": [baseline_citation_id],
                    "confidence": "medium",
                }
            )
            continue

        if not _has_material_delta(primary_node, baseline_node, similarity):
            continue

        primary_citation_id = _add_citation(
            citations,
            _citation_for_node(
                role="primary",
                node=primary_node,
                spine_doc=primary_spine,
                chunk_lookup=primary_chunks,
            ),
        )
        findings.append(
            {
                "finding_id": f"comparison_deviation_{index}",
                "finding_type": "comparison_deviation",
                "severity": "high" if similarity < 0.55 else "medium",
                "summary": "Primary contract language materially differs from the uploaded baseline.",
                "similarity": similarity,
                "citation_ids": [primary_citation_id, baseline_citation_id],
                "confidence": "medium",
            }
        )

    return findings


def _obligation_findings(
    *,
    primary_spine: SpineDoc,
    citations: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    primary_chunks = _chunk_lookup(primary_spine)
    obligations: list[dict[str, Any]] = []
    for index, node in enumerate(primary_spine.nodes, start=1):
        lower_text = node.text.lower()
        trigger = next((item for item in OBLIGATION_TRIGGERS if item in lower_text), None)
        if trigger is None:
            continue
        citation_id = _add_citation(
            citations,
            _citation_for_node(role="primary", node=node, spine_doc=primary_spine, chunk_lookup=primary_chunks),
        )
        obligations.append(
            {
                "finding_id": f"obligation_{index}",
                "finding_type": "obligation",
                "severity": "info",
                "summary": f"Obligation language detected through trigger '{trigger}'.",
                "trigger": trigger,
                "citation_ids": [citation_id],
                "confidence": "medium",
            }
        )
    return obligations


def _risk_findings(
    *,
    primary_spine: SpineDoc,
    citations: dict[str, dict[str, Any]],
    comparison_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    primary_chunks = _chunk_lookup(primary_spine)
    risks: list[dict[str, Any]] = []
    for finding in comparison_findings:
        if finding.get("severity") in {"high", "medium"}:
            risks.append(
                {
                    "finding_id": f"risk_from_{finding['finding_id']}",
                    "finding_type": "risk_flag",
                    "risk_type": "baseline_deviation",
                    "severity": finding["severity"],
                    "summary": "Comparison deviation may require legal or business review.",
                    "citation_ids": list(finding.get("citation_ids", [])),
                    "confidence": finding.get("confidence", "medium"),
                }
            )

    for index, node in enumerate(primary_spine.nodes, start=1):
        lower_text = node.text.lower()
        for signal, risk_type in RISK_SIGNALS.items():
            if signal not in lower_text:
                continue
            citation_id = _add_citation(
                citations,
                _citation_for_node(role="primary", node=node, spine_doc=primary_spine, chunk_lookup=primary_chunks),
            )
            risks.append(
                {
                    "finding_id": f"risk_{risk_type}_{index}",
                    "finding_type": "risk_flag",
                    "risk_type": risk_type,
                    "severity": "medium",
                    "summary": f"Risk signal '{signal}' appears in primary contract evidence.",
                    "citation_ids": [citation_id],
                    "confidence": "medium",
                }
            )
    return risks


def analyze_contract_insights(
    *,
    primary_spine: SpineDoc,
    baseline_spine: SpineDoc | None,
    query: str = "Compare obligations and risks.",
) -> dict[str, Any]:
    policy = default_baseline_policy()
    if baseline_spine is None:
        citations: dict[str, dict[str, Any]] = {}
        obligations = _obligation_findings(primary_spine=primary_spine, citations=citations)
        risks = _risk_findings(primary_spine=primary_spine, citations=citations, comparison_findings=[])
        findings = obligations + risks
        chunks = [
            {
                "citation_id": citation["citation_id"],
                "document_role": citation["document_role"],
                "chunk_id": citation["chunk_id"],
                "source_node_ids": citation["source_node_ids"],
                "span_start": citation["span_start"],
                "span_end": citation["span_end"],
                "excerpt": citation["excerpt"],
            }
            for citation in citations.values()
        ]
        return {
            "schema_version": INSIGHT_ANALYSIS_SCHEMA_VERSION,
            "analysis_state": "complete",
            "query": query,
            "baseline_state": {"state": "no_baseline_supplied", "baseline_policy": policy.to_dict()},
            "baseline_policy": policy.to_dict(),
            "comparison": {"material_differences": [], "state": "no_baseline_supplied"},
            "obligations": obligations,
            "risks": risks,
            "findings": findings,
            "citations": list(citations.values()),
            "chunks": chunks,
            "source_documents": [_source_document(primary_spine, "primary")],
            "confidence": "medium" if findings else "low",
            "grounding": "grounded" if findings else "not_grounded",
            "trace": {"engine": "contract_insights.analyze_contract_insights", "version": "0.1"},
        }

    citations: dict[str, dict[str, Any]] = {}
    comparison = _comparison_findings(
        primary_spine=primary_spine,
        baseline_spine=baseline_spine,
        citations=citations,
    )
    obligations = _obligation_findings(primary_spine=primary_spine, citations=citations)
    risks = _risk_findings(primary_spine=primary_spine, citations=citations, comparison_findings=comparison)
    findings = comparison + obligations + risks

    chunks = [
        {
            "citation_id": citation["citation_id"],
            "document_role": citation["document_role"],
            "chunk_id": citation["chunk_id"],
            "source_node_ids": citation["source_node_ids"],
            "span_start": citation["span_start"],
            "span_end": citation["span_end"],
            "excerpt": citation["excerpt"],
        }
        for citation in citations.values()
    ]

    return {
        "schema_version": INSIGHT_ANALYSIS_SCHEMA_VERSION,
        "analysis_state": "complete",
        "query": query,
        "baseline_state": {"state": "available", "baseline_policy": policy.to_dict()},
        "baseline_policy": policy.to_dict(),
        "comparison": {
            "state": "no_material_diff" if not comparison else "material_differences_found",
            "material_differences": comparison,
        },
        "obligations": obligations,
        "risks": risks,
        "findings": findings,
        "citations": list(citations.values()),
        "chunks": chunks,
        "source_documents": [_source_document(primary_spine, "primary"), _source_document(baseline_spine, "baseline")],
        "confidence": "medium" if findings else "high",
        "grounding": "grounded" if findings else "grounded_no_diff",
        "trace": {"engine": "contract_insights.analyze_contract_insights", "version": "0.1"},
    }
