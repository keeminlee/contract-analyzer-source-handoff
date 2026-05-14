from __future__ import annotations

from typing import Any

CLAUSE_PATTERNS: list[tuple[tuple[str, ...], str, float]] = [
    (("limitation of liability",), "limitation_of_liability", 0.93),
    (("indemn",), "indemnity", 0.92),
    (("governing law", "jurisdiction", "venue"), "governing_law", 0.91),
    (("data protection", "privacy", "personal data"), "data_protection", 0.9),
    (("termination", "expiry", "survival"), "termination", 0.89),
    (("payment", "fees", "interest rate", "principal", "repayment", "prepayment"), "payment_terms", 0.91),
    (("event of default", "cross default", "default"), "event_of_default", 0.94),
    (("financial covenant", "covenant", "debt service", "leverage ratio"), "financial_covenants", 0.93),
    (("security interest", "collateral", "pledge", "lien"), "collateral_security", 0.94),
    (("representation", "warranty"), "representations_and_warranties", 0.9),
    (("guaranty", "guarantee"), "guarantees", 0.9),
    (("conditions precedent",), "conditions_precedent", 0.9),
    (("confidential",), "confidentiality", 0.88),
]


def classify(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("type") not in {"clause", "section_heading"}:
            continue
        label = (node.get("label") or "").lower()
        semantic_type = "unknown_clause"
        confidence = 0.55
        for keywords, mapped, pattern_confidence in CLAUSE_PATTERNS:
            if any(keyword in label for keyword in keywords):
                semantic_type = mapped
                confidence = pattern_confidence
                break
        enriched = dict(node)
        enriched["type"] = semantic_type
        enriched["confidence"] = max(node.get("confidence", 0.0), confidence)
        enriched["provenance"] = {"tool": "clause_classifier", "version": "0.1"}
        classified.append(enriched)
    return classified
