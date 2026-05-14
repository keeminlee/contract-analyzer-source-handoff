from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import jwt
import requests as http_requests
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

# ---------------------------------------------------------------------------
# Central logging — adopted verbatim from AiDa's `Aida_api_registry.py:18-35`
# pattern. Stdout-only, structured `asctime | levelname | name | message`
# format. Deployment platform captures stdout; no file rotation, no third-
# party logger backends. Field encoding inside the message string is
# `key=value` whitespace-separated (per plan Locked Decision 1).
# ---------------------------------------------------------------------------
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

root_logger = logging.getLogger()
if not root_logger.handlers:
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
else:
    root_logger.setLevel(LOG_LEVEL)
    formatter = logging.Formatter(LOG_FORMAT)
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.info("Central logging initialized at level %s", logging.getLevelName(LOG_LEVEL))

# ---------------------------------------------------------------------------
# CORS — same origin allowlist as AiDa API registry
# ---------------------------------------------------------------------------
_AIDA_ORIGINS = [
    "https://ce1aidldeapp001.mufgbank.com",
    "https://aidaapi-dev.mufgamericas.com",
    "https://aida-dev.mufgamericas.com",
    "https://aidagtw-dev.mufgamericas.com",
    "https://aidagtw-uat.mufgamericas.com",
    "https://aidaapi-uat.mufgamericas.com",
    "https://aida-uat.mufgamericas.com",
    "https://aida.mufgamericas.com",
    "https://aidagtw.mufgamericas.com",
    "http://localhost:3000",
    "http://localhost:5173",
]

# ---------------------------------------------------------------------------
# Azure AD JWT auth — lightweight token validation matching AiDa's pattern.
# JWKS endpoint is fetched once per process; kid-keyed cache avoids repeated
# network calls.  Set CAA_SKIP_AUTH=1 in local dev to bypass entirely.
# ---------------------------------------------------------------------------
_TENANT_ID = os.getenv("AZURE_TENANT_ID", "d0deeebd-f1d4-417d-9239-8dc40d182181")
_JWKS_URL = f"https://login.microsoftonline.com/{_TENANT_ID}/discovery/keys"
_ALLOWED_ISSUERS = {
    f"https://sts.windows.net/{_TENANT_ID}/",
    f"https://login.microsoftonline.com/{_TENANT_ID}/v2.0",
}
_jwks_cache: dict[str, Any] = {}


def _get_public_key(token: str):
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if kid not in _jwks_cache:
        resp = http_requests.get(_JWKS_URL, timeout=10)
        resp.raise_for_status()
        for key in resp.json().get("keys", []):
            _jwks_cache[key["kid"]] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
    return _jwks_cache.get(kid)


async def verify_azure_token(request: Request) -> dict:
    """FastAPI dependency — validates the AiDa Azure AD bearer token.
    Set CAA_SKIP_AUTH=1 to bypass in local dev."""
    if os.getenv("CAA_SKIP_AUTH") == "1":
        return {"pid": "dev", "roles": [], "groups": []}
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth_header.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")
    try:
        public_key = _get_public_key(token)
        if public_key is None:
            raise ValueError("Unknown kid")
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        if claims.get("iss") not in _ALLOWED_ISSUERS:
            raise ValueError(f"Invalid issuer: {claims.get('iss')}")
        return claims
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Unauthorized") from exc

from backend_fastapi.extraction import (
    EXTRACTION_TIMEOUT_SECONDS,
    MAX_UPLOAD_BYTES,
    BronzeBoundaryError,
    extract_and_store_bronze,
)
from caa_backend.storage import BronzeStore, CollectionNameInUse, KbStore
from tools.contract_insights import analyze_contract_insights
from tools.insight_packet import build_insight_answer_packet
from tools.production_spine import build_spine_from_bronze
from tools.retrieval_evidence import build_evidence_packet
from tools.semantic_router import route_query


