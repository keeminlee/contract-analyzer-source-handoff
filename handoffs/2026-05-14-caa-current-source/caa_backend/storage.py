"""CAA bronze persistence — SingleStore-backed `BronzeStore`.

Modelled verbatim on AiDa's `MUFG/aida/aid_aida-backend/history/singleStoreHistory.py`
pattern: `__init__ → _load_secrets → _get_connection → close`. Per-request
connection open/close (no pooling — explicit `# TODO(platform-pooling)` marker
mirrors AiDa's known platform-wide tech debt).

Backends
--------
- `singlestore` (default in deployed envs): real SingleStore via `mysql.connector`,
  secrets fetched from AWS Secrets Manager at `/application/aid/{env}/caa-app-secret`.
- `inmemory` (default in tests + local dev without AWS): process-local dict shim.
  Selected via `CAA_STORAGE_BACKEND=inmemory`.

Public methods
--------------
- `save_bronze(*, analysis_id, user_identifier, payload)` — insert one
  CAA_ANALYSIS row + N CAA_BRONZE_CHUNK rows.
- `load_bronze(*, analysis_id)` — return the bronze dict shape that
  `extract_and_store_bronze` returns today, plus `user_identifier`. Returns
  `None` for missing OR soft-deleted rows.
- `soft_delete(*, analysis_id, user_identifier)` — flips ACTIVE_INDICATOR to 0;
  returns True if a row was updated, False otherwise. ACL-enforced at the SQL
  layer (`USER_IDENTIFIER = %s` in WHERE).
- `save_raw(*, analysis_id, filename, content)` / `load_raw(*, analysis_id)` —
  in-memory-only raw upload byte seam for the Layer 3 source viewer. SingleStore
  mode intentionally no-ops until a blob column is approved.

NOT persisted in v1 (Locked Decision 1):
- `tables[]` and `metadata` from the bronze payload. Both are passthrough
  surfaces consumed in-process; persisting them would lock the schema to
  AiDa-uninvolved structures.

NOT included (Locked Decision 6):
- Connection pooling. Mirror AiDa's posture; revisit when AiDa adopts a pool.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory shim state (test seam; Locked Decision 7)
# ---------------------------------------------------------------------------
# Process-global. Resettable via `BronzeStore.reset_inmemory()`. Not a
# long-term abstraction; just a swap point so unit tests + local-dev runs
# without AWS credentials still work.
_inmemory_state: dict[str, dict[str, Any]] = {}
_inmemory_raw_state: dict[str, tuple[str, bytes]] = {}
_inmemory_kb_collections: dict[str, dict[str, Any]] = {}
_inmemory_kb_members: dict[str, dict[str, Any]] = {}


class CollectionNameInUse(ValueError):
    """Raised when an active user KB collection already owns a name."""


class BronzeStore:
    """Persistence layer for CAA bronze artifacts.

    Per-request lifecycle:
        store = BronzeStore()
        try:
            store.save_bronze(analysis_id=..., user_identifier=..., payload=...)
        finally:
            store.close()
    """

    def __init__(self) -> None:
        self.backend = os.getenv("CAA_STORAGE_BACKEND", "singlestore").strip().lower()
        if self.backend not in ("singlestore", "inmemory"):
            raise ValueError(
                f"CAA_STORAGE_BACKEND must be 'singlestore' or 'inmemory', got {self.backend!r}"
            )
        self.conn = None
        self.cur = None
        if self.backend == "singlestore":
            self.secret_name = (
                f"/application/aid/{os.getenv('CAA_ENV', 'dev').strip()}/caa-app-secret"
            )
            self.region = os.getenv("CAA_AWS_REGION", "us-east-1")
            self.secrets = self._load_secrets()
            # TODO(platform-pooling): mirror AiDa's no-pooling posture; revisit when
            # AiDa adopts a connection pool (per AIDA_ENTERPRISE_READINESS_NOTES_2026-05-08.md).
            self.conn = self._get_connection()
            self.cur = self.conn.cursor(dictionary=True)

    # -- Secrets / connection (verbatim AiDa pattern) ----------------------

    def _load_secrets(self) -> dict:
        # Verbatim AiDa pattern — see `singleStoreHistory.py:_load_secrets`.
        # `verify=False` mirrors AiDa's corporate-proxy posture (readiness §3, §7).
        import boto3  # local import keeps test envs that lack AWS deps importable
        client = boto3.client("secretsmanager", region_name=self.region, verify=False)
        response = client.get_secret_value(SecretId=self.secret_name)
        return json.loads(response["SecretString"])

    def _get_connection(self):
        # Verbatim AiDa pattern — see `singleStoreHistory.py:_get_connection`.
        import mysql.connector  # local import: env may not have driver in inmemory mode
        conn = mysql.connector.connect(
            host=self.secrets["singlestore_host"],
            port=int(self.secrets.get("singlestore_port", 3306)),
            user=self.secrets["singlestore_user"],
            database=self.secrets["singlestore_db"],
            password=self.secrets["singlestore_pwd"],
            allow_local_infile=True,
            use_pure=True,
        )
        return conn

    def close(self) -> None:
        """Close cursor and connection. Safe-no-op in inmemory mode."""
        try:
            if self.cur:
                self.cur.close()
        except Exception:
            pass
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass

    # -- Test seam ---------------------------------------------------------

    @staticmethod
    def reset_inmemory() -> None:
        """Clear the inmemory backend state. Intended for tests."""
        _inmemory_state.clear()
        _inmemory_raw_state.clear()
        _inmemory_kb_collections.clear()
        _inmemory_kb_members.clear()

    # -- Public CRUD -------------------------------------------------------

    def save_bronze(
        self,
        *,
        analysis_id: str,
        user_identifier: str,
        payload: dict,
        mode: str = "solo",
        comparison_context_id: str | None = None,
    ) -> str:
        """Insert one CAA_ANALYSIS row + N CAA_BRONZE_CHUNK rows.

        Returns `analysis_id` unchanged. v1 does NOT persist
        `payload["tables"]` or `payload["metadata"]`.
        """
        now = datetime.utcnow()
        analysis_mode = (mode or "solo").strip().lower()
        source = payload.get("source", {}) or {}
        extracted_text = str(payload.get("extracted_text", ""))
        chunks = payload.get("chunks", []) or []
        schema_version = str(payload.get("schema_version", "contract_analyzer_bronze_v1"))

        if self.backend == "inmemory":
            _inmemory_state[analysis_id] = {
                "analysis_id": analysis_id,
                "user_identifier": user_identifier,
                "analysis_mode": analysis_mode,
                "comparison_context_identifier": comparison_context_id,
                "schema_version": schema_version,
                "source": dict(source),
                "extracted_text": extracted_text,
                "chunks": [dict(c) for c in chunks],
                "tables": payload.get("tables", []) or [],
                "metadata": dict(payload.get("metadata", {}) or {}),
                "active_indicator": 1,
                "effective_from_timestamp": now,
                "as_of_timestamp": now,
            }
            return analysis_id

        # SingleStore path — parameterized SQL only, no f-string SQL.
        insert_analysis_sql = (
            "INSERT INTO CAA_ANALYSIS ("
            "ANALYSIS_IDENTIFIER, USER_IDENTIFIER, ANALYSIS_MODE, COMPARISON_CONTEXT_IDENTIFIER, "
            "SOURCE_FILENAME, SOURCE_EXTENSION, "
            "SOURCE_MIME_TYPE, SOURCE_SIZE_BYTES, EXTRACTED_TEXT, EXTRACTED_TEXT_CHAR_COUNT, "
            "SCHEMA_VERSION, EFFECTIVE_FROM_TIMESTAMP, ACTIVE_INDICATOR, As_of_Timestamp"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        self.cur.execute(
            insert_analysis_sql,
            (
                analysis_id,
                user_identifier,
                analysis_mode,
                comparison_context_id,
                source.get("name"),
                source.get("extension"),
                source.get("content_type"),
                source.get("size_bytes"),
                extracted_text,
                len(extracted_text),
                schema_version,
                now,
                1,
                now,
            ),
        )
        self.conn.commit()

        insert_chunk_sql = (
            "INSERT INTO CAA_BRONZE_CHUNK ("
            "CHUNK_IDENTIFIER, ANALYSIS_IDENTIFIER, CHUNK_INDEX, CHUNK_TEXT, "
            "SPAN_START, SPAN_END, EFFECTIVE_FROM_TIMESTAMP, ACTIVE_INDICATOR"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        for index, chunk in enumerate(chunks):
            chunk_id = f"{analysis_id}__{index}"
            self.cur.execute(
                insert_chunk_sql,
                (
                    chunk_id,
                    analysis_id,
                    index,
                    str(chunk.get("text", "")),
                    int(chunk.get("span_start", 0)),
                    int(chunk.get("span_end", 0)),
                    now,
                    1,
                ),
            )
            self.conn.commit()
        return analysis_id

    def load_bronze(self, *, analysis_id: str) -> dict[str, Any] | None:
        """Return the bronze dict (same shape as `extract_and_store_bronze`'s
        output) plus `user_identifier`. Filters `ACTIVE_INDICATOR = 1`.
        Returns `None` for missing OR soft-deleted rows."""
        if self.backend == "inmemory":
            row = _inmemory_state.get(analysis_id)
            if row is None or row.get("active_indicator") != 1:
                return None
            return self._row_to_payload(row, list(row.get("chunks", [])))

        select_analysis_sql = (
            "SELECT ANALYSIS_IDENTIFIER, USER_IDENTIFIER, SOURCE_FILENAME, "
            "ANALYSIS_MODE, COMPARISON_CONTEXT_IDENTIFIER, "
            "SOURCE_EXTENSION, SOURCE_MIME_TYPE, SOURCE_SIZE_BYTES, "
            "EXTRACTED_TEXT, SCHEMA_VERSION, EFFECTIVE_FROM_TIMESTAMP, "
            "ACTIVE_INDICATOR, As_of_Timestamp "
            "FROM CAA_ANALYSIS "
            "WHERE ANALYSIS_IDENTIFIER = %s AND ACTIVE_INDICATOR = 1"
        )
        self.cur.execute(select_analysis_sql, (analysis_id,))
        row = self.cur.fetchone()
        if row is None:
            return None

        select_chunks_sql = (
            "SELECT CHUNK_INDEX, CHUNK_TEXT, SPAN_START, SPAN_END "
            "FROM CAA_BRONZE_CHUNK "
            "WHERE ANALYSIS_IDENTIFIER = %s AND ACTIVE_INDICATOR = 1 "
            "ORDER BY CHUNK_INDEX ASC"
        )
        self.cur.execute(select_chunks_sql, (analysis_id,))
        chunks_rows = self.cur.fetchall() or []
        chunks = [
            {
                "chunk_id": f"bronze_chunk_{int(c['CHUNK_INDEX']) + 1}",
                "text": c["CHUNK_TEXT"],
                "span_start": int(c["SPAN_START"]),
                "span_end": int(c["SPAN_END"]),
            }
            for c in chunks_rows
        ]
        normalized = {
            "analysis_id": row["ANALYSIS_IDENTIFIER"],
            "user_identifier": row["USER_IDENTIFIER"],
            "analysis_mode": row.get("ANALYSIS_MODE") or "solo",
            "comparison_context_identifier": row.get("COMPARISON_CONTEXT_IDENTIFIER"),
            "schema_version": row["SCHEMA_VERSION"],
            "source": {
                "name": row.get("SOURCE_FILENAME"),
                "extension": row.get("SOURCE_EXTENSION"),
                "content_type": row.get("SOURCE_MIME_TYPE"),
                "size_bytes": row.get("SOURCE_SIZE_BYTES"),
            },
            "extracted_text": row.get("EXTRACTED_TEXT") or "",
            "chunks": chunks,
            # v1 does NOT persist tables / metadata; surface empty stand-ins so
            # consumers (build_spine_from_bronze) see a stable shape.
            "tables": [],
            "metadata": {},
        }
        return self._row_to_payload(normalized, chunks)

    def soft_delete(self, *, analysis_id: str, user_identifier: str) -> bool:
        """Flip ACTIVE_INDICATOR to 0 for the named analysis. ACL-enforced at
        the SQL level (`USER_IDENTIFIER = %s` in WHERE) — defense-in-depth.
        Returns True if a row was updated, False otherwise (idempotent miss).
        v1 does NOT cascade-soft-delete on chunks; reads filter through the
        parent analysis's flag."""
        if self.backend == "inmemory":
            row = _inmemory_state.get(analysis_id)
            if row is None or row.get("user_identifier") != user_identifier or row.get("active_indicator") != 1:
                return False
            row["active_indicator"] = 0
            row["as_of_timestamp"] = datetime.utcnow()
            return True

        update_sql = (
            "UPDATE CAA_ANALYSIS SET ACTIVE_INDICATOR = 0, As_of_Timestamp = %s "
            "WHERE ANALYSIS_IDENTIFIER = %s AND USER_IDENTIFIER = %s AND ACTIVE_INDICATOR = 1"
        )
        self.cur.execute(update_sql, (datetime.utcnow(), analysis_id, user_identifier))
        self.conn.commit()
        return self.cur.rowcount > 0

    def save_raw(self, *, analysis_id: str, filename: str, content: bytes) -> None:
        """Store original upload bytes for local source/PDF preview.

        The deployed SingleStore schema does not have an approved blob column in
        v1, so SingleStore mode deliberately treats this as a no-op. The API
        reports `pdf_not_stored` when `load_raw` cannot return bytes.
        """
        if self.backend == "inmemory":
            _inmemory_raw_state[analysis_id] = (filename, bytes(content))

    def load_raw(self, *, analysis_id: str) -> tuple[str, bytes] | None:
        """Return original upload bytes for local source/PDF preview."""
        if self.backend == "inmemory":
            return _inmemory_raw_state.get(analysis_id)
        return None

    # -- internals --------------------------------------------------------

    @staticmethod
    def _row_to_payload(row: dict, chunks: list[dict]) -> dict:
        """Shape a row dict into the `extract_and_store_bronze`-compatible
        return so route handlers don't need to know which backend served it."""
        extracted_text = str(row.get("extracted_text", "") or "")
        return {
            "schema_version": row.get("schema_version", "contract_analyzer_bronze_v1"),
            "analysis_id": row.get("analysis_id"),
            "session_id": row.get("analysis_id"),
            "user_identifier": row.get("user_identifier"),
            "analysis_mode": row.get("analysis_mode") or "solo",
            "mode": row.get("analysis_mode") or "solo",
            "comparison_context_identifier": row.get("comparison_context_identifier"),
            "comparison_context_id": row.get("comparison_context_identifier"),
            "source": dict(row.get("source", {}) or {}),
            "text": {
                "full": extracted_text,
                "char_count": len(extracted_text),
            },
            "extracted_text": extracted_text,
            "chunks": list(chunks),
            "tables": list(row.get("tables", []) or []),
            "metadata": dict(row.get("metadata", {}) or {}),
        }


