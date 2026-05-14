from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.auto_spine_builder import build_auto_spine
from tools.spine_types import SpineDoc, SpineNode


def _resolve_page(span_start: int, span_end: int, page_spans: list[dict]) -> tuple[int | None, int | None]:
    """Return (page_start, page_end) for a node's char span using the
    page_spans list from bronze metadata.
    page_spans entries: {page_number, span_start, span_end}."""
    if not page_spans:
        return None, None
    first_page: int | None = None
    last_page: int | None = None
    for ps in page_spans:
        ps_start = ps["span_start"]
        ps_end = ps["span_end"]
        # Node overlaps this page if their spans intersect.
        if ps_start < span_end and ps_end > span_start:
            page_num = ps["page_number"]
            if first_page is None:
                first_page = page_num
            last_page = page_num
    return first_page, last_page


class SpineSchemaError(ValueError):
    pass


def _text_from_bronze(payload: dict[str, Any]) -> str:
    text_block = payload.get("text")
    if isinstance(text_block, dict) and isinstance(text_block.get("full"), str):
        return text_block["full"]
    if isinstance(payload.get("extracted_text"), str):
        return payload["extracted_text"]
    raise SpineSchemaError("Bronze payload must include text.full or extracted_text.")


def _stable_node_id(*, analysis_id: str, kind: str, span_start: int, span_end: int, text: str) -> str:
    digest = hashlib.sha1()
    digest.update(analysis_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(kind.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(span_start).encode("ascii"))
    digest.update(b":")
    digest.update(str(span_end).encode("ascii"))
    digest.update(b"\0")
    digest.update(" ".join(text.lower().split()).encode("utf-8"))
    return f"spine_{digest.hexdigest()[:16]}"


def _load_payload(payload_or_path: dict[str, Any] | str | Path) -> tuple[dict[str, Any], str | None]:
    if isinstance(payload_or_path, dict):
        return payload_or_path, None
    path = Path(payload_or_path)
    return json.loads(path.read_text(encoding="utf-8")), str(path)


def build_spine_from_bronze(payload_or_path: dict[str, Any] | str | Path) -> SpineDoc:
    payload, source_path = _load_payload(payload_or_path)
    if payload.get("schema_version") != "contract_analyzer_bronze_v1":
        raise SpineSchemaError("Unsupported bronze schema_version.")

    analysis_id = str(payload.get("analysis_id") or "").strip()
    if not analysis_id:
        raise SpineSchemaError("Bronze payload must include analysis_id.")

    text = _text_from_bronze(payload)
    if not text.strip():
        raise SpineSchemaError("Bronze payload text is empty.")

    source = dict(payload.get("source", {})) if isinstance(payload.get("source"), dict) else {}
    metadata = payload.get("metadata") or {}
    page_spans: list[dict] = metadata.get("page_spans") or []

    auto_doc = build_auto_spine(text)
    nodes: list[SpineNode] = []
    for index, node in enumerate(auto_doc.nodes, start=1):
        stable_id = _stable_node_id(
            analysis_id=analysis_id,
            kind=node.kind,
            span_start=node.span_start,
            span_end=node.span_end,
            text=node.text,
        )
        page_start, page_end = _resolve_page(node.span_start, node.span_end, page_spans)
        nodes.append(
            SpineNode(
                node_id=stable_id,
                kind=node.kind,
                title=node.title,
                text=node.text,
                span_start=node.span_start,
                span_end=node.span_end,
                mass=node.mass,
                page_start=page_start,
                page_end=page_end,
                meta={
                    **node.meta,
                    "source": source,
                    "source_analysis_id": analysis_id,
                    "source_span": {"start": node.span_start, "end": node.span_end},
                    "excerpt": node.text[:280],
                    "deterministic_id_rule": "sha1(analysis_id, kind, span_start, span_end, normalized_text)[:16]",
                    "ordinal": index,
                },
            )
        )

    return SpineDoc(
        nodes=nodes,
        spine_source="bronze_v1",
        meta={
            "schema_version": "contract_analyzer_spine_v1",
            "analysis_id": analysis_id,
            "source": source,
            "source_bronze_path": source_path,
            "builder": "production_spine.build_spine_from_bronze",
            "node_count": len(nodes),
        },
    )
