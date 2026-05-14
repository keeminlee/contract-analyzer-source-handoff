from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BASELINE_POLICY_SCHEMA_VERSION = "contract_analyzer_baseline_policy_v1"
BASELINE_SOURCE_SECOND_UPLOAD = "second_user_upload"
MISSING_BASELINE_BLOCKER = "missing_second_upload_baseline"


@dataclass(frozen=True, slots=True)
class BaselinePolicy:
    source: str
    status: str
    api_implications: dict[str, Any]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BASELINE_POLICY_SCHEMA_VERSION,
            "source": self.source,
            "status": self.status,
            "api_implications": self.api_implications,
            "reasons": self.reasons,
        }


def default_baseline_policy() -> BaselinePolicy:
    return BaselinePolicy(
        source=BASELINE_SOURCE_SECOND_UPLOAD,
        status="resolved",
        api_implications={
            "upload_contract": "primary_upload_plus_optional_baseline_upload",
            "required_for_comparison": ["primary_analysis_id", "baseline_analysis_id"],
            "backend_inputs": ["primary_spine", "baseline_spine"],
            "ui_inputs": ["primary document upload", "compare-against document upload"],
            "precedent_store": "reference_only_for_v1_not_authoritative_baseline",
            "missing_baseline_behavior": "return structured blocked state without comparison claims",
        },
        reasons=[
            "The production plan leaves precedent-store authority unresolved.",
            "Second user upload is the smallest reviewable v1 comparison source.",
            "Failing closed avoids silently comparing against an unapproved baseline.",
        ],
    )


def missing_baseline_state(policy: BaselinePolicy | None = None) -> dict[str, Any]:
    active_policy = policy or default_baseline_policy()
    return {
        "schema_version": "contract_analyzer_baseline_state_v1",
        "state": "blocked",
        "blocker": MISSING_BASELINE_BLOCKER,
        "message": "Comparison requires a second uploaded baseline contract for v1.",
        "baseline_policy": active_policy.to_dict(),
        "required_api_inputs": active_policy.api_implications["required_for_comparison"],
        "allowed_sources": [
            BASELINE_SOURCE_SECOND_UPLOAD,
            "managed_precedent_store",
            "both",
            "blocked_out_of_mvp",
        ],
    }