class KbStore(BronzeStore):
    """Persistence layer for doc-to-KB collections and collection members."""

    def create_collection(self, *, user_identifier: str, collection_name: str) -> dict[str, Any]:
        now = datetime.utcnow()
        name = collection_name.strip()
        if not name:
            raise ValueError("collection_name is required")
        if self.backend == "inmemory":
            for row in _inmemory_kb_collections.values():
                if (
                    row.get("user_identifier") == user_identifier
                    and row.get("collection_name", "").lower() == name.lower()
                    and row.get("active_indicator") == 1
                ):
                    raise CollectionNameInUse(name)
            collection_id = uuid.uuid4().hex
            row = {
                "collection_id": collection_id,
                "user_identifier": user_identifier,
                "collection_name": name,
                "ingestion_status": "pending",
                "member_count": 0,
                "active_indicator": 1,
                "effective_from_timestamp": now,
                "as_of_timestamp": now,
            }
            _inmemory_kb_collections[collection_id] = row
            return self._collection_payload(row)

        collection_id = uuid.uuid4().hex
        insert_sql = (
            "INSERT INTO CAA_KB_COLLECTION ("
            "COLLECTION_IDENTIFIER, USER_IDENTIFIER, COLLECTION_NAME, INGESTION_STATUS, "
            "EFFECTIVE_FROM_TIMESTAMP, ACTIVE_INDICATOR, As_of_Timestamp"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        try:
            self.cur.execute(insert_sql, (collection_id, user_identifier, name, "pending", now, 1, now))
            self.conn.commit()
        except Exception as exc:
            if "duplicate" in str(exc).lower():
                raise CollectionNameInUse(name) from exc
            raise
        return self.get_collection(collection_id=collection_id, user_identifier=user_identifier)  # type: ignore[return-value]

    def list_collections(self, *, user_identifier: str) -> list[dict[str, Any]]:
        if self.backend == "inmemory":
            rows = [
                self._collection_payload(row)
                for row in _inmemory_kb_collections.values()
                if row.get("user_identifier") == user_identifier and row.get("active_indicator") == 1
            ]
            return sorted(rows, key=lambda row: row["collection_name"].lower())

        select_sql = (
            "SELECT c.COLLECTION_IDENTIFIER, c.USER_IDENTIFIER, c.COLLECTION_NAME, "
            "c.INGESTION_STATUS, COUNT(m.MEMBER_IDENTIFIER) AS MEMBER_COUNT, "
            "c.ACTIVE_INDICATOR, c.EFFECTIVE_FROM_TIMESTAMP, c.As_of_Timestamp "
            "FROM CAA_KB_COLLECTION c "
            "LEFT JOIN CAA_KB_MEMBER m ON c.COLLECTION_IDENTIFIER = m.COLLECTION_IDENTIFIER "
            "AND m.ACTIVE_INDICATOR = 1 "
            "WHERE c.USER_IDENTIFIER = %s AND c.ACTIVE_INDICATOR = 1 "
            "GROUP BY c.COLLECTION_IDENTIFIER, c.USER_IDENTIFIER, c.COLLECTION_NAME, "
            "c.INGESTION_STATUS, c.ACTIVE_INDICATOR, c.EFFECTIVE_FROM_TIMESTAMP, c.As_of_Timestamp "
            "ORDER BY c.COLLECTION_NAME"
        )
        self.cur.execute(select_sql, (user_identifier,))
        return [self._collection_payload(self._normalize_collection_row(row)) for row in self.cur.fetchall() or []]

    def get_collection(self, *, collection_id: str, user_identifier: str) -> dict[str, Any] | None:
        if self.backend == "inmemory":
            row = _inmemory_kb_collections.get(collection_id)
            if row is None or row.get("user_identifier") != user_identifier or row.get("active_indicator") != 1:
                return None
            payload = self._collection_payload(row)
            payload["members"] = self.get_collection_members(
                collection_id=collection_id,
                user_identifier=user_identifier,
            )
            return payload

        select_sql = (
            "SELECT COLLECTION_IDENTIFIER, USER_IDENTIFIER, COLLECTION_NAME, INGESTION_STATUS, "
            "ACTIVE_INDICATOR, EFFECTIVE_FROM_TIMESTAMP, As_of_Timestamp "
            "FROM CAA_KB_COLLECTION "
            "WHERE COLLECTION_IDENTIFIER = %s AND USER_IDENTIFIER = %s AND ACTIVE_INDICATOR = 1"
        )
        self.cur.execute(select_sql, (collection_id, user_identifier))
        row = self.cur.fetchone()
        if row is None:
            return None
        payload = self._collection_payload(self._normalize_collection_row(row))
        payload["members"] = self.get_collection_members(collection_id=collection_id, user_identifier=user_identifier)
        payload["member_count"] = len(payload["members"])
        return payload

    def soft_delete_collection(self, *, collection_id: str, user_identifier: str) -> bool:
        now = datetime.utcnow()
        if self.backend == "inmemory":
            row = _inmemory_kb_collections.get(collection_id)
            if row is None or row.get("user_identifier") != user_identifier or row.get("active_indicator") != 1:
                return False
            row["active_indicator"] = 0
            row["as_of_timestamp"] = now
            for member in _inmemory_kb_members.values():
                if member.get("collection_id") == collection_id:
                    member["active_indicator"] = 0
                    member["as_of_timestamp"] = now
            return True

        update_sql = (
            "UPDATE CAA_KB_COLLECTION SET ACTIVE_INDICATOR = 0, As_of_Timestamp = %s "
            "WHERE COLLECTION_IDENTIFIER = %s AND USER_IDENTIFIER = %s AND ACTIVE_INDICATOR = 1"
        )
        self.cur.execute(update_sql, (now, collection_id, user_identifier))
        self.conn.commit()
        return self.cur.rowcount > 0

    def add_member(
        self,
        *,
        collection_id: str,
        user_identifier: str,
        analysis_id: str,
        source_filename: str,
    ) -> dict[str, Any] | None:
        collection = self.get_collection(collection_id=collection_id, user_identifier=user_identifier)
        if collection is None:
            return None
        now = datetime.utcnow()
        member_id = uuid.uuid4().hex
        if self.backend == "inmemory":
            row = {
                "member_id": member_id,
                "collection_id": collection_id,
                "analysis_id": analysis_id,
                "user_identifier": user_identifier,
                "source_filename": source_filename,
                "ingestion_status": "pending",
                "active_indicator": 1,
                "effective_from_timestamp": now,
                "as_of_timestamp": now,
            }
            _inmemory_kb_members[member_id] = row
            _inmemory_kb_collections[collection_id]["member_count"] = len(
                [
                    item
                    for item in _inmemory_kb_members.values()
                    if item.get("collection_id") == collection_id and item.get("active_indicator") == 1
                ]
            )
            _inmemory_kb_collections[collection_id]["as_of_timestamp"] = now
            return self._member_payload(row)

        insert_sql = (
            "INSERT INTO CAA_KB_MEMBER ("
            "MEMBER_IDENTIFIER, COLLECTION_IDENTIFIER, ANALYSIS_IDENTIFIER, SOURCE_FILENAME, "
            "INGESTION_STATUS, EFFECTIVE_FROM_TIMESTAMP, ACTIVE_INDICATOR, As_of_Timestamp"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        self.cur.execute(insert_sql, (member_id, collection_id, analysis_id, source_filename, "pending", now, 1, now))
        self.conn.commit()
        return self._member_payload(
            {
                "member_id": member_id,
                "collection_id": collection_id,
                "analysis_id": analysis_id,
                "user_identifier": user_identifier,
                "source_filename": source_filename,
                "ingestion_status": "pending",
                "active_indicator": 1,
                "effective_from_timestamp": now,
                "as_of_timestamp": now,
            }
        )

    def get_collection_members(self, *, collection_id: str, user_identifier: str) -> list[dict[str, Any]]:
        if self.backend == "inmemory":
            collection = _inmemory_kb_collections.get(collection_id)
            if collection is None or collection.get("user_identifier") != user_identifier:
                return []
            rows = [
                self._member_payload(row)
                for row in _inmemory_kb_members.values()
                if row.get("collection_id") == collection_id and row.get("active_indicator") == 1
            ]
            return sorted(rows, key=lambda row: row["effective_from_timestamp"])

        select_sql = (
            "SELECT MEMBER_IDENTIFIER, COLLECTION_IDENTIFIER, ANALYSIS_IDENTIFIER, SOURCE_FILENAME, "
            "INGESTION_STATUS, ACTIVE_INDICATOR, EFFECTIVE_FROM_TIMESTAMP, As_of_Timestamp "
            "FROM CAA_KB_MEMBER "
            "WHERE COLLECTION_IDENTIFIER = %s AND ACTIVE_INDICATOR = 1 "
            "ORDER BY EFFECTIVE_FROM_TIMESTAMP"
        )
        self.cur.execute(select_sql, (collection_id,))
        return [self._member_payload(self._normalize_member_row(row, user_identifier)) for row in self.cur.fetchall() or []]

    def mark_collection_ready(self, *, collection_id: str, user_identifier: str) -> bool:
        now = datetime.utcnow()
        if self.backend == "inmemory":
            row = _inmemory_kb_collections.get(collection_id)
            if row is None or row.get("user_identifier") != user_identifier or row.get("active_indicator") != 1:
                return False
            row["ingestion_status"] = "ready"
            row["as_of_timestamp"] = now
            return True

        update_sql = (
            "UPDATE CAA_KB_COLLECTION SET INGESTION_STATUS = 'ready', As_of_Timestamp = %s "
            "WHERE COLLECTION_IDENTIFIER = %s AND USER_IDENTIFIER = %s AND ACTIVE_INDICATOR = 1"
        )
        self.cur.execute(update_sql, (now, collection_id, user_identifier))
        self.conn.commit()
        return self.cur.rowcount > 0

    @staticmethod
    def _collection_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "collection_id": row.get("collection_id"),
            "user_identifier": row.get("user_identifier"),
            "collection_name": row.get("collection_name"),
            "ingestion_status": row.get("ingestion_status") or "pending",
            "member_count": int(row.get("member_count") or 0),
            "effective_from_timestamp": str(row.get("effective_from_timestamp")),
            "as_of_timestamp": str(row.get("as_of_timestamp")),
        }

    @staticmethod
    def _member_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "member_id": row.get("member_id"),
            "collection_id": row.get("collection_id"),
            "analysis_id": row.get("analysis_id"),
            "source_filename": row.get("source_filename"),
            "ingestion_status": row.get("ingestion_status") or "pending",
            "effective_from_timestamp": str(row.get("effective_from_timestamp")),
            "as_of_timestamp": str(row.get("as_of_timestamp")),
        }

    @staticmethod
    def _normalize_collection_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "collection_id": row.get("COLLECTION_IDENTIFIER"),
            "user_identifier": row.get("USER_IDENTIFIER"),
            "collection_name": row.get("COLLECTION_NAME"),
            "ingestion_status": row.get("INGESTION_STATUS"),
            "member_count": row.get("MEMBER_COUNT") or 0,
            "active_indicator": row.get("ACTIVE_INDICATOR"),
            "effective_from_timestamp": row.get("EFFECTIVE_FROM_TIMESTAMP"),
            "as_of_timestamp": row.get("As_of_Timestamp"),
        }

    @staticmethod
    def _normalize_member_row(row: dict[str, Any], user_identifier: str) -> dict[str, Any]:
        return {
            "member_id": row.get("MEMBER_IDENTIFIER"),
            "collection_id": row.get("COLLECTION_IDENTIFIER"),
            "analysis_id": row.get("ANALYSIS_IDENTIFIER"),
            "user_identifier": user_identifier,
            "source_filename": row.get("SOURCE_FILENAME"),
            "ingestion_status": row.get("INGESTION_STATUS"),
            "active_indicator": row.get("ACTIVE_INDICATOR"),
            "effective_from_timestamp": row.get("EFFECTIVE_FROM_TIMESTAMP"),
            "as_of_timestamp": row.get("As_of_Timestamp"),
        }
