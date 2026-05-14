from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from backend_fastapi.extraction import (
    EXTRACTION_TIMEOUT_SECONDS,
    MAX_UPLOAD_BYTES,
    BronzeBoundaryError,
    extract_and_store_bronze,
)
from tools.contract_insights import analyze_contract_insights
from tools.insight_packet import build_insight_answer_packet
from tools.production_spine import build_spine_from_bronze
from tools.retrieval_evidence import build_evidence_packet
from tools.semantic_router import route_query


APP_VERSION = "0.1"
SUPPORTED_EXTENSIONS = (".txt", ".pdf", ".docx")
DEFAULT_BRONZE_STORAGE_DIR = Path(__file__).resolve().parent / "runtime" / "bronze"

app = FastAPI(title="contract-analyzer-backend", version=APP_VERSION)
app.state.bronze_storage_dir = DEFAULT_BRONZE_STORAGE_DIR
app.state.max_upload_bytes = MAX_UPLOAD_BYTES
app.state.extraction_timeout_seconds = EXTRACTION_TIMEOUT_SECONDS


def _error_response(status_code: int, code: str, message: str, *, details: object | None = None) -> JSONResponse:
    payload: dict[str, object] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def build_analysis_id(filename: str, content: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(filename.strip().lower().encode("utf-8"))
    digest.update(b"\0")
    digest.update(content)
    return f"analysis_{digest.hexdigest()[:16]}"


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    for error in errors:
        if error.get("loc") == ("body", "file") and "Expected UploadFile" in str(error.get("msg", "")):
            return _error_response(400, "empty_filename", "Uploaded file must include a filename.")

    return _error_response(
        422,
        "upload_validation_error",
        "Upload request is invalid.",
        details=jsonable_encoder(errors),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 400:
        return _error_response(400, "upload_request_invalid", "Upload request body is malformed.")
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return _error_response(exc.status_code, "http_error", detail)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "contract-analyzer-backend",
        "version": APP_VERSION,
    }


@app.post("/api/v1/uploads")
async def create_upload(request: Request, file: UploadFile | None = File(default=None)) -> JSONResponse:
    if file is None:
        if request.headers.get("content-length", "0") not in ("", "0"):
            return _error_response(400, "upload_request_invalid", "Upload request body is malformed.")
        return _error_response(422, "missing_upload_file", "Upload file is required.")

    filename = (file.filename or "").strip()
    if not filename:
        return _error_response(400, "empty_filename", "Uploaded file must include a filename.")

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        return _error_response(
            400,
            "unsupported_extension",
            "Unsupported file extension.",
            details={"allowed_extensions": list(SUPPORTED_EXTENSIONS), "received_extension": extension},
        )

    content = await file.read()
    if not content:
        return _error_response(400, "empty_upload", "Uploaded file is empty.")

    analysis_id = build_analysis_id(filename, content)
    try:
        bronze_result = extract_and_store_bronze(
            filename=filename,
            content=content,
            content_type=file.content_type,
            analysis_id=analysis_id,
            storage_root=Path(app.state.bronze_storage_dir),
            max_upload_bytes=int(app.state.max_upload_bytes),
            extraction_timeout_seconds=int(app.state.extraction_timeout_seconds),
        )
    except BronzeBoundaryError as exc:
        return _error_response(exc.status_code, exc.code, exc.message, details=exc.details)

    return JSONResponse(
        status_code=200,
        content={
            "schema_version": "contract_analyzer_upload_v1",
            "analysis_id": analysis_id,
            "session_id": analysis_id,
            "filename": filename,
            "extension": extension,
            "status": "accepted",
            "bronze": bronze_result["bronze"],
            "artifacts": bronze_result["artifact"],
        },
    )


def _load_bronze(analysis_id: str, storage_root: Path) -> dict[str, Any] | None:
    bronze_path = storage_root / analysis_id / "bronze.json"
    if not bronze_path.exists():
        return None
    return json.loads(bronze_path.read_text(encoding="utf-8"))


@app.get("/api/v1/analyses/{analysis_id}/insights")
async def get_insights(request: Request, analysis_id: str, baseline_analysis_id: str | None = None) -> JSONResponse:
    storage_root = Path(app.state.bronze_storage_dir)
    primary_bronze = _load_bronze(analysis_id, storage_root)
    if primary_bronze is None:
        return _error_response(404, "analysis_not_found", f"No analysis found for id: {analysis_id}")

    primary_spine = build_spine_from_bronze(primary_bronze)

    baseline_spine = None
    if baseline_analysis_id:
        baseline_bronze = _load_bronze(baseline_analysis_id, storage_root)
        if baseline_bronze is None:
            return _error_response(404, "baseline_not_found", f"No analysis found for baseline id: {baseline_analysis_id}")
        baseline_spine = build_spine_from_bronze(baseline_bronze)

    analysis = analyze_contract_insights(primary_spine=primary_spine, baseline_spine=baseline_spine)
    packet = build_insight_answer_packet(query="", analysis=analysis)

    return JSONResponse(status_code=200, content=packet)


@app.post("/api/v1/analyses/{analysis_id}/chat")
async def chat(request: Request, analysis_id: str) -> JSONResponse:
    storage_root = Path(app.state.bronze_storage_dir)
    primary_bronze = _load_bronze(analysis_id, storage_root)
    if primary_bronze is None:
        return _error_response(404, "analysis_not_found", f"No analysis found for id: {analysis_id}")

    body = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        return _error_response(400, "missing_query", "Chat request must include a non-empty query.")

    baseline_analysis_id = body.get("baseline_analysis_id")
    primary_spine = build_spine_from_bronze(primary_bronze)

    baseline_spine = None
    if baseline_analysis_id:
        baseline_bronze = _load_bronze(baseline_analysis_id, storage_root)
        if baseline_bronze:
            baseline_spine = build_spine_from_bronze(baseline_bronze)

    route = route_query(query, comparison_baseline_resolved=baseline_spine is not None)
    evidence_packet = build_evidence_packet(primary_spine, query)
    analysis = analyze_contract_insights(primary_spine=primary_spine, baseline_spine=baseline_spine)
    packet = build_insight_answer_packet(query=query, analysis=analysis)

    return JSONResponse(status_code=200, content={
        "schema_version": "contract_analyzer_chat_response_v1",
        "analysis_id": analysis_id,
        "query": query,
        "route": route.to_dict(),
        "evidence_packet": evidence_packet,
        "answer": packet,
    })
