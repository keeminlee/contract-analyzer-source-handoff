from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _extract_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf(path: Path) -> tuple[str, list[dict]]:
    """Return (full_text, page_spans) where page_spans is a list of
    {page_number (1-based), span_start, span_end} dicts that map character
    offsets in `full_text` back to their source page."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF support requires 'pypdf'. Install it with: pip install pypdf"
        ) from exc

    reader = PdfReader(str(path))
    pages_text: list[str] = []
    page_spans: list[dict] = []
    cursor = 0
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages_text.append(text)
        span_start = cursor
        span_end = cursor + len(text)
        page_spans.append({"page_number": page_num, "span_start": span_start, "span_end": span_end})
        # The joining separator "\n\n" adds 2 chars; account for that.
        cursor = span_end + 2
    return "\n\n".join(pages_text), page_spans


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "DOCX support requires 'python-docx'. Install it with: pip install python-docx"
        ) from exc

    document = Document(str(path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs)


def extract_bronze(doc_path: Path) -> dict[str, Any]:
    if not doc_path.exists():
        raise FileNotFoundError(f"Document not found: {doc_path}")

    suffix = doc_path.suffix.lower()
    page_spans: list[dict] = []
    if suffix == ".txt":
        extracted_text = _extract_txt(doc_path)
        extractor = "txt_reader"
    elif suffix == ".pdf":
        extracted_text, page_spans = _extract_pdf(doc_path)
        extractor = "pypdf"
    elif suffix == ".docx":
        extracted_text = _extract_docx(doc_path)
        extractor = "python_docx"
    else:
        raise ValueError("Unsupported file type. Use .txt, .pdf, or .docx")

    stat = doc_path.stat()
    metadata: dict[str, Any] = {
        "extractor": extractor,
        "extracted_utc": datetime.now(tz=timezone.utc).isoformat(),
        "version": "0.1",
    }
    if page_spans:
        metadata["page_spans"] = page_spans
        metadata["page_count"] = len(page_spans)
    return {
        "source": {
            "path": str(doc_path),
            "name": doc_path.name,
            "extension": suffix,
            "size_bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        },
        "extracted_text": extracted_text,
        "tables": [],
        "metadata": metadata,
    }
