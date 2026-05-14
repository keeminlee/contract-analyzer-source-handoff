from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.spine_types import SpineDoc


@dataclass(frozen=True, slots=True)
class DocumentTypeInference:
    label: str
    confidence: float
    fallback: bool
    reasons: list[str]
    signals: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "fallback": self.fallback,
            "reasons": self.reasons,
            "signals": self.signals,
        }


SIGNALS: dict[str, tuple[str, ...]] = {
    "nda": (
        "non-disclosure",
        "nondisclosure",
        "confidential information",
        "receiving party",
        "disclosing party",
        "permitted purpose",
    ),
    "credit_agreement": (
        "credit agreement",
        "borrower",
        "lender",
        "facility",
        "interest rate",
        "event of default",
        "commitment",
    ),
    "loan_agreement": (
        "loan agreement",
        "principal amount",
        "repayment",
        "maturity date",
        "promissory",
    ),
    "msa": (
        "master services agreement",
        "statement of work",
        "services",
        "service provider",
        "fees",
    ),
}


def _as_text(spine_or_text: SpineDoc | str) -> str:
    if isinstance(spine_or_text, SpineDoc):
        return "\n\n".join(node.text for node in spine_or_text.nodes)
    return str(spine_or_text)


def infer_document_type(spine_or_text: SpineDoc | str) -> DocumentTypeInference:
    lowered = _as_text(spine_or_text).lower()
    counts = {
        label: sum(1 for keyword in keywords if keyword in lowered)
        for label, keywords in SIGNALS.items()
    }
    best_label = max(counts, key=lambda label: counts[label])
    best_count = counts[best_label]

    if best_count == 0:
        return DocumentTypeInference(
            label="generic_contract",
            confidence=0.25,
            fallback=True,
            reasons=["No high-signal document-type keywords were found."],
            signals=counts,
        )

    second_count = max((count for label, count in counts.items() if label != best_label), default=0)
    confidence = min(0.95, 0.45 + (best_count * 0.1) + max(0, best_count - second_count) * 0.05)
    fallback = confidence < 0.65
    reasons = [
        f"Matched {best_count} {best_label} signal(s).",
    ]
    if second_count:
        reasons.append(f"Nearest competing signal count: {second_count}.")
    if fallback:
        return DocumentTypeInference(
            label="generic_contract",
            confidence=round(confidence, 3),
            fallback=True,
            reasons=reasons + ["Confidence below typed-routing threshold; using generic fallback."],
            signals=counts,
        )
    return DocumentTypeInference(
        label=best_label,
        confidence=round(confidence, 3),
        fallback=False,
        reasons=reasons,
        signals=counts,
    )


def attach_document_type(spine_doc: SpineDoc) -> SpineDoc:
    inference = infer_document_type(spine_doc)
    spine_doc.meta["document_type"] = inference.to_dict()
    return spine_doc
