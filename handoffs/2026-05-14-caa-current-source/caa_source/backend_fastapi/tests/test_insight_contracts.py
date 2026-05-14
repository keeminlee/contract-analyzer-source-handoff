from __future__ import annotations

import unittest

from tools.comparison_policy import BASELINE_SOURCE_SECOND_UPLOAD, default_baseline_policy
from tools.contract_insights import analyze_contract_insights
from tools.insight_packet import build_insight_answer_packet
from tools.production_spine import build_spine_from_bronze


def _bronze_payload(analysis_id: str, filename: str, text: str) -> dict:
    return {
        "schema_version": "contract_analyzer_bronze_v1",
        "analysis_id": analysis_id,
        "session_id": analysis_id,
        "source": {
            "name": filename,
            "extension": "." + filename.rsplit(".", 1)[-1],
            "size_bytes": len(text.encode("utf-8")),
            "content_type": "text/plain",
        },
        "text": {"full": text, "char_count": len(text)},
        "extracted_text": text,
        "chunks": [],
        "tables": [],
        "metadata": {},
    }


BASELINE_CREDIT = """CREDIT AGREEMENT

1 Interest
The Borrower shall pay interest at 5 percent per annum.

2 Event of Default
Failure to pay principal or interest when due is an Event of Default.

3 Financial Covenants
The Borrower must maintain quarterly leverage covenant reporting.
"""

DEVIATION_CREDIT = """CREDIT AGREEMENT

1 Interest
The Borrower shall pay interest at 9 percent per annum.

2 Event of Default
Failure to pay principal or interest when due is an Event of Default after a 30 day cure period.

3 Financial Covenants
The Borrower will provide annual covenant reporting.
"""


def _spine(analysis_id: str, filename: str, text: str):
    return build_spine_from_bronze(_bronze_payload(analysis_id, filename, text))


class TestInsightContracts(unittest.TestCase):
    def test_5a_baseline_policy_selects_second_upload_and_exposes_api_contract(self) -> None:
        policy = default_baseline_policy()

        self.assertEqual(policy.source, BASELINE_SOURCE_SECOND_UPLOAD)
        self.assertEqual(policy.status, "resolved")
        self.assertIn("primary_analysis_id", policy.api_implications["required_for_comparison"])
        self.assertIn("baseline_analysis_id", policy.api_implications["required_for_comparison"])
        self.assertEqual(policy.api_implications["precedent_store"], "reference_only_for_v1_not_authoritative_baseline")

    def test_5a_missing_baseline_returns_solo_analysis(self) -> None:
        primary = _spine("primary_missing_baseline", "primary.txt", BASELINE_CREDIT)
        analysis = analyze_contract_insights(primary_spine=primary, baseline_spine=None)

        self.assertEqual(analysis["analysis_state"], "complete")
        self.assertEqual(analysis["baseline_state"]["state"], "no_baseline_supplied")
        self.assertEqual(analysis["comparison"]["state"], "no_baseline_supplied")
        self.assertEqual(analysis["comparison"]["material_differences"], [])
        self.assertTrue(analysis["obligations"])
        self.assertTrue(analysis["risks"])
        self.assertTrue(analysis["findings"])
        self.assertTrue(analysis["citations"])
        self.assertEqual({doc["role"] for doc in analysis["source_documents"]}, {"primary"})

    def test_5b_same_document_comparison_yields_no_material_diff(self) -> None:
        primary = _spine("same_primary", "primary.txt", BASELINE_CREDIT)
        baseline = _spine("same_baseline", "baseline.txt", BASELINE_CREDIT)
        analysis = analyze_contract_insights(primary_spine=primary, baseline_spine=baseline)

        self.assertEqual(analysis["analysis_state"], "complete")
        self.assertEqual(analysis["comparison"]["state"], "no_material_diff")
        self.assertEqual(analysis["comparison"]["material_differences"], [])

    def test_5b_known_deviation_produces_cited_comparison_and_risk_output(self) -> None:
        primary = _spine("deviation_primary", "primary.txt", DEVIATION_CREDIT)
        baseline = _spine("deviation_baseline", "baseline.txt", BASELINE_CREDIT)
        analysis = analyze_contract_insights(primary_spine=primary, baseline_spine=baseline)

        self.assertEqual(analysis["comparison"]["state"], "material_differences_found")
        comparison = analysis["comparison"]["material_differences"][0]
        self.assertEqual(comparison["finding_type"], "comparison_deviation")
        self.assertGreaterEqual(len(comparison["citation_ids"]), 2)
        citation_roles = {citation["document_role"] for citation in analysis["citations"]}
        self.assertIn("primary", citation_roles)
        self.assertIn("baseline", citation_roles)
        self.assertTrue(analysis["risks"])

    def test_5b_obligation_and_risk_outputs_include_chunk_span_citations(self) -> None:
        primary = _spine("obligation_primary", "primary.txt", DEVIATION_CREDIT)
        baseline = _spine("obligation_baseline", "baseline.txt", BASELINE_CREDIT)
        analysis = analyze_contract_insights(primary_spine=primary, baseline_spine=baseline)

        self.assertTrue(analysis["obligations"])
        self.assertTrue(analysis["risks"])
        citation_by_id = {citation["citation_id"]: citation for citation in analysis["citations"]}
        for finding in analysis["obligations"] + analysis["risks"]:
            self.assertTrue(finding["citation_ids"])
            for citation_id in finding["citation_ids"]:
                citation = citation_by_id[citation_id]
                self.assertIn("chunk_id", citation)
                self.assertGreater(citation["span_end"], citation["span_start"])
                self.assertIn("excerpt", citation)

    def test_5c_answer_packet_contains_ui_evidence_fields(self) -> None:
        primary = _spine("packet_primary", "primary.txt", DEVIATION_CREDIT)
        baseline = _spine("packet_baseline", "baseline.txt", BASELINE_CREDIT)
        analysis = analyze_contract_insights(primary_spine=primary, baseline_spine=baseline)
        packet = build_insight_answer_packet(query="Compare risk obligations", analysis=analysis)

        self.assertEqual(packet["schema_version"], "contract_analyzer_insight_answer_packet_v1")
        self.assertEqual(packet["grounding"], "grounded")
        self.assertTrue(packet["answer_text"])
        self.assertTrue(packet["findings"])
        self.assertTrue(packet["citations"])
        self.assertTrue(packet["chunks"])
        self.assertEqual({doc["role"] for doc in packet["source_documents"]}, {"primary", "baseline"})
        self.assertIn("trace_metadata", packet)

    def test_5c_uncited_generated_claim_converts_to_abstention(self) -> None:
        primary = _spine("uncited_primary", "primary.txt", DEVIATION_CREDIT)
        baseline = _spine("uncited_baseline", "baseline.txt", BASELINE_CREDIT)
        analysis = analyze_contract_insights(primary_spine=primary, baseline_spine=baseline)
        packet = build_insight_answer_packet(
            query="Compare risk obligations",
            analysis=analysis,
            generated_answer="The agreement is risky because pricing changed.",
        )

        self.assertEqual(packet["grounding"], "not_grounded")
        self.assertEqual(packet["answer_text"], "")
        self.assertIn("uncited_claim_rejected", packet["warnings"])


if __name__ == "__main__":
    unittest.main()
