from __future__ import annotations

import re
from typing import Any

from tools.dynamic_chunker import build_chunks, rank_chunks
from tools.spine_types import SpineDoc


DEFAULT_TOP_K = 3
TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


def _tokens(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall((text or "").lower()))


def build_evidence_packet(
    spine_doc: SpineDoc,
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_overlap: int = 1,
) -> dict[str, Any]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return {
            "schema_version": "contract_analyzer_evidence_packet_v1",
            "query": query,
            "top_k": top_k,
            "evidence": [],
            "confidence": "low",
            "no_evidence": True,
            "reason": "Query contains no retrievable tokens.",
            "source_document": spine_doc.meta.get("source", {}),
            "analysis_id": spine_doc.meta.get("analysis_id"),
        }

    chunk_graph = build_chunks(spine_doc.nodes)
    raw_hits = rank_chunks(chunk_graph, query, k=max(1, top_k))
    evidence: list[dict[str, Any]] = []
    node_lookup = {node.node_id: node for node in spine_doc.nodes}

    for rank, hit in enumerate(raw_hits, start=1):
        overlap = len(query_tokens & _tokens(hit.excerpt))
        if overlap < min_overlap:
            continue
        evidence.append(
            {
                "rank": rank,
                "chunk_id": hit.chunk_id,
                "score": hit.score,
                "span_start": hit.span_start,
                "span_end": hit.span_end,
                "page_start": hit.page_start,
                "page_end": hit.page_end,
                "excerpt": hit.excerpt,
                "source_node_ids": hit.node_ids,
                "source_nodes": [
                    {
                        "node_id": node.node_id,
                        "kind": node.kind,
                        "title": node.title,
                        "span_start": node.span_start,
                        "span_end": node.span_end,
                        "page_start": node.page_start,
                        "page_end": node.page_end,
                    }
                    for node_id in hit.node_ids
                    if (node := node_lookup.get(node_id)) is not None
                ],
                "source_document": spine_doc.meta.get("source", {}),
                # pdf_url is populated by the route layer once we know the analysis_id;
                # left as None here so downstream consumers can check presence.
                "pdf_url": None,
            }
        )

    analysis_id = spine_doc.meta.get("analysis_id")
    return {
        "schema_version": "contract_analyzer_evidence_packet_v1",
        "query": query,
        "top_k": top_k,
        "retrieval_params": {"top_k_default": DEFAULT_TOP_K, "min_overlap": min_overlap},
        "evidence": evidence,
        "confidence": "medium" if evidence else "low",
        "no_evidence": not evidence,
        "reason": None if evidence else "No chunks met the lexical evidence threshold.",
        "source_document": spine_doc.meta.get("source", {}),
        "analysis_id": analysis_id,
        # Route fills this in: /api/v1/analyses/{id}/pdf
        "pdf_url": f"/api/v1/analyses/{analysis_id}/pdf" if analysis_id else None,
    }
