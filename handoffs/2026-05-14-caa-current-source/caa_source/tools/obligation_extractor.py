from __future__ import annotations

from typing import Any

TRIGGER_WORDS = ["shall", "must", "will", "agrees to", "required to"]


def extract(classified_nodes: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    obligations: list[dict[str, Any]] = []
    lower_text = text.lower()

    for idx, node in enumerate(classified_nodes, start=1):
        start = int(node.get("span_start", 0))
        end = int(node.get("span_end", start))
        window = lower_text[start : min(len(lower_text), end + 400)]

        if any(trigger in window for trigger in TRIGGER_WORDS):
            obligations.append(
                {
                    "node_id": f"obligation_{idx}",
                    "source_node_id": node.get("node_id"),
                    "type": "obligation",
                    "span_start": start,
                    "span_end": min(len(text), end + 200),
                    "confidence": 0.8,
                    "provenance": {"tool": "obligation_extractor", "version": "0.1"},
                }
            )

    return obligations
