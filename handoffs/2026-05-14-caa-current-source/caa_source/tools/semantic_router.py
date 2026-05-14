from __future__ import annotations

from dataclasses import dataclass
from typing import Any


COMPARISON_POLICY_BLOCKER = "comparison_baseline_policy_unresolved_step_5"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    mode: str
    intent: str
    confidence: float
    reasons: list[str]
    selected_pipeline_path: str
    required_evidence_inputs: list[str]
    blocked: bool = False
    clarification: str | None = None
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "intent": self.intent,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "selected_pipeline_path": self.selected_pipeline_path,
            "required_evidence_inputs": self.required_evidence_inputs,
            "blocked": self.blocked,
            "clarification": self.clarification,
            "blocker": self.blocker,
        }


def route_query(query: str, *, comparison_baseline_resolved: bool = False) -> RouteDecision:
    normalized = " ".join((query or "").lower().split())
    if not normalized or len(normalized) < 8:
        return RouteDecision(
            mode="clarify",
            intent="ambiguous",
            confidence=0.2,
            reasons=["Query is empty or too short to route safely."],
            selected_pipeline_path="clarification_required",
            required_evidence_inputs=[],
            blocked=True,
            clarification="Ask a more specific contract-analysis question.",
        )

    if any(token in normalized for token in ("compare", "against baseline", "prior agreement", "precedent")):
        if not comparison_baseline_resolved:
            return RouteDecision(
                mode="comparison",
                intent="compare_terms",
                confidence=0.78,
                reasons=["Comparison keyword detected.", "Step 5 baseline policy is unresolved."],
                selected_pipeline_path="blocked_until_step_5_baseline_policy",
                required_evidence_inputs=["primary_spine", "baseline_document_or_policy"],
                blocked=True,
                blocker=COMPARISON_POLICY_BLOCKER,
            )
        return RouteDecision(
            mode="comparison",
            intent="compare_terms",
            confidence=0.78,
            reasons=["Comparison keyword detected."],
            selected_pipeline_path="comparison_pipeline",
            required_evidence_inputs=["primary_spine", "baseline_document_or_policy"],
        )

    if any(token in normalized for token in ("where", "which clause", "cite", "evidence", "exact", "interest", "confidential")):
        return RouteDecision(
            mode="precision",
            intent="answer_specific_question",
            confidence=0.72,
            reasons=["Precision/citation signal detected."],
            selected_pipeline_path="precision_evidence_pipeline",
            required_evidence_inputs=["evidence_packet"],
        )

    if any(token in normalized for token in ("risk", "obligation", "covenant", "default", "termination", "liability")):
        return RouteDecision(
            mode="insight",
            intent="extract_risks_or_obligations",
            confidence=0.74,
            reasons=["Risk/obligation signal detected."],
            selected_pipeline_path="evidence_insight_pipeline",
            required_evidence_inputs=["evidence_packet", "spine_doc"],
        )

    if any(token in normalized for token in ("summarize", "overview", "what is", "describe", "high level")):
        return RouteDecision(
            mode="overview",
            intent="summarize_contract",
            confidence=0.7,
            reasons=["Overview signal detected."],
            selected_pipeline_path="overview_pipeline",
            required_evidence_inputs=["spine_doc", "evidence_packet"],
        )

    return RouteDecision(
        mode="clarify",
        intent="ambiguous",
        confidence=0.35,
        reasons=["No strong overview, precision, comparison, or insight signal detected."],
        selected_pipeline_path="clarification_required",
        required_evidence_inputs=[],
        blocked=True,
        clarification="Ask for an overview, a specific cited clause, a comparison, or a risk/obligation review.",
    )
