from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from tools.spine_types import SpineNode


TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    node_ids: list[str]
    span_start: int
    span_end: int
    mass: float
    excerpt: str
    page_start: int | None = None
    page_end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "node_ids": self.node_ids,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "mass": self.mass,
            "excerpt": self.excerpt,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }


@dataclass(slots=True)
class ChunkGraph:
    chunks: list[Chunk]
    params: dict[str, Any]


@dataclass(slots=True)
class ChunkHit:
    chunk_id: str
    score: float
    mass: float
    span_start: int
    span_end: int
    excerpt: str
    node_ids: list[str]
    page_start: int | None = None
    page_end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "score": self.score,
            "mass": self.mass,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "excerpt": self.excerpt,
            "node_ids": self.node_ids,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall((text or "").lower()))


def _coerce_nodes(nodes: list[SpineNode | dict[str, Any]]) -> list[SpineNode]:
    normalized: list[SpineNode] = []
    for index, node in enumerate(nodes, start=1):
        if isinstance(node, SpineNode):
            normalized.append(node)
            continue

        text = str(node.get("text", ""))
        normalized.append(
            SpineNode(
                node_id=str(node.get("node_id", f"node_{index}")),
                kind=str(node.get("kind", "paragraph")),
                title=str(node.get("title", "")),
                text=text,
                span_start=int(node.get("span_start", 0) or 0),
                span_end=int(node.get("span_end", 0) or 0),
                mass=float(node.get("mass", 1.0) or 1.0),
                meta=dict(node.get("meta", {})) if isinstance(node.get("meta", {}), dict) else {},
            )
        )

    normalized.sort(key=lambda item: (item.span_start, item.span_end, item.node_id))
    return normalized


def _strength(left: SpineNode, right: SpineNode) -> float:
    left_tokens = _tokenize(left.text)
    right_tokens = _tokenize(right.text)
    if not left_tokens or not right_tokens:
        return 0.0

    overlap_ratio = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    distance = max(1, right.span_start - left.span_end)
    distance_decay = 1.0 / (1.0 + distance / 400.0)
    return overlap_ratio * distance_decay


def build_chunks(nodes: list[SpineNode | dict[str, Any]], params: dict[str, Any] | None = None) -> ChunkGraph:
    options = dict(params or {})
    window = int(options.get("window", 6))

    working_nodes = _coerce_nodes(nodes)
    chunks: list[Chunk] = []
    index = 0

    while index < len(working_nodes):
        seed = working_nodes[index]
        chunk_nodes = [seed]
        end_index = index

        for candidate_index in range(index + 1, min(len(working_nodes), index + 1 + window)):
            candidate = working_nodes[candidate_index]
            current = chunk_nodes[-1]
            strength = _strength(current, candidate)
            threshold = 0.02 + 0.015 * ((current.mass + candidate.mass) / 2.0)
            if strength >= threshold:
                chunk_nodes.append(candidate)
                end_index = candidate_index
            else:
                break

        if end_index == index and chunk_nodes:
            end_index = index

        # Propagate page range from member nodes (None if nodes have no page info).
        page_starts = [n.page_start for n in chunk_nodes if n.page_start is not None]
        page_ends = [n.page_end for n in chunk_nodes if n.page_end is not None]
        excerpt = "\n\n".join(node.text for node in chunk_nodes if node.text).strip()
        chunks.append(
            Chunk(
                chunk_id=f"chunk_{len(chunks) + 1}",
                node_ids=[node.node_id for node in chunk_nodes],
                span_start=min(node.span_start for node in chunk_nodes),
                span_end=max(node.span_end for node in chunk_nodes),
                mass=round(sum(node.mass for node in chunk_nodes), 6),
                excerpt=excerpt,
                page_start=min(page_starts) if page_starts else None,
                page_end=max(page_ends) if page_ends else None,
            )
        )
        index = end_index + 1

    minimum_chunks = min(3, len(working_nodes))
    if len(chunks) < minimum_chunks and len(working_nodes) >= minimum_chunks:
        chunks = [
            Chunk(
                chunk_id=f"chunk_{idx}",
                node_ids=[node.node_id],
                span_start=node.span_start,
                span_end=node.span_end,
                mass=round(node.mass, 6),
                excerpt=node.text,
                page_start=node.page_start,
                page_end=node.page_end,
            )
            for idx, node in enumerate(working_nodes, start=1)
        ]

    options.setdefault("window", window)
    options.setdefault("merge", "mass_strength_naive")
    return ChunkGraph(chunks=chunks, params=options)


def rank_chunks(chunk_graph: ChunkGraph, query: str, k: int = 3) -> list[ChunkHit]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        query_tokens = {"contract"}

    scored: list[ChunkHit] = []
    for chunk in chunk_graph.chunks:
        chunk_tokens = _tokenize(chunk.excerpt)
        overlap = len(query_tokens & chunk_tokens)
        overlap_score = overlap / max(1, len(query_tokens))
        total_score = overlap_score + (chunk.mass * 0.01)
        scored.append(
            ChunkHit(
                chunk_id=chunk.chunk_id,
                score=round(total_score, 6),
                mass=chunk.mass,
                span_start=chunk.span_start,
                span_end=chunk.span_end,
                excerpt=chunk.excerpt,
                node_ids=chunk.node_ids,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
            )
        )

    scored.sort(key=lambda item: (item.score, item.mass), reverse=True)
    return scored[: max(1, k)]
