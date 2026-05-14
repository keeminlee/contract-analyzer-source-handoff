from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend_fastapi.main import app

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from caa_backend.storage import BronzeStore  # noqa: E402
from tools.aida_proxy_client import AiDaProxyClient
from tools.contract_insights import analyze_contract_insights
from tools.evidence_generation import generate_grounded_answer
from tools.insight_packet import build_insight_answer_packet
from tools.production_spine import build_spine_from_bronze
from tools.retrieval_evidence import build_evidence_packet
from tools.semantic_router import route_query


PRIMARY_CONTRACT = """CREDIT AGREEMENT

1 Interest
The Borrower shall pay interest at 9 percent per annum.

2 Event of Default
Failure to pay principal or interest when due is an Event of Default after a 30 day cure period.

3 Financial Covenants
The Borrower will provide annual covenant reporting.
"""

BASELINE_CONTRACT = """CREDIT AGREEMENT

1 Interest
The Borrower shall pay interest at 5 percent per annum.

2 Event of Default
Failure to pay principal or interest when due is an Event of Default.

3 Financial Covenants
The Borrower must maintain quarterly leverage covenant reporting.
"""


class FakeAiDaTransport:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def generate(self, request: dict) -> dict:
        self.requests.append(request)
        prompt = request["payload"]["body"]["messages"][0]["content"]
        chunk_id = next(line[1:].split("]", 1)[0] for line in prompt.splitlines() if line.startswith("["))
        return {"response": {"content": [{"text": f"The payment-default answer is supported by [{chunk_id}]."}]}}


class TestE2EValidationContracts(unittest.TestCase):
    def setUp(self) -> None:
        # Step 3 (logging) added `verify_azure_token` to /uploads; bypass via CAA_SKIP_AUTH=1.
        # Step 3 (singlestore) routes bronze through `BronzeStore` inmemory shim in tests.
        # Step 7 of singlestore migration: `app.state.bronze_storage_dir`
        # removed (Step 6 discard); inmemory backend handles persistence.
        os.environ["CAA_SKIP_AUTH"] = "1"
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        app.state.max_upload_bytes = 25 * 1024 * 1024
        app.state.extraction_timeout_seconds = 30
        self.client = TestClient(app)

    def tearDown(self) -> None:
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_SKIP_AUTH", None)
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def _upload(self, filename: str, text: str) -> dict:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": (filename, text.encode("utf-8"), "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_step8_internal_golden_path_upload_to_grounded_answer_and_ui_packet(self) -> None:
        primary_upload = self._upload("primary-credit.txt", PRIMARY_CONTRACT)
        baseline_upload = self._upload("baseline-credit.txt", BASELINE_CONTRACT)

        primary_spine = build_spine_from_bronze(primary_upload["bronze"])
        baseline_spine = build_spine_from_bronze(baseline_upload["bronze"])
        evidence_packet = build_evidence_packet(primary_spine, "Which clause cites the event of default?")
        route = route_query("Which clause cites the event of default?")
        transport = FakeAiDaTransport()
        answer = generate_grounded_answer(
            query="Which clause cites the event of default?",
            evidence_packet=evidence_packet,
            route=route,
            client=AiDaProxyClient(transport),
        )
        analysis = analyze_contract_insights(
            primary_spine=primary_spine,
            baseline_spine=baseline_spine,
            query="Compare risk obligations.",
        )
        insight_packet = build_insight_answer_packet(query="Compare risk obligations.", analysis=analysis)

        self.assertEqual(primary_upload["status"], "accepted")
        self.assertEqual(primary_spine.meta["schema_version"], "contract_analyzer_spine_v1")
        self.assertFalse(evidence_packet["no_evidence"])
        self.assertEqual(route.selected_pipeline_path, "precision_evidence_pipeline")
        self.assertEqual(answer["grounding_state"], "grounded")
        self.assertTrue(answer["citations"])
        self.assertTrue(transport.requests)
        self.assertEqual(insight_packet["schema_version"], "contract_analyzer_insight_answer_packet_v1")
        self.assertEqual(insight_packet["grounding"], "grounded")
        self.assertTrue(insight_packet["findings"])
        self.assertTrue(insight_packet["citations"])
        self.assertIn("chunk_id", insight_packet["citations"][0])

    def test_step8_low_evidence_case_abstains_without_proxy_call(self) -> None:
        upload = self._upload("primary-credit.txt", PRIMARY_CONTRACT)
        spine = build_spine_from_bronze(upload["bronze"])
        evidence_packet = build_evidence_packet(spine, "quantum telemetry unrelated concept")
        route = route_query("Which clause cites quantum telemetry?")
        transport = FakeAiDaTransport()
        answer = generate_grounded_answer(
            query="Which clause cites quantum telemetry?",
            evidence_packet=evidence_packet,
            route=route,
            client=AiDaProxyClient(transport),
        )

        self.assertTrue(evidence_packet["no_evidence"])
        self.assertEqual(evidence_packet["confidence"], "low")
        self.assertEqual(answer["grounding_state"], "not_grounded")
        self.assertEqual(answer["warnings"], ["no_supporting_evidence"])
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
