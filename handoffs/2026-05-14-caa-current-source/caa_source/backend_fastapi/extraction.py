from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
import logging
from pathlib import Path
import tempfile
from typing import Any

from tools.bronze_extractor import extract_bronze


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
EXTRACTION_TIMEOUT_SECONDS = 30
RAW_UPLOAD_RETENTION = "not_retained"
VIRUS_SCANNING = "out_of_scope_v1"

logger = logging.getLogger(__name__)


class BronzeBoundaryError(Exception):
    def __init__(self, status_code: int, code: str, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def build_text_chunks(text: str, *, target_chars: int = 1200) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    cursor = 0
    text_length = len(text)

    while cursor < text_length:
        while cursor < text_length and text[cursor].isspace():
            cursor += 1
        if cursor >= text_length:
            break

        end = min(text_length, cursor + target_chars)
        if end < text_length:
            split_at = text.rfind("\n", cursor, end)
            if split_at <= cursor:
                split_at = text.rfind(" ", cursor, end)
            if split_at > cursor:
                end = split_at

        excerpt = text[cursor:end].strip()
        if excerpt:
            chunks.append(
                {
                    "chunk_id": f"bronze_chunk_{len(chunks) + 1}",
                    "text": excerpt,
                    "span_start": cursor,
                    "span_end": end,
                }
            )
        cursor = max(end, cursor + 1)

    return chunks


def _extract_with_timeout(path: Path, timeout_seconds: int) -> dict[str, Any]:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(extract_bronze, path)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        logger.error(
            "event=boundary_failure code=extraction_timeout timeout_seconds=%d",
            timeout_seconds,
        )
        raise BronzeBoundaryError(
            504,
            "extraction_timeout",
            "Document extraction timed out.",
            details={"timeout_seconds": timeout_seconds},
        ) from exc
    except BronzeBoundaryError:
        raise
    except Exception as exc:
        logger.warning(
            "event=boundary_failure code=extraction_failed reason=%s",
            exc.__class__.__name__,
        )
        raise BronzeBoundaryError(
            422,
            "extraction_failed",
            "Document extraction failed.",
            details={"reason": exc.__class__.__name__},
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def extract_and_store_bronze(
    *,
    filename: str,
    content: bytes,
    content_type: str | None,
    analysis_id: str,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    extraction_timeout_seconds: int = EXTRACTION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Extract bronze from raw upload bytes.

    Post-SingleStore-migration: extraction is in-memory only; persistence is
    the caller's responsibility (typically `BronzeStore.save_bronze` from
    `caa_backend/main.py`). No local-filesystem write is performed.
    """
    extension = Path(filename).suffix.lower()
    size_bytes = len(content)

    if size_bytes > max_upload_bytes:
        logger.warning(
            "event=boundary_failure code=upload_too_large max_bytes=%d received_bytes=%d",
            max_upload_bytes,
            size_bytes,
        )
        raise BronzeBoundaryError(
            413,
            "upload_too_large",
            "Uploaded file exceeds the v1 size limit.",
            details={"max_upload_bytes": max_upload_bytes, "received_bytes": size_bytes},
        )

    with tempfile.TemporaryDirectory(prefix="contract_analyzer_upload_") as temp_dir:
        temp_path = Path(temp_dir) / f"source{extension}"
        temp_path.write_bytes(content)
        bronze = _extract_with_timeout(temp_path, extraction_timeout_seconds)

    extracted_text = str(bronze.get("extracted_text", ""))
    if not extracted_text.strip():
        logger.warning("event=boundary_failure code=no_extractable_text")
        raise BronzeBoundaryError(
            422,
            "no_extractable_text",
            "Uploaded file did not produce extractable text.",
        )

    chunks = build_text_chunks(extracted_text)
    extractor_metadata = dict(bronze.get("metadata", {}))
    source_metadata = {
        "name": filename,
        "extension": extension,
        "size_bytes": size_bytes,
        "content_type": content_type,
    }
    extraction_metadata = {
        **extractor_metadata,
        "timeout_seconds": extraction_timeout_seconds,
        "raw_upload_retention": RAW_UPLOAD_RETENTION,
        "virus_scanning": VIRUS_SCANNING,
        "stored_utc": datetime.now(tz=timezone.utc).isoformat(),
    }

    payload = {
        "schema_version": "contract_analyzer_bronze_v1",
        "analysis_id": analysis_id,
        "session_id": analysis_id,
        "source": source_metadata,
        "text": {
            "full": extracted_text,
            "char_count": len(extracted_text),
        },
        "extracted_text": extracted_text,
        "chunks": chunks,
        "tables": bronze.get("tables", []),
        "metadata": extraction_metadata,
    }

    return {
        "bronze": payload,
        "artifact": {
            "storage_backend": "singlestore",
            "raw_upload_retention": RAW_UPLOAD_RETENTION,
        },
        # Raw bytes passed back so the route layer can persist them for PDF serving.
        "raw_content": content,
        "raw_filename": filename,
    }
