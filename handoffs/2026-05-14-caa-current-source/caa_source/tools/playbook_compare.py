from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_baseline(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(
    classified_nodes: list[dict[str, Any]],
    baseline_path: Path,
) -> list[dict[str, Any]]:
    baseline = _load_baseline(baseline_path)
    required = set(baseline.get("required_clauses", []))
    present = {node.get("type") for node in classified_nodes}

    findings: list[dict[str, Any]] = []

    for clause_type in sorted(required - present):
        findings.append(
            {
                "finding_id": f"missing_{clause_type}",
                "status": "missing",
                "clause_type": clause_type,
                "severity": "high",
                "message": f"Required clause '{clause_type}' was not detected.",
                "citation": None,
            }
        )

    for node in classified_nodes:
        if node.get("type") not in required:
            continue
        findings.append(
            {
                "finding_id": f"present_{node.get('node_id')}",
                "status": "present",
                "clause_type": node.get("type"),
                "severity": "info",
                "message": f"Detected clause type '{node.get('type')}'.",
                "citation": {
                    "node_id": node.get("node_id"),
                    "span_start": node.get("span_start"),
                    "span_end": node.get("span_end"),
                },
            }
        )

    return findings
