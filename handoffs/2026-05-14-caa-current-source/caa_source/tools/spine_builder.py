from __future__ import annotations

import re
from typing import Any


def detect_headings(text: str) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    pattern = re.compile(r"(?m)^(Section\s+\d+[\.:]?\s+.+)$")
    for idx, match in enumerate(pattern.finditer(text), start=1):
        headings.append(
            {
                "node_id": f"heading_{idx}",
                "type": "section_heading",
                "label": match.group(1).strip(),
                "span_start": match.start(),
                "span_end": match.end(),
                "confidence": 0.9,
                "provenance": {"tool": "detect_headings", "version": "0.1"},
            }
        )
    return headings


def detect_numbered_clauses(text: str) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    pattern = re.compile(r"(?m)^(\d+(?:\.\d+){0,3})\s+(.+)$")
    for idx, match in enumerate(pattern.finditer(text), start=1):
        clause_id = match.group(1)
        label = match.group(2).strip()
        clauses.append(
            {
                "node_id": f"clause_{clause_id.replace('.', '_')}",
                "type": "clause",
                "label": label,
                "span_start": match.start(),
                "span_end": match.end(),
                "confidence": 0.85,
                "provenance": {"tool": "detect_numbered_clauses", "version": "0.1"},
            }
        )
    return clauses


def extract_definitions(text: str) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    pattern = re.compile(r'(?m)^"([^"]+)"\s+means\s+(.+)$')
    for idx, match in enumerate(pattern.finditer(text), start=1):
        definitions.append(
            {
                "node_id": f"def_{idx}",
                "type": "definition",
                "term": match.group(1).strip(),
                "value": match.group(2).strip(),
                "span_start": match.start(),
                "span_end": match.end(),
                "confidence": 0.88,
                "provenance": {"tool": "extract_definitions", "version": "0.1"},
            }
        )
    return definitions


def build_spine(text: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "headings": detect_headings(text),
        "clauses": detect_numbered_clauses(text),
        "definitions": extract_definitions(text),
    }
