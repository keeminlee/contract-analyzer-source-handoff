from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend_fastapi.main import app

# Make `caa_backend.storage.BronzeStore` importable for fixture reset.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from caa_backend.storage import BronzeStore  # noqa: E402


def _minimal_text_pdf(text: str) -> bytes:
    objects: list[bytes] = []
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
    )
    objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    chunks = [b"%PDF-1.4\n"]
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    chunks.append(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return b"".join(chunks)


class TestUploadApiContracts(unittest.TestCase):
    def setUp(self) -> None:
        # Step 3 (auth-claims-threading) added `verify_azure_token` to /uploads.
        # Existing tests bypass auth via CAA_SKIP_AUTH=1 (synthetic dev pid).
        # Singlestore migration Step 3: persist via BronzeStore inmemory shim.
        # Step 6 of singlestore migration: `app.state.bronze_storage_dir` no
        # longer exists; the `self.storage` TemporaryDirectory is now scratch
        # only (used by the docx fixture and the post-failure no-orphans
        # assertions; not bound to any app state).
        os.environ["CAA_SKIP_AUTH"] = "1"
        os.environ["CAA_STORAGE_BACKEND"] = "inmemory"
        BronzeStore.reset_inmemory()
        self.storage = TemporaryDirectory()
        app.state.max_upload_bytes = 10 * 1024 * 1024
        app.state.extraction_timeout_seconds = 30
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.storage.cleanup()
        BronzeStore.reset_inmemory()
        os.environ.pop("CAA_SKIP_AUTH", None)
        os.environ.pop("CAA_STORAGE_BACKEND", None)

    def test_health_contract(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("service"), "contract-analyzer-backend")
        self.assertIn("version", payload)

    def test_upload_accepts_supported_extension(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("sample.txt", b"Confidentiality survives termination.", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("schema_version"), "contract_analyzer_upload_v1")
        self.assertEqual(payload.get("filename"), "sample.txt")
        self.assertEqual(payload.get("extension"), ".txt")
        self.assertEqual(payload.get("status"), "accepted")
        self.assertEqual(payload.get("analysis_id"), payload.get("session_id"))
        # Step 3 (singlestore tree) — analysis_id is now UUID v4 hex (32 chars).
        # Replaces the SHA-of-content `analysis_<16hex>` scheme.
        import re
        self.assertRegex(str(payload.get("analysis_id", "")), r"^[0-9a-f]{32}$")
        bronze = payload.get("bronze", {})
        self.assertEqual(bronze.get("schema_version"), "contract_analyzer_bronze_v1")
        self.assertEqual(bronze.get("analysis_id"), payload.get("analysis_id"))
        self.assertEqual(bronze.get("source", {}).get("name"), "sample.txt")
        self.assertIn("Confidentiality survives termination.", bronze.get("extracted_text", ""))
        self.assertGreaterEqual(len(bronze.get("chunks", [])), 1)
        first_chunk = bronze["chunks"][0]
        self.assertEqual(first_chunk.get("span_start"), 0)
        self.assertGreater(first_chunk.get("span_end"), 0)
        artifact = payload.get("artifacts", {})
        self.assertEqual(artifact.get("raw_upload_retention"), "not_retained")
        # Step 3 (singlestore tree) — `bronze_path` replaced by `storage_backend`
        # because the local-fs JSON write is no longer performed.
        self.assertEqual(artifact.get("storage_backend"), "singlestore")
        self.assertNotIn("bronze_path", artifact)

    def test_upload_extracts_pdf_to_bronze(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("sample.pdf", _minimal_text_pdf("PDF contract text"), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("extension"), ".pdf")
        self.assertIn("PDF contract text", payload.get("bronze", {}).get("extracted_text", ""))

    def test_upload_extracts_docx_to_bronze(self) -> None:
        from docx import Document

        docx_path = Path(self.storage.name) / "sample.docx"
        document = Document()
        document.add_paragraph("DOCX contract text")
        document.save(docx_path)

        response = self.client.post(
            "/api/v1/uploads",
            files={
                "file": (
                    "sample.docx",
                    docx_path.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("extension"), ".docx")
        self.assertIn("DOCX contract text", payload.get("bronze", {}).get("extracted_text", ""))

    def test_upload_rejects_unsupported_extension(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("sample.exe", b"MZ", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        error = payload.get("error", {})
        self.assertEqual(error.get("code"), "unsupported_extension")
        self.assertEqual(error.get("message"), "Unsupported file extension.")
        self.assertEqual(error.get("details", {}).get("allowed_extensions"), [".txt", ".pdf", ".docx"])
        self.assertEqual(error.get("details", {}).get("received_extension"), ".exe")

    def test_upload_requires_file(self) -> None:
        response = self.client.post("/api/v1/uploads")
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "missing_upload_file")
        self.assertEqual(payload.get("error", {}).get("message"), "Upload file is required.")

    def test_upload_rejects_empty_filename(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("", b"contract text", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "empty_filename")
        self.assertEqual(payload.get("error", {}).get("message"), "Uploaded file must include a filename.")

    def test_upload_rejects_empty_payload(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "empty_upload")
        self.assertEqual(payload.get("error", {}).get("message"), "Uploaded file is empty.")

    def test_upload_rejects_oversized_payload(self) -> None:
        app.state.max_upload_bytes = 8
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("large.txt", b"this is too large", "text/plain")},
        )
        self.assertEqual(response.status_code, 413)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "upload_too_large")
        details = payload.get("error", {}).get("details", {})
        self.assertEqual(details.get("max_upload_bytes"), 8)

    def test_upload_rejects_corrupt_pdf_without_retaining_raw_file(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            files={"file": ("bad.pdf", b"%PDF-1.4 bad", "application/pdf")},
        )
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "extraction_failed")
        self.assertEqual(list(Path(self.storage.name).rglob("*")), [])

    def test_upload_rejects_extraction_timeout(self) -> None:
        def slow_extract(_: Path) -> dict:
            import time

            time.sleep(0.2)
            return {"extracted_text": "too late", "metadata": {}, "tables": []}

        app.state.extraction_timeout_seconds = 0
        with patch("backend_fastapi.extraction.extract_bronze", side_effect=slow_extract):
            response = self.client.post(
                "/api/v1/uploads",
                files={"file": ("slow.txt", b"slow text", "text/plain")},
            )
        self.assertEqual(response.status_code, 504)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "extraction_timeout")

    def test_upload_rejects_no_extractable_text(self) -> None:
        with patch(
            "backend_fastapi.extraction.extract_bronze",
            return_value={"extracted_text": "   \n\t", "metadata": {}, "tables": []},
        ):
            response = self.client.post(
                "/api/v1/uploads",
                files={"file": ("blank.txt", b"blank source", "text/plain")},
            )
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "no_extractable_text")
        self.assertEqual(payload.get("error", {}).get("message"), "Uploaded file did not produce extractable text.")
        self.assertEqual(list(Path(self.storage.name).rglob("*")), [])

    def test_upload_rejects_malformed_multipart(self) -> None:
        response = self.client.post(
            "/api/v1/uploads",
            content=b"--bad-boundary\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\n",
            headers={"Content-Type": "multipart/form-data; boundary=bad-boundary"},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload.get("error", {}).get("code"), "upload_request_invalid")
        self.assertEqual(payload.get("error", {}).get("message"), "Upload request body is malformed.")

    def test_analysis_id_is_unique_per_upload(self) -> None:
        # Renamed from `test_analysis_id_is_stable_for_repeat_uploads`. Step 3 of
        # caa-singlestore-bronze-migration switched analysis_id from SHA-of-content
        # (which collided across users) to a server-assigned UUID v4 hex. Two
        # uploads of the same content now produce DIFFERENT analysis_ids — that is
        # the binding outcome of the migration, not a regression.
        files = {"file": ("repeat.txt", b"repeatable payload", "text/plain")}
        first = self.client.post("/api/v1/uploads", files=files)
        second = self.client.post("/api/v1/uploads", files=files)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_payload = first.json()
        second_payload = second.json()
        self.assertNotEqual(first_payload.get("analysis_id"), second_payload.get("analysis_id"))
        # session_id continues to mirror analysis_id (back-compat with FE).
        self.assertEqual(first_payload.get("session_id"), first_payload.get("analysis_id"))
        self.assertEqual(second_payload.get("session_id"), second_payload.get("analysis_id"))


if __name__ == "__main__":
    unittest.main()
