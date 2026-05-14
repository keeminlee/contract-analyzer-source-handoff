from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.spine_types import SpineDoc, SpineNode


def _calc_mass(kind: str, text: str, existing_mass: Any = None) -> float:
    if isinstance(existing_mass, (int, float)):
        return float(existing_mass)
    kind_bonus = 0.35 if kind == "heading" else 0.0
    return round(1.0 + 0.002 * len(text) + kind_bonus, 6)


def _normalize_kind(raw_type: str, section_name: str) -> str:
    lowered = (raw_type or section_name or "").lower()
    if "heading" in lowered or section_name == "headings":
        return "heading"
    return "paragraph"


def _node_title(node: dict[str, Any], kind: str) -> str:
    if node.get("title"):
        return str(node["title"])
    if node.get("label"):
        return str(node["label"])
    if node.get("term"):
        return str(node["term"])
    if kind == "heading":
        return "Heading"
    return "Paragraph"


def _node_text(node: dict[str, Any]) -> str:
    if node.get("text"):
        return str(node["text"])
    if node.get("label"):
        return str(node["label"])
    if node.get("value"):
        return str(node["value"])
    if node.get("term"):
        return str(node["term"])
    return ""


def _normalize_spine_node(node: dict[str, Any], section_name: str, fallback_index: int) -> SpineNode:
    kind = _normalize_kind(str(node.get("type", "")), section_name)
    text = _node_text(node)
    span_start = int(node.get("span_start", 0) or 0)
    span_end = int(node.get("span_end", span_start) or span_start)
    node_id = str(node.get("node_id") or f"{section_name}_{fallback_index}")

    return SpineNode(
        node_id=node_id,
        kind=kind,
        title=_node_title(node, kind),
        text=text,
        span_start=span_start,
        span_end=span_end,
        mass=_calc_mass(kind, text, node.get("mass")),
        meta={"source_section": section_name, "raw": node},
    )


def load_silver_spine(path: str | Path) -> SpineDoc:
    silver_path = Path(path)
    payload = json.loads(silver_path.read_text(encoding="utf-8"))
    raw_spine = payload.get("spine", {})

    nodes: list[SpineNode] = []
    for section_name in ("headings", "clauses", "definitions"):
        for index, node in enumerate(raw_spine.get(section_name, []), start=1):
            if isinstance(node, dict):
                nodes.append(_normalize_spine_node(node, section_name, index))

    nodes.sort(key=lambda item: (item.span_start, item.span_end, item.node_id))
    return SpineDoc(
        nodes=nodes,
        spine_source="silver",
        meta={
            "silver_path": str(silver_path),
            "document": payload.get("document", {}),
        },
    )


def save_spine(path: str | Path, spine_doc: SpineDoc) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spine_doc.to_dict(), indent=2), encoding="utf-8")