APP_VERSION = "0.1"
SUPPORTED_EXTENSIONS = (".txt", ".pdf", ".docx")
VALID_ANALYSIS_MODES = {"solo", "one_to_one", "kb"}

app = FastAPI(title="contract-analyzer-backend", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_AIDA_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_client_ip(request: Request) -> str:
    """IP precedence ladder per AiDa convention (Locked Decision 7):
    `X-Real-IP` -> first hop of `X-Forwarded-For` -> `request.client.host`."""
    real_ip = request.headers.get("X-Real-IP") or request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    forwarded = request.headers.get("X-Forwarded-For") or request.headers.get("x-forwarded-for")
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _route_template(request: Request) -> str:
    """Return the matched FastAPI path template (e.g. `/api/v1/analyses/{analysis_id}/insights`)
    instead of the interpolated URL. Falls back to raw path when no route matched
    (404 / unmatched). Keeps log cardinality bounded."""
    route = request.scope.get("route")
    path_template = getattr(route, "path", None)
    if path_template:
        return path_template
    return request.url.path


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Emit one structured transport-line per request.

    Format (Locked Decision 1, key=value whitespace-separated):
        event=request request_id=<uuid> route=<template> method=<m>
        status=<code> latency_ms=<int> ip=<addr>

    Generates `request_id` server-side as UUID4 hex if no inbound
    `X-Request-ID` header (Locked Decision 2). Echoes the id on the
    response. `/health` logs at DEBUG (suppressed by default INFO
    threshold) to avoid liveness-probe flooding (Locked Decision 8).
    """
    start = time.perf_counter()
    inbound_request_id = (
        request.headers.get("X-Request-ID")
        or request.headers.get("x-request-id")
        or ""
    ).strip()
    request_id = inbound_request_id if inbound_request_id else uuid.uuid4().hex
    request.state.request_id = request_id

    response = await call_next(request)

    latency_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    route = _route_template(request)
    ip = _resolve_client_ip(request)
    level = logging.DEBUG if route == "/health" else logging.INFO
    logger.log(
        level,
        "event=request request_id=%s route=%s method=%s status=%d latency_ms=%d ip=%s",
        request_id,
        route,
        request.method,
        response.status_code,
        latency_ms,
        ip,
    )
    return response


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


def _normalize_analysis_mode(mode: str | None) -> str:
    return (mode or "solo").strip().lower()


def _validate_upload_context(
    *,
    store: KbStore,
    mode: str,
    comparison_context_id: str | None,
    user_identifier: str,
) -> JSONResponse | None:
    if mode not in VALID_ANALYSIS_MODES:
        return _error_response(
            422,
            "invalid_mode",
            "Upload mode must be one of solo, one_to_one, or kb.",
            details={"allowed_modes": sorted(VALID_ANALYSIS_MODES), "received_mode": mode},
        )
    context_id = (comparison_context_id or "").strip()
    if mode == "solo" and context_id:
        return _error_response(422, "solo_mode_no_context_allowed", "Solo mode cannot include comparison_context_id.")
    if mode == "one_to_one":
        if not context_id:
            return _error_response(422, "comparison_context_required", "one_to_one mode requires comparison_context_id.")
        baseline = store.load_bronze(analysis_id=context_id)
        if baseline is None or baseline.get("user_identifier") != user_identifier:
            return _error_response(
                422,
                "baseline_not_found_or_unauthorized",
                "comparison_context_id must reference an analysis owned by the caller.",
            )
    if mode == "kb":
        if not context_id:
            return _error_response(422, "comparison_context_required", "kb mode requires comparison_context_id.")
        collection = store.get_collection(collection_id=context_id, user_identifier=user_identifier)
        if collection is None or collection.get("ingestion_status") != "ready":
            return _error_response(
                422,
                "kb_collection_not_ready_or_unauthorized",
                "comparison_context_id must reference a ready KB collection owned by the caller.",
            )
    return None


def _context_id_for_persistence(mode: str, comparison_context_id: str | None) -> str | None:
    context_id = (comparison_context_id or "").strip()
    return context_id if mode in {"one_to_one", "kb"} else None


def _resolved_baseline_id(primary_bronze: dict[str, Any], explicit_baseline_id: str | None) -> str | None:
    if explicit_baseline_id:
        return explicit_baseline_id
    if primary_bronze.get("analysis_mode") == "one_to_one":
        return primary_bronze.get("comparison_context_identifier")
    return None


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    for error in errors:
        if error.get("loc") == ("body", "file") and "Expected UploadFile" in str(error.get("msg", "")):
            logger.warning("event=request_invalid status=400 code=empty_filename")
            return _error_response(400, "empty_filename", "Uploaded file must include a filename.")

    logger.warning("event=request_invalid status=422 code=upload_validation_error")
    return _error_response(
        422,
        "upload_validation_error",
        "Upload request is invalid.",
        details=jsonable_encoder(errors),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 400:
        logger.warning("event=request_invalid status=400 code=upload_request_invalid")
        return _error_response(400, "upload_request_invalid", "Upload request body is malformed.")
    logger.warning("event=request_invalid status=%d code=http_error", exc.status_code)
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
async def create_upload(
    request: Request,
    file: UploadFile | None = File(default=None),
    mode: str = Form(default="solo"),
    comparison_context_id: str | None = Form(default=None),
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    request.state.pid = claims.get("pid", "unknown")
    request.state.upn = claims.get("upn", "unknown")
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

    # Server-assigned UUID v4 hex. Replaces SHA-of-content (Step 3 spec) so
    # two users uploading the same file get distinct analysis_ids.
    analysis_id = uuid.uuid4().hex
    user_identifier = claims.get("pid") or "unknown"
    if user_identifier == "unknown":
        return _error_response(401, "missing_user_identifier", "User identifier missing from claims.")
    analysis_mode = _normalize_analysis_mode(mode)
    persisted_context_id = _context_id_for_persistence(analysis_mode, comparison_context_id)
    store = KbStore()
    try:
        context_error = _validate_upload_context(
            store=store,
            mode=analysis_mode,
            comparison_context_id=comparison_context_id,
            user_identifier=user_identifier,
        )
        if context_error is not None:
            return context_error
    finally:
        store.close()

    try:
        bronze_result = extract_and_store_bronze(
            filename=filename,
            content=content,
            content_type=file.content_type,
            analysis_id=analysis_id,
            max_upload_bytes=int(app.state.max_upload_bytes),
            extraction_timeout_seconds=int(app.state.extraction_timeout_seconds),
        )
    except BronzeBoundaryError as exc:
        logger.warning(
            "event=upload_failed analysis_id=%s pid=%s request_id=%s code=%s status=%d",
            analysis_id,
            getattr(request.state, "pid", "unknown"),
            getattr(request.state, "request_id", "unknown"),
            exc.code,
            exc.status_code,
        )
        return _error_response(exc.status_code, exc.code, exc.message, details=exc.details)

    # Persist to SingleStore (or in-memory shim) per Step 3.
    store = BronzeStore()
    try:
        store.save_bronze(
            analysis_id=analysis_id,
            user_identifier=user_identifier,
            payload=bronze_result["bronze"],
            mode=analysis_mode,
            comparison_context_id=persisted_context_id,
        )
        store.save_raw(
            analysis_id=analysis_id,
            filename=filename,
            content=bronze_result["raw_content"],
        )
    finally:
        store.close()

    # Audit line — emitted just before successful return so failed routes
    # (handled by Step 5 boundary-failure logging) do not produce an audit
    # success line. Filename itself is excluded per AC 7.3 (filenames can carry
    # sensitive document titles); only the extension is logged.
    logger.info(
        "event=upload analysis_id=%s pid=%s upn=%s request_id=%s filename_ext=%s size_bytes=%d",
        analysis_id,
        getattr(request.state, "pid", "unknown"),
        getattr(request.state, "upn", "unknown"),
        getattr(request.state, "request_id", "unknown"),
        extension,
        len(content),
    )
    return JSONResponse(
        status_code=200,
        content={
            "schema_version": "contract_analyzer_upload_v1",
            "analysis_id": analysis_id,
            "session_id": analysis_id,
            "filename": filename,
            "extension": extension,
            "mode": analysis_mode,
            "comparison_context_id": persisted_context_id,
            "status": "accepted",
            "bronze": bronze_result["bronze"],
            "artifacts": bronze_result["artifact"],
        },
    )


def _load_bronze(store: BronzeStore, analysis_id: str) -> dict[str, Any] | None:
    """Load a bronze record via BronzeStore. Returns None for missing or
    soft-deleted (`ACTIVE_INDICATOR = 0`) rows."""
    return store.load_bronze(analysis_id=analysis_id)


def _load_bronze_with_acl(
    store: BronzeStore,
    analysis_id: str,
    pid: str,
) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """Load + ACL-check. Same `analysis_not_found` envelope for missing and
    cross-user (Locked Decision 10 — no info leak)."""
    bronze = store.load_bronze(analysis_id=analysis_id)
    if bronze is None:
        return None, _error_response(404, "analysis_not_found", f"No analysis found for id: {analysis_id}")
    if bronze.get("user_identifier") != pid:
        return None, _error_response(404, "analysis_not_found", f"No analysis found for id: {analysis_id}")
    return bronze, None


@app.post("/api/v1/kb_collections")
async def create_kb_collection(
    request: Request,
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    # MODE IS IMMUTABLE PER ANALYSIS. Switching modes requires a fresh upload.
    # See docs/week_8/05_14_2026/PLANS/caa-doc-to-kb-comparison/2_mode-parameter-at-upload/.
    request.state.pid = claims.get("pid", "unknown")
    request.state.upn = claims.get("upn", "unknown")
    user_identifier = request.state.pid
    if user_identifier == "unknown":
        return _error_response(401, "missing_user_identifier", "User identifier missing from claims.")
    body = await request.json()
    collection_name = str(body.get("collection_name") or "").strip()
    if not collection_name:
        return _error_response(422, "missing_collection_name", "collection_name is required.")

    store = KbStore()
    try:
        try:
            collection = store.create_collection(user_identifier=user_identifier, collection_name=collection_name)
        except CollectionNameInUse:
            return _error_response(409, "collection_name_in_use", "Collection name is already in use.")
        return JSONResponse(
            status_code=201,
            content={"schema_version": "contract_analyzer_kb_collection_v1", "collection": collection},
        )
    finally:
        store.close()


@app.get("/api/v1/kb_collections")
async def list_kb_collections(
    request: Request,
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    request.state.pid = claims.get("pid", "unknown")
    store = KbStore()
    try:
        collections = store.list_collections(user_identifier=request.state.pid)
        return JSONResponse(
            status_code=200,
            content={"schema_version": "contract_analyzer_kb_collection_list_v1", "collections": collections},
        )
    finally:
        store.close()


@app.get("/api/v1/kb_collections/{collection_id}")
async def get_kb_collection(
    request: Request,
    collection_id: str,
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    request.state.pid = claims.get("pid", "unknown")
    store = KbStore()
    try:
        collection = store.get_collection(collection_id=collection_id, user_identifier=request.state.pid)
        if collection is None:
            return _error_response(404, "kb_collection_not_found", "KB collection was not found.")
        return JSONResponse(
            status_code=200,
            content={"schema_version": "contract_analyzer_kb_collection_v1", "collection": collection},
        )
    finally:
        store.close()


@app.post("/api/v1/kb_collections/{collection_id}/members")
async def add_kb_collection_member(
    request: Request,
    collection_id: str,
    file: UploadFile | None = File(default=None),
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    request.state.pid = claims.get("pid", "unknown")
    user_identifier = request.state.pid
    if file is None:
        return _error_response(422, "missing_upload_file", "Upload file is required.")
    filename = (file.filename or "").strip()
    if not filename:
        return _error_response(400, "empty_filename", "Uploaded file must include a filename.")
    extension = Path(filename).suffix.lower()
    if extension == ".zip":
        return _error_response(501, "zip_ingestion_pending_step_5", "ZIP ingestion is pending Step 5.")
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

    store = KbStore()
    try:
        collection = store.get_collection(collection_id=collection_id, user_identifier=user_identifier)
        if collection is None:
            return _error_response(404, "kb_collection_not_found", "KB collection was not found.")
        analysis_id = uuid.uuid4().hex
        try:
            bronze_result = extract_and_store_bronze(
                filename=filename,
                content=content,
                content_type=file.content_type,
                analysis_id=analysis_id,
                max_upload_bytes=int(app.state.max_upload_bytes),
                extraction_timeout_seconds=int(app.state.extraction_timeout_seconds),
            )
        except BronzeBoundaryError as exc:
            return _error_response(exc.status_code, exc.code, exc.message, details=exc.details)

        store.save_bronze(
            analysis_id=analysis_id,
            user_identifier=user_identifier,
            payload=bronze_result["bronze"],
            mode="solo",
            comparison_context_id=None,
        )
        store.save_raw(
            analysis_id=analysis_id,
            filename=filename,
            content=bronze_result["raw_content"],
        )
        member = store.add_member(
            collection_id=collection_id,
            user_identifier=user_identifier,
            analysis_id=analysis_id,
            source_filename=filename,
        )
        if member is None:
            return _error_response(404, "kb_collection_not_found", "KB collection was not found.")
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": "contract_analyzer_kb_member_ingest_v1",
                "collection_id": collection_id,
                "member_ids": [member["member_id"]],
                "members": [member],
                "status": "pending",
            },
        )
    finally:
        store.close()


@app.delete("/api/v1/kb_collections/{collection_id}")
async def delete_kb_collection(
    request: Request,
    collection_id: str,
    claims: dict = Depends(verify_azure_token),
) -> Response:
    request.state.pid = claims.get("pid", "unknown")
    store = KbStore()
    try:
        deleted = store.soft_delete_collection(collection_id=collection_id, user_identifier=request.state.pid)
        if not deleted:
            return _error_response(404, "kb_collection_not_found", "KB collection was not found.")
        return Response(status_code=204)
    finally:
        store.close()


@app.get("/api/v1/analyses/{analysis_id}/insights")
async def get_insights(
    request: Request,
    analysis_id: str,
    baseline_analysis_id: str | None = None,
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    request.state.pid = claims.get("pid", "unknown")
    request.state.upn = claims.get("upn", "unknown")
    pid = request.state.pid
    store = BronzeStore()
    try:
        primary_bronze, err = _load_bronze_with_acl(store, analysis_id, pid)
        if err is not None:
            return err

        primary_spine = build_spine_from_bronze(primary_bronze)

        resolved_baseline_id = _resolved_baseline_id(primary_bronze, baseline_analysis_id)
        baseline_spine = None
        if resolved_baseline_id:
            baseline_bronze, baseline_err = _load_bronze_with_acl(store, resolved_baseline_id, pid)
            if baseline_err is not None:
                return _error_response(404, "baseline_not_found", f"No analysis found for baseline id: {resolved_baseline_id}")
            baseline_spine = build_spine_from_bronze(baseline_bronze)

        analysis = analyze_contract_insights(primary_spine=primary_spine, baseline_spine=baseline_spine)
        packet = build_insight_answer_packet(query="", analysis=analysis)

        logger.info(
            "event=insights_read analysis_id=%s baseline_analysis_id=%s pid=%s upn=%s request_id=%s",
            analysis_id,
            resolved_baseline_id or "none",
            getattr(request.state, "pid", "unknown"),
            getattr(request.state, "upn", "unknown"),
            getattr(request.state, "request_id", "unknown"),
        )
        return JSONResponse(status_code=200, content=packet)
    finally:
        store.close()


@app.delete("/api/v1/analyses/{analysis_id}")
async def delete_analysis(
    request: Request,
    analysis_id: str,
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    """Soft-delete an analysis (flip ACTIVE_INDICATOR to 0).

    ACL: requires `claims["pid"] == row.USER_IDENTIFIER`. Idempotent — a second
    DELETE on the same id returns the same `analysis_not_found` 404 envelope.
    Cross-user delete attempts collapse to the same envelope to avoid leaking
    analysis_id existence (Locked Decision 10).

    v1 does NOT cascade-soft-delete on `CAA_BRONZE_CHUNK`. Chunks remain at
    `ACTIVE_INDICATOR = 1` but are unreachable because their parent analysis
    row is filtered out at read time. Cascade deferred to v2 — see
    `caa_backend/storage.py::soft_delete` docstring.
    """
    request.state.pid = claims.get("pid", "unknown")
    request.state.upn = claims.get("upn", "unknown")
    pid = request.state.pid
    store = BronzeStore()
    try:
        deleted = store.soft_delete(analysis_id=analysis_id, user_identifier=pid)
        if not deleted:
            # Same envelope on missing / cross-user / already-deleted — no info leak.
            return _error_response(404, "analysis_not_found", f"No analysis found for id: {analysis_id}")
        logger.info(
            "event=delete analysis_id=%s pid=%s upn=%s request_id=%s",
            analysis_id,
            getattr(request.state, "pid", "unknown"),
            getattr(request.state, "upn", "unknown"),
            getattr(request.state, "request_id", "unknown"),
        )
        return JSONResponse(
            status_code=200,
            content={"status": "deleted", "analysis_id": analysis_id},
        )
    finally:
        store.close()


@app.post("/api/v1/analyses/{analysis_id}/chat")
async def chat(
    request: Request,
    analysis_id: str,
    claims: dict = Depends(verify_azure_token),
) -> JSONResponse:
    request.state.pid = claims.get("pid", "unknown")
    request.state.upn = claims.get("upn", "unknown")
    pid = request.state.pid
    store = BronzeStore()
    try:
        primary_bronze, err = _load_bronze_with_acl(store, analysis_id, pid)
        if err is not None:
            return err

        body = await request.json()
        query = (body.get("query") or "").strip()
        if not query:
            return _error_response(400, "missing_query", "Chat request must include a non-empty query.")

        baseline_analysis_id = _resolved_baseline_id(primary_bronze, body.get("baseline_analysis_id"))
        primary_spine = build_spine_from_bronze(primary_bronze)

        baseline_spine = None
        if baseline_analysis_id:
            baseline_bronze, _baseline_err = _load_bronze_with_acl(store, baseline_analysis_id, pid)
            if baseline_bronze:
                baseline_spine = build_spine_from_bronze(baseline_bronze)

        route = route_query(query, comparison_baseline_resolved=baseline_spine is not None)
        evidence_packet = build_evidence_packet(primary_spine, query)
        analysis = analyze_contract_insights(primary_spine=primary_spine, baseline_spine=baseline_spine)
        packet = build_insight_answer_packet(query=query, analysis=analysis)

        logger.info(
            "event=chat analysis_id=%s baseline_analysis_id=%s pid=%s upn=%s request_id=%s query_len=%d query=%r",
            analysis_id,
            baseline_analysis_id or "none",
            getattr(request.state, "pid", "unknown"),
            getattr(request.state, "upn", "unknown"),
            getattr(request.state, "request_id", "unknown"),
            len(query),
            query,
        )
        return JSONResponse(status_code=200, content={
            "schema_version": "contract_analyzer_chat_response_v1",
            "analysis_id": analysis_id,
            "query": query,
            "route": route.to_dict(),
            "evidence_packet": evidence_packet,
            "answer": packet,
        })
    finally:
        store.close()
