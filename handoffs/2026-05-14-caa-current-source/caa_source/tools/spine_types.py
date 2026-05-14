from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SpineNode:
    node_id: str
    kind: str
    title: str
    text: str
    span_start: int
    span_end: int
    mass: float
    meta: dict[str, Any] = field(default_factory=dict)
    page_start: int | None = None
    page_end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "mass": self.mass,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "meta": self.meta,
        }


@dataclass(slots=True)
class SpineDoc:
    nodes: list[SpineNode]
    spine_source: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spine_source": self.spine_source,
            "meta": self.meta,
            "nodes": [node.to_dict() for node in self.nodes],
        }
