from __future__ import annotations

import json
from pathlib import Path

from tools.auto_spine_builder import build_auto_spine
from tools.bronze_extractor import extract_bronze
from tools.spine_io import load_silver_spine
from tools.spine_types import SpineDoc


ROOT = Path(__file__).resolve().parents[1]
SILVER_DIR = ROOT / "docs" / "silver"
BRONZE_DIR = ROOT / "docs" / "bronze"


def _load_bronze_text(bronze_path: Path) -> str:
    payload = json.loads(bronze_path.read_text(encoding="utf-8"))
    return str(payload.get("extracted_text", ""))


def resolve_spine(
    doc_path: str | Path,
    doc_type: str,
    mode: str,
    bronze_path: str | Path | None = None,
    silver_path: str | Path | None = None,
) -> SpineDoc:
    source_doc = Path(doc_path)

    silver_candidate = Path(silver_path) if silver_path else SILVER_DIR / f"{source_doc.stem}.{doc_type}.{mode}.silver.json"
    if silver_candidate.exists():
        spine_doc = load_silver_spine(silver_candidate)
        spine_doc.spine_source = "silver"
        spine_doc.meta["resolved_from"] = str(silver_candidate)
        return spine_doc

    if bronze_path:
        bronze_candidate = Path(bronze_path)
    else:
        bronze_candidate = BRONZE_DIR / f"{source_doc.stem}.bronze.json"

    if bronze_candidate.exists():
        text = _load_bronze_text(bronze_candidate)
        spine_doc = build_auto_spine(text)
        spine_doc.meta["resolved_from"] = str(bronze_candidate)
        return spine_doc

    extracted = extract_bronze(source_doc)
    spine_doc = build_auto_spine(str(extracted.get("extracted_text", "")))
    spine_doc.meta["resolved_from"] = "extract_bronze_runtime"
    return spine_doc
