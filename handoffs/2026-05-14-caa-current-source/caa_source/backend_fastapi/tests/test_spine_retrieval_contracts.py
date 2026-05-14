from __future__ import annotations

import unittest

from tools.doc_type_inference import attach_document_type, infer_document_type
from tools.production_spine import SpineSchemaError, build_spine_from_bronze
from tools.retrieval_evidence import DEFAULT_TOP_K, build_evidence_packet


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


NDA_TEXT = """NON-DISCLOSURE AGREEMENT

1 Confidential Information
The Disclosing Party may provide Confidential Information to the Receiving Party for a Permitted Purpose.

2 Survival
Confidentiality obligations survive termination for three years.
"""

CREDIT_TEXT = """CREDIT AGREEMENT

1 Facility
The Borrower may request loans from each Lender under the revolving credit facility.

2 Event of Default
Failure to pay principal or interest when due is an Event of Default.
"""

GENERIC_TEXT = """OPERATING MEMORANDUM

This document records intake steps, review owners, and a reminder to keep source evidence attached.

The parties will meet weekly to discuss open items.
"""


class TestSpineRetrievalContracts(unittest.TestCase):
    def test_3a_stable_spine_nodes_preserve_ids_and_spans(self) -> None:
        payload = _bronze_payload("analysis_nda", "nda.txt", NDA_TEXT)
        first = build_spine_from_bronze(payload)
        second = build_spine_from_bronze(payload)

        self.assertEqual([node.node_id for node in first.nodes], [node.node_id for node in second.nodes])
        self.assertGreaterEqual(len(first.nodes), 3)
        node = first.nodes[0]
        self.assertTrue(node.node_id.startswith("spine_"))
        self.assertIn(node.kind, {"heading", "paragraph"})
        self.assertGreater(node.span_end, node.span_start)
        self.assertEqual(node.meta["source"]["name"], "nda.txt")
        self.assertIn("excerpt", node.meta)
        self.assertEqual(first.meta["schema_version"], "contract_analyzer_spine_v1")

    def test_3a_generic_fixture_does_not_require_template_selection(self) -> None:
        spine = build_spine_from_bronze(_bronze_payload("analysis_generic", "generic.txt", GENERIC_TEXT))
        self.assertEqual(spine.spine_source, "bronze_v1")
        self.assertGreaterEqual(len(spine.nodes), 2)
        self.assertNotIn("template", spine.meta)

    def test_3a_malformed_bronze_returns_schema_error(self) -> None:
        with self.assertRaises(SpineSchemaError):
            build_spine_from_bronze({"schema_version": "unexpected", "analysis_id": "bad"})

    def test_3b_infers_nda_and_credit_with_confidence(self) -> None:
        nda = build_spine_from_bronze(_bronze_payload("analysis_nda", "nda.txt", NDA_TEXT))
        credit = build_spine_from_bronze(_bronze_payload("analysis_credit", "credit.txt", CREDIT_TEXT))

        nda_inference = infer_document_type(nda)
        credit_inference = infer_document_type(credit)

        self.assertEqual(nda_inference.label, "nda")
        self.assertFalse(nda_inference.fallback)
        self.assertGreaterEqual(nda_inference.confidence, 0.65)
        self.assertEqual(credit_inference.label, "credit_agreement")
        self.assertFalse(credit_inference.fallback)
        self.assertGreaterEqual(credit_inference.confidence, 0.65)

    def test_3b_generic_fixture_uses_visible_fallback(self) -> None:
        spine = build_spine_from_bronze(_bronze_payload("analysis_generic", "generic.txt", GENERIC_TEXT))
        attach_document_type(spine)
        inference = spine.meta["document_type"]
        self.assertEqual(inference["label"], "generic_contract")
        self.assertTrue(inference["fallback"])
        self.assertLess(inference["confidence"], 0.65)
        self.assertIn("signals", inference)

    def test_3c_evidence_packet_contains_cited_chunks(self) -> None:
        spine = build_spine_from_bronze(_bronze_payload("analysis_credit", "credit.txt", CREDIT_TEXT))
        packet = build_evidence_packet(spine, "event default interest")

        self.assertEqual(packet["schema_version"], "contract_analyzer_evidence_packet_v1")
        self.assertEqual(packet["top_k"], DEFAULT_TOP_K)
        self.assertFalse(packet["no_evidence"])
        self.assertGreaterEqual(len(packet["evidence"]), 1)
        first = packet["evidence"][0]
        self.assertIn("chunk_id", first)
        self.assertIn("source_node_ids", first)
        self.assertIn("source_document", first)
        self.assertGreater(first["span_end"], first["span_start"])
        self.assertIn("Event of Default", first["excerpt"])

    def test_3c_no_evidence_query_returns_low_confidence_empty_state(self) -> None:
        spine = build_spine_from_bronze(_bronze_payload("analysis_nda", "nda.txt", NDA_TEXT))
        packet = build_evidence_packet(spine, "quantum banana telemetry")

        self.assertTrue(packet["no_evidence"])
        self.assertEqual(packet["confidence"], "low")
        self.assertEqual(packet["evidence"], [])
        self.assertIn("No chunks met", packet["reason"])


if __name__ == "__main__":
    unittest.main()
