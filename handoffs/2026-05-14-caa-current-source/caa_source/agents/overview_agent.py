from __future__ import annotations

from collections import Counter
from typing import Any


def run_overview(classified_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(node.get("type", "unknown_clause") for node in classified_nodes)

    hypotheses: list[str] = []
    if counts.get("limitation_of_liability", 0) == 0:
        hypotheses.append("Limitation of liability may be missing or uncapped.")
    if counts.get("termination", 0) > 0:
        hypotheses.append("Termination language detected; review for convenience termination rights.")
    if counts.get("indemnity", 0) > 0:
        hypotheses.append("Indemnity language detected; verify breadth against baseline.")
    if not hypotheses:
        hypotheses.append("No obvious high-risk deviations detected in quick scan.")

    return {
        "mode": "overview",
        "hypotheses": hypotheses,
        "clause_type_counts": dict(counts),
    }
