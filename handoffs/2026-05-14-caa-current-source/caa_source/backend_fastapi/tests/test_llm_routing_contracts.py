from __future__ import annotations

from pathlib import Path
import unittest

from tools.aida_proxy_client import AiDaProxyClient, AiDaProxyError, AIDA_V1_MODEL_PATH
from tools.evidence_generation import generate_grounded_answer
from tools.semantic_router import COMPARISON_POLICY_BLOCKER, route_query


class FakeTransport:
    def __init__(self, text: str = "The default is cited in [chunk_1].", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.requests: list[dict] = []

    def generate(self, request: dict) -> dict:
        self.requests.append(request)
        if self.error:
            raise self.error
        return {"response": {"content": [{"text": self.text}]}}


def _evidence_packet() -> dict:
    return {
        "schema_version": "contract_analyzer_evidence_packet_v1",
        "query": "event default",
        "top_k": 3,
        "evidence": [
            {
                "rank": 1,
                "chunk_id": "chunk_1",
                "score": 1.2,
                "span_start": 10,
                "span_end": 50,
                "excerpt": "Failure to pay interest is an Event of Default.",
                "source_node_ids": ["spine_1"],
                "source_document": {"name": "credit.txt"},
            }
        ],
        "confidence": "medium",
        "no_evidence": False,
        "source_document": {"name": "credit.txt"},
        "analysis_id": "analysis_credit",
    }


class TestLlmRoutingContracts(unittest.TestCase):
    def test_4a_proxy_client_builds_aida_request_without_direct_provider_imports(self) -> None:
        transport = FakeTransport("Answer from [chunk_1].")
        client = AiDaProxyClient(transport)
        response = client.generate("Use evidence [chunk_1].")

        self.assertEqual(response["model_path"], AIDA_V1_MODEL_PATH)
        request = transport.requests[0]
        self.assertEqual(request["proxy"], "aida_oauth_api_gateway_bedrock")
        self.assertIn("x-apigw-api-id", request["headers"])
        self.assertIn("inferenceProfileId", request["payload"])
        source = Path("tools/aida_proxy_client.py").read_text(encoding="utf-8")
        self.assertNotIn("import boto3", source)
        self.assertNotIn("bedrock-runtime", source)

    def test_4a_proxy_failure_returns_structured_error(self) -> None:
        transport = FakeTransport(error=AiDaProxyError("auth_failed", "Token unavailable."))
        client = AiDaProxyClient(transport)
        with self.assertRaises(AiDaProxyError) as ctx:
            client.generate("Use evidence [chunk_1].")
        self.assertEqual(ctx.exception.to_dict()["code"], "auth_failed")

    def test_4b_routes_representative_queries_and_blocks_comparison(self) -> None:
        overview = route_query("Summarize this agreement at a high level")
        precision = route_query("Which clause cites the event of default?")
        insight = route_query("List risk obligations and covenants")
        comparison = route_query("Compare this against the prior agreement")

        self.assertEqual(overview.mode, "overview")
        self.assertEqual(precision.mode, "precision")
        self.assertEqual(insight.mode, "insight")
        self.assertEqual(comparison.mode, "comparison")
        self.assertTrue(comparison.blocked)
        self.assertEqual(comparison.blocker, COMPARISON_POLICY_BLOCKER)
        self.assertIn("baseline_document_or_policy", comparison.required_evidence_inputs)

    def test_4b_ambiguous_query_requests_clarification(self) -> None:
        decision = route_query("help")
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.mode, "clarify")
        self.assertLess(decision.confidence, 0.5)
        self.assertIsNotNone(decision.clarification)

    def test_4c_grounded_answer_cites_evidence_chunk(self) -> None:
        route = route_query("Which clause cites the event of default?")
        transport = FakeTransport("Failure to pay interest is an Event of Default [chunk_1].")
        answer = generate_grounded_answer(
            query="Which clause cites the event of default?",
            evidence_packet=_evidence_packet(),
            route=route,
            client=AiDaProxyClient(transport),
        )

        self.assertEqual(answer["schema_version"], "contract_analyzer_grounded_answer_v1")
        self.assertEqual(answer["grounding_state"], "grounded")
        self.assertEqual(answer["citations"], ["chunk_1"])
        self.assertIn("[chunk_1]", answer["answer_text"])

    def test_4c_no_evidence_abstains_without_proxy_call(self) -> None:
        route = route_query("Which clause cites the event of default?")
        transport = FakeTransport()
        packet = {**_evidence_packet(), "evidence": [], "no_evidence": True}
        answer = generate_grounded_answer(
            query="Which clause cites the event of default?",
            evidence_packet=packet,
            route=route,
            client=AiDaProxyClient(transport),
        )

        self.assertEqual(answer["grounding_state"], "not_grounded")
        self.assertEqual(answer["abstention_reason"], "No retrieved evidence supports this answer.")
        self.assertEqual(transport.requests, [])

    def test_4c_proxy_error_abstains_without_claims(self) -> None:
        route = route_query("Which clause cites the event of default?")
        transport = FakeTransport(error=AiDaProxyError("proxy_timeout", "Proxy timed out."))
        answer = generate_grounded_answer(
            query="Which clause cites the event of default?",
            evidence_packet=_evidence_packet(),
            route=route,
            client=AiDaProxyClient(transport),
        )

        self.assertEqual(answer["grounding_state"], "proxy_error")
        self.assertEqual(answer["answer_text"], "")
        self.assertEqual(answer["error"]["code"], "proxy_timeout")
        self.assertIn("proxy_failure", answer["warnings"])


if __name__ == "__main__":
    unittest.main()
