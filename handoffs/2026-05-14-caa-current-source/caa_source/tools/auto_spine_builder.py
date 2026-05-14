from __future__ import annotations

import re

from tools.spine_types import SpineDoc, SpineNode

_BLOCK_PATTERN = re.compile(r"\S[\s\S]*?(?=\n\s*\n|\Z)")
_HEADING_PATTERN = re.compile(r"^(SECTION|ARTICLE)\b|^\d+(\.\d+)*\b|^[A-Z][A-Z\s]{8,}$")


def _mass(kind: str, num_chars: int) -> float:
    kind_bonus = 0.35 if kind == "heading" else 0.0
    return round(1.0 + 0.002 * num_chars + kind_bonus, 6)


def build_auto_spine(full_text: str) -> SpineDoc:
    nodes: list[SpineNode] = []

    for index, block_match in enumerate(_BLOCK_PATTERN.finditer(full_text), start=1):
        raw = block_match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue

        leading_ws = len(raw) - len(raw.lstrip())
        trailing_ws = len(raw) - len(raw.rstrip())
        span_start = block_match.start() + leading_ws
        span_end = block_match.end() - trailing_ws

        first_line = stripped.splitlines()[0].strip() if stripped else ""
        kind = "heading" if _HEADING_PATTERN.match(first_line) else "paragraph"
        title = first_line if kind == "heading" else f"Paragraph {index}"

        nodes.append(
            SpineNode(
                node_id=f"auto_{index}",
                kind=kind,
                title=title,
                text=stripped,
                span_start=span_start,
                span_end=span_end,
                mass=_mass(kind, len(stripped)),
                meta={"builder": "auto_spine_builder", "index": index},
            )
        )

    return SpineDoc(
        nodes=nodes,
        spine_source="auto",
        meta={"builder": "auto_spine_builder", "block_count": len(nodes)},
    )
