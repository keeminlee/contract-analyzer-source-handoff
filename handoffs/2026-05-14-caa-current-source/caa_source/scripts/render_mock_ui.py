from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SECTION_PATTERN = re.compile(r"^Section\s+(\d+)\s+(.+)$", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"^(\d+)\.(\d+)\s+(.+)$")

SEVERITY_RANK = {
    "high": 0,
    "warn": 1,
    "warning": 1,
    "medium": 1,
    "info": 2,
    "low": 2,
}

STEP_LABELS: dict[str, tuple[str, str]] = {
    "detect_headings": ("Identify Section Headings", "Find top-level sections in the contract."),
    "detect_numbered_clauses": ("Identify Numbered Clauses", "Locate clause numbering such as 6.1 and 7.1."),
    "extract_definitions": ("Extract Definitions", "Capture defined terms that shape clause meaning."),
    "clause_classifier": ("Classify Clause Types", "Label clauses by legal function (defaults, covenants, payment, etc.)."),
    "obligation_extractor": ("Extract Contract Obligations", "Identify action-oriented obligations and responsibilities."),
    "playbook_compare": ("Compare Against Baseline Risk Policy", "Check detected clauses against baseline requirements and flag gaps."),
}

REASON_TRANSLATIONS = {
    "doc_type selected by keyword score": "Document identified as a Credit Agreement based on contractual language cues.",
    "query contains precision/evidence keywords": "Request asks for precise, citation-backed clause language.",
    "precision + compare/risk query => playbook_diff": "Comparison against risk baseline requires precision review and policy diff checks.",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_doc_type(doc_type: str) -> str:
    if not doc_type:
        return "Unknown"
    return doc_type.replace("_", " ").title()


def _format_mode(mode: str) -> str:
    if mode == "precision":
        return "Precision Review"
    if mode == "overview":
        return "Overview"
    return mode.title() if mode else "Unknown"


def _severity_key(finding: dict[str, Any]) -> tuple[int, str]:
    sev = str(finding.get("severity", "info")).lower()
    return (SEVERITY_RANK.get(sev, 99), str(finding.get("finding_id", "")))


def _sorted_chunks(retrieval: dict[str, Any], k: int = 3) -> list[dict[str, Any]]:
    chunks = list(retrieval.get("chunks", []) or [])
    chunks.sort(key=lambda item: (-float(item.get("score", 0.0)), str(item.get("chunk_id", ""))))
    return chunks[:k]


def _translate_reason(reason: str) -> str:
    lowered = reason.lower()
    for needle, replacement in REASON_TRANSLATIONS.items():
        if needle in lowered:
            return replacement
    return reason


def _iter_lines_with_spans(text: str) -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        start = offset
        offset += len(line)
        rows.append((line.rstrip("\r\n"), start, offset))
    return rows


def _build_document_map(extracted_text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None

    for raw_line, span_start, span_end in _iter_lines_with_spans(extracted_text):
        line = raw_line.strip()
        if not line:
            continue

        sec_match = SECTION_PATTERN.match(line)
        if sec_match:
            number = sec_match.group(1)
            title = sec_match.group(2).strip()
            current_section = {
                "number": number,
                "title": title,
                "node_id": f"heading_{number}",
                "span_start": span_start,
                "span_end": span_end,
                "clauses": [],
            }
            sections.append(current_section)
            continue

        clause_match = CLAUSE_PATTERN.match(line)
        if clause_match:
            major = clause_match.group(1)
            minor = clause_match.group(2)
            clause_title = clause_match.group(3).strip()
            clause = {
                "number": f"{major}.{minor}",
                "title": clause_title,
                "node_id": f"clause_{major}_{minor}",
                "span_start": span_start,
                "span_end": span_end,
            }
            if current_section and current_section["number"] == major:
                current_section["clauses"].append(clause)
            elif sections:
                sections[-1]["clauses"].append(clause)
            else:
                sections.append(
                    {
                        "number": major,
                        "title": "Unlabeled Section",
                        "node_id": f"heading_{major}",
                        "span_start": span_start,
                        "span_end": span_end,
                        "clauses": [clause],
                    }
                )

    return sections


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def _normalize_findings(evidence_packet: dict[str, Any]) -> list[dict[str, Any]]:
    findings = list(evidence_packet.get("findings", []) or [])
    findings.sort(key=_severity_key)
    return findings


def _normalize_trace(evidence_root: dict[str, Any]) -> list[dict[str, Any]]:
    dag = evidence_root.get("dag_execution", {})
    trace = list(dag.get("trace", []) or [])
    order = list(dag.get("selected_steps", []) or [])
    order_index = {step_id: idx for idx, step_id in enumerate(order)}
    trace.sort(key=lambda row: (order_index.get(str(row.get("step_id", "")), 999), str(row.get("step_id", ""))))
    return trace


def _build_highlight_sets(
    document_map: list[dict[str, Any]],
    display_chunks: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    chunk_spans = [
        (int(ch.get("span_start", -1)), int(ch.get("span_end", -1)))
        for ch in display_chunks
        if ch.get("span_start") is not None and ch.get("span_end") is not None
    ]

    citation_nodes = {str(c.get("node_id", "")) for c in citations if c.get("node_id")}
    for finding in findings:
        citation = finding.get("citation", {}) or {}
        node_id = citation.get("node_id")
        if node_id:
            citation_nodes.add(str(node_id))

    retrieved_nodes: set[str] = set()
    cited_nodes: set[str] = set(citation_nodes)
    citation_spans: list[tuple[int, int]] = []
    for citation in citations:
        if citation.get("span_start") is not None and citation.get("span_end") is not None:
            citation_spans.append((int(citation.get("span_start", -1)), int(citation.get("span_end", -1))))
    for finding in findings:
        citation = finding.get("citation", {}) or {}
        if citation.get("span_start") is not None and citation.get("span_end") is not None:
            citation_spans.append((int(citation.get("span_start", -1)), int(citation.get("span_end", -1))))

    for section in document_map:
        sec_id = str(section.get("node_id", ""))
        s_start = int(section.get("span_start", -1))
        s_end = int(section.get("span_end", -1))
        if any(_spans_overlap(s_start, s_end, c_start, c_end) for c_start, c_end in chunk_spans):
            retrieved_nodes.add(sec_id)
        if any(_spans_overlap(s_start, s_end, c_start, c_end) for c_start, c_end in citation_spans):
            cited_nodes.add(sec_id)

        for clause in section.get("clauses", []):
            clause_id = str(clause.get("node_id", ""))
            c_start = int(clause.get("span_start", -1))
            c_end = int(clause.get("span_end", -1))
            if any(_spans_overlap(c_start, c_end, rs, re) for rs, re in chunk_spans):
                retrieved_nodes.add(clause_id)
            if any(_spans_overlap(c_start, c_end, rs, re) for rs, re in citation_spans):
                cited_nodes.add(clause_id)

    return retrieved_nodes, cited_nodes


def _friendly_step(step_id: str) -> tuple[str, str]:
    return STEP_LABELS.get(step_id, (step_id.replace("_", " ").title(), "Pipeline step executed for evidence processing."))


def _severity_chip_class(severity: str) -> str:
    value = severity.lower()
    if value in {"high", "critical"}:
        return "sev-high"
    if value in {"warn", "warning", "medium"}:
        return "sev-warn"
    return "sev-info"


def _chunk_context_label(chunk: dict[str, Any], document_map: list[dict[str, Any]]) -> str:
    start = int(chunk.get("span_start", -1))
    end = int(chunk.get("span_end", -1))
    for section in document_map:
        sec_start = int(section.get("span_start", -1))
        sec_end = int(section.get("span_end", -1))
        if _spans_overlap(start, end, sec_start, sec_end):
            sec_num = section.get("number", "")
            sec_title = section.get("title", "")
            for clause in section.get("clauses", []):
                c_start = int(clause.get("span_start", -1))
                c_end = int(clause.get("span_end", -1))
                if _spans_overlap(start, end, c_start, c_end):
                    return f"Section {sec_num}.{clause.get('number', '').split('.')[-1]} ({clause.get('number', '')})"
            return f"Section {sec_num} ({sec_title})"
    return "Span-linked evidence"


def _build_answer_preview(
    findings: list[dict[str, Any]],
    display_chunks: list[dict[str, Any]],
    document_map: list[dict[str, Any]],
) -> tuple[str, str]:
    missing = [f for f in findings if str(f.get("status", "")).lower() == "missing"]
    high_risk = [f for f in findings if str(f.get("severity", "")).lower() in {"high", "critical"}]

    summary = "Events of Default language was found and verified against baseline risk checks."
    summary += f" Summary: {len(findings)} checks evaluated; {len(missing)} flagged as missing; {len(high_risk)} high-risk flags."

    citation_parts: list[str] = []
    for chunk in display_chunks:
        chunk_id = str(chunk.get("chunk_id", "(chunk)"))
        label = _chunk_context_label(chunk, document_map)
        citation_parts.append(f"{chunk_id} ({label})")

    citation_line = "Backed by citations: " + ", ".join(citation_parts) if citation_parts else "Backed by citations: none"
    return summary, citation_line


def _html_escape(value: Any) -> str:
    return html.escape(str(value))


def _chunk_clause_label(chunk: dict[str, Any], document_map: list[dict[str, Any]]) -> str:
    start = int(chunk.get("span_start", -1))
    end = int(chunk.get("span_end", -1))
    for section in document_map:
        sec_number = str(section.get("number", "")).strip()
        sec_title = str(section.get("title", "")).strip()
        for clause in section.get("clauses", []):
            c_start = int(clause.get("span_start", -1))
            c_end = int(clause.get("span_end", -1))
            if _spans_overlap(start, end, c_start, c_end):
                clause_number = str(clause.get("number", "")).strip()
                clause_title = str(clause.get("title", "")).strip()
                return f"{clause_number} {clause_title}".strip()
        sec_start = int(section.get("span_start", -1))
        sec_end = int(section.get("span_end", -1))
        if _spans_overlap(start, end, sec_start, sec_end):
            return f"Section {sec_number} {sec_title}".strip()
    return "Relevant contract passage"


def _collect_citation_spans(citations: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[tuple[int, int]]:
    spans: set[tuple[int, int]] = set()
    for citation in citations:
        if citation.get("span_start") is not None and citation.get("span_end") is not None:
            spans.add((int(citation.get("span_start", -1)), int(citation.get("span_end", -1))))
    for finding in findings:
        citation = finding.get("citation", {}) or {}
        if citation.get("span_start") is not None and citation.get("span_end") is not None:
            spans.add((int(citation.get("span_start", -1)), int(citation.get("span_end", -1))))
    return sorted(spans)


def _build_tree_model(document_map: list[dict[str, Any]], full_text: str) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for section in document_map:
        sec_number = str(section.get("number", "")).strip()
        sec_node = {
            "tree_id": f"sec_{sec_number}",
            "source_ids": [str(section.get("node_id", ""))],
            "kind": "section",
            "label": f"Section {sec_number} - {str(section.get('title', '')).strip()}",
            "span_start": int(section.get("span_start", -1)),
            "span_end": int(section.get("span_end", -1)),
            "parent": "doc_root",
            "clauses": [],
        }
        for clause in section.get("clauses", []):
            clause_num = str(clause.get("number", "")).strip()
            clause_tree_id = f"cl_{clause_num.replace('.', '_')}"
            sec_node["clauses"].append(
                {
                    "tree_id": clause_tree_id,
                    "source_ids": [str(clause.get("node_id", ""))],
                    "kind": "clause",
                    "label": f"{clause_num} {str(clause.get('title', '')).strip()}",
                    "span_start": int(clause.get("span_start", -1)),
                    "span_end": int(clause.get("span_end", -1)),
                    "parent": sec_node["tree_id"],
                }
            )
        sections.append(sec_node)

    return {
        "root": {
            "tree_id": "doc_root",
            "kind": "root",
            "label": "Contract Document",
            "span_start": 0,
            "span_end": len(full_text),
            "parent": "",
        },
        "sections": sections,
    }


def _compute_tree_touch_states(
    tree_model: dict[str, Any],
    evidence_spans: list[tuple[int, int]],
    citation_spans: list[tuple[int, int]],
) -> None:
    def overlaps(node: dict[str, Any], spans: list[tuple[int, int]]) -> bool:
        start = int(node.get("span_start", -1))
        end = int(node.get("span_end", -1))
        return any(_spans_overlap(start, end, a, b) for a, b in spans)

    for section in tree_model.get("sections", []):
        for clause in section.get("clauses", []):
            clause_evidence_used = overlaps(clause, evidence_spans)
            clause_referenced = (not clause_evidence_used) and overlaps(clause, citation_spans)
            clause_untouched = not clause_evidence_used and not clause_referenced
            clause["evidence_used"] = clause_evidence_used
            clause["referenced"] = clause_referenced
            clause["untouched"] = clause_untouched
            clause["state"] = "evidence_used" if clause_evidence_used else ("referenced" if clause_referenced else "untouched")

        has_evidence_descendant = any(bool(clause.get("evidence_used")) for clause in section.get("clauses", []))
        has_referenced_descendant = any(bool(clause.get("referenced")) for clause in section.get("clauses", []))

        section["evidence_used"] = has_evidence_descendant
        section["referenced"] = (not has_evidence_descendant) and has_referenced_descendant
        section["untouched"] = not section["evidence_used"] and not section["referenced"]
        section["state"] = "evidence_used" if section["evidence_used"] else ("referenced" if section["referenced"] else "untouched")

    root = tree_model.get("root", {})
    any_evidence_used = any(bool(sec.get("evidence_used")) for sec in tree_model.get("sections", []))
    any_referenced = any(bool(sec.get("referenced")) for sec in tree_model.get("sections", []))
    root["contains_evidence"] = any_evidence_used or any_referenced
    root["state"] = "contains_evidence" if root["contains_evidence"] else "untouched"


def _truncate_label(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _render_tree_svg(tree_model: dict[str, Any]) -> str:
    section_title_max_chars = 22
    clause_title_max_chars = 28
    max_leaves_per_section = 3

    def _section_sort_key(section: dict[str, Any]) -> tuple[int, str]:
        tree_id = str(section.get("tree_id", ""))
        number_part = tree_id.split("sec_", 1)[-1] if "sec_" in tree_id else ""
        try:
            return (int(number_part), str(section.get("label", "")))
        except ValueError:
            return (999, str(section.get("label", "")))

    sections = sorted(tree_model.get("sections", []), key=_section_sort_key)
    width = 1160
    svg_height_base = 520

    root_w = 240
    root_h = 44
    section_w = 120
    section_h = 44
    clause_w = 130
    clause_h = 36

    root_y = 80
    sections_y = 200
    clauses_y = 340
    clause_vertical_gap = 44
    clause_vertical_offset = 140

    root_center_x = width / 2
    root_x = root_center_x - (root_w / 2)

    section_count = len(sections)
    section_spacing = width / (section_count + 1) if section_count else width / 2

    section_layout: list[dict[str, Any]] = []
    max_clause_depth = 1
    for index, section in enumerate(sections, start=1):
        center_x = section_spacing * index
        clause_start_y = clauses_y
        visible_clause_count = min(max_leaves_per_section, len(section.get("clauses", [])))
        has_more_leaf = len(section.get("clauses", [])) > max_leaves_per_section
        clause_count = max(1, visible_clause_count + (1 if has_more_leaf else 0))
        max_clause_depth = max(max_clause_depth, clause_count)
        section_layout.append(
            {
                "section": section,
                "center_x": center_x,
                "section_x": center_x - (section_w / 2),
                "section_y": sections_y,
                "clause_x": center_x - (clause_w / 2),
                "clause_start_y": clause_start_y,
                "visible_clause_count": visible_clause_count,
                "has_more_leaf": has_more_leaf,
            }
        )

    dynamic_height = clauses_y + (max_clause_depth - 1) * clause_vertical_gap + clause_h + 40
    height = int(max(svg_height_base, dynamic_height))

    def node_style(node: dict[str, Any]) -> tuple[str, str, str]:
        state = str(node.get("state", "untouched"))
        if state == "evidence_used":
            return ("#e7f6ec", "#54a173", "#143f2a")
        if state == "referenced":
            return ("#edf2fb", "#6e87b5", "#243e66")
        if state == "contains_evidence":
            return ("#f2f8f4", "#9cc8ad", "#2a4b38")
        return ("#f3f5f7", "#c4ccd5", "#5b6675")

    edge_lines: list[str] = []
    node_blocks: list[str] = []

    branch_y = sections_y - 28
    if section_layout:
        min_section_x = min(float(item["center_x"]) for item in section_layout)
        max_section_x = max(float(item["center_x"]) for item in section_layout)
        edge_lines.append(
            f'<line x1="{root_center_x:.1f}" y1="{root_y + root_h:.1f}" x2="{root_center_x:.1f}" y2="{branch_y:.1f}" class="edge-spine"/>'
        )
        edge_lines.append(
            f'<line x1="{min_section_x:.1f}" y1="{branch_y:.1f}" x2="{max_section_x:.1f}" y2="{branch_y:.1f}" class="edge-spine"/>'
        )

    for item in section_layout:
        section = item["section"]
        sy = float(item["section_y"])
        sec_x = float(item["section_x"])
        center_x = float(item["center_x"])
        sec_fill, sec_stroke, sec_text = node_style(section)
        sec_edge_class = "edge-path" if section.get("evidence_used") else "edge"

        edge_lines.append(
            f'<line x1="{center_x:.1f}" y1="{branch_y:.1f}" x2="{center_x:.1f}" y2="{sy:.1f}" class="{sec_edge_class}"/>'
        )

        section_state = str(section.get("state", "untouched"))
        section_badge_text = "Evidence Used" if section_state == "evidence_used" else ("Referenced" if section_state == "referenced" else "Untouched")

        section_label = _truncate_label(str(section.get("label", "")), section_title_max_chars)
        node_blocks.append(
            "\n".join(
                [
                    f'<rect x="{sec_x:.1f}" y="{sy:.1f}" width="{section_w}" height="{section_h}" rx="8" fill="{sec_fill}" stroke="{sec_stroke}" stroke-width="1.2"/>',
                    f'<text x="{sec_x + 8:.1f}" y="{sy + 18:.1f}" class="node-title" fill="{sec_text}">{_html_escape(section_label)}</text>',
                    f'<text x="{sec_x + 8:.1f}" y="{sy + 33:.1f}" class="node-sub" fill="{sec_text}">{_html_escape(section_badge_text)}</text>',
                ]
            )
        )

        clause_x = float(item["clause_x"])
        cy = float(item["clause_start_y"])
        visible_clause_count = int(item.get("visible_clause_count", 0))
        visible_clauses = list(section.get("clauses", []))[:visible_clause_count]
        for clause in visible_clauses:
            cl_fill, cl_stroke, cl_text = node_style(clause)
            clause_edge_class = "edge-path" if clause.get("evidence_used") else "edge"
            edge_lines.append(
                f'<line x1="{center_x:.1f}" y1="{sy + section_h:.1f}" x2="{center_x:.1f}" y2="{cy:.1f}" class="{clause_edge_class}"/>'
            )

            clause_label = _truncate_label(str(clause.get("label", "")), clause_title_max_chars)
            clause_state = str(clause.get("state", "untouched"))
            clause_badge_text = "Evidence Used" if clause_state == "evidence_used" else ("Referenced" if clause_state == "referenced" else "Untouched")
            node_blocks.append(
                "\n".join(
                    [
                        f'<rect x="{clause_x:.1f}" y="{cy:.1f}" width="{clause_w}" height="{clause_h}" rx="7" fill="{cl_fill}" stroke="{cl_stroke}" stroke-width="1"/>',
                        f'<text x="{clause_x + 8:.1f}" y="{cy + 16:.1f}" class="node-title" fill="{cl_text}">{_html_escape(clause_label)}</text>',
                        f'<text x="{clause_x + 8:.1f}" y="{cy + 29:.1f}" class="node-sub" fill="{cl_text}">{_html_escape(clause_badge_text)}</text>',
                    ]
                )
            )
            cy += clause_vertical_gap

        if bool(item.get("has_more_leaf")):
            hidden_count = max(0, len(section.get("clauses", [])) - visible_clause_count)
            if hidden_count > 0:
                edge_lines.append(
                    f'<line x1="{center_x:.1f}" y1="{sy + section_h:.1f}" x2="{center_x:.1f}" y2="{cy:.1f}" class="edge"/>'
                )
                node_blocks.append(
                    "\n".join(
                        [
                            f'<rect x="{clause_x:.1f}" y="{cy:.1f}" width="{clause_w}" height="{clause_h}" rx="7" fill="#f3f5f7" stroke="#c4ccd5" stroke-width="1"/>',
                            f'<text x="{clause_x + 8:.1f}" y="{cy + 22:.1f}" class="node-title" fill="#5b6675">{_html_escape("+" + str(hidden_count) + " more")}</text>',
                        ]
                    )
                )

    root_fill, root_stroke, root_text = node_style(tree_model.get("root", {}))
    root_label = str(tree_model.get("root", {}).get("label", "Contract Document"))
    root_state = "Contains Evidence" if tree_model.get("root", {}).get("contains_evidence") else "Untouched"
    root_block = "\n".join(
        [
            f'<rect x="{root_x}" y="{root_y}" width="{root_w}" height="{root_h}" rx="9" fill="{root_fill}" stroke="{root_stroke}" stroke-width="1.4"/>',
            f'<text x="{root_x + 12}" y="{root_y + 18}" class="node-title" fill="{root_text}">{_html_escape(root_label)}</text>',
            f'<text x="{root_x + 12}" y="{root_y + 32}" class="node-sub" fill="{root_text}">{_html_escape(root_state)}</text>',
        ]
    )

    return "".join(
        [
            f'<svg class="tree-svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Contract map tree">',
            '<defs><style>.edge{stroke:#c8d0da;stroke-width:1.2;fill:none}.edge-path{stroke:#4f9c70;stroke-width:2.0;fill:none}.edge-spine{stroke:#d6dde5;stroke-width:1.1;fill:none}.node-title{font-family:Segoe UI,Trebuchet MS,Arial,sans-serif;font-size:12px;font-weight:600}.node-sub{font-family:Segoe UI,Trebuchet MS,Arial,sans-serif;font-size:11px}</style></defs>',
            "".join(edge_lines),
            root_block,
            "".join(node_blocks),
            '</svg>',
        ]
    )


def _render_tree_section(tree_svg: str) -> str:
    return "\n".join(
        [
            '<section class="row card tree-card">',
            '<h2>Contract Map (Nodes Touched)</h2>',
            '<p class="muted">We map the contract into sections and clauses automatically. Highlighted nodes show the exact clauses used to generate this answer.</p>',
            '<p class="muted">This map is built automatically from the raw document (no manual tagging). Highlighted nodes show exactly what the model read to produce the answer.</p>',
            '<div class="tree-legend">',
            '<span class="legend-item"><span class="legend-swatch sw-ev"></span>Evidence Used (green): used in response generation</span>',
            '<span class="legend-item"><span class="legend-swatch sw-ref"></span>Referenced (blue): cited in findings</span>',
            '<span class="legend-item"><span class="legend-swatch sw-ut"></span>Untouched (gray): present but not used</span>',
            '<span class="legend-item"><span class="legend-line"></span>Evidence Path: root to evidence-used nodes</span>',
            '</div>',
            '<div class="tree-wrap">',
            tree_svg,
            '</div>',
            '</section>',
        ]
    )


def _render_html(
    bronze: dict[str, Any],
    evidence_root: dict[str, Any],
    out_path: Path,
    print_mode: bool,
    no_timestamp: bool,
    tree_only: bool,
) -> str:
    evidence_packet = evidence_root.get("evidence_packet", {}) or {}
    decision = evidence_root.get("orchestrator_decision", {}) or {}

    query = evidence_root.get("query") or decision.get("query") or "(no query provided)"
    doc_type = evidence_root.get("doc_type") or decision.get("doc_type") or evidence_packet.get("doc_type") or "unknown"
    mode = evidence_root.get("mode") or decision.get("mode") or evidence_packet.get("mode") or "unknown"
    confidence = float(decision.get("confidence", 0.0) or 0.0)

    retrieval = evidence_packet.get("retrieval") or decision.get("retrieval") or {}
    display_chunks = _sorted_chunks(retrieval, k=3)
    findings = _normalize_findings(evidence_packet)
    trace = _normalize_trace(evidence_root)
    citations = list(evidence_packet.get("citations", []) or [])

    bronze_text = bronze.get("extracted_text", "")
    document_map = _build_document_map(bronze_text)
    retrieved_nodes, cited_nodes = _build_highlight_sets(document_map, display_chunks, citations, findings)
    evidence_spans = [
        (int(ch.get("span_start", -1)), int(ch.get("span_end", -1)))
        for ch in display_chunks
        if ch.get("span_start") is not None and ch.get("span_end") is not None
    ]
    citation_spans = _collect_citation_spans(citations, findings)
    tree_model = _build_tree_model(document_map, bronze_text)
    _compute_tree_touch_states(tree_model, evidence_spans=evidence_spans, citation_spans=citation_spans)
    tree_svg = _render_tree_svg(tree_model)
    tree_section_html = _render_tree_section(tree_svg)

    translated_reasons = [_translate_reason(str(reason)) for reason in list(decision.get("reasons", []) or [])]

    answer_summary, answer_citations = _build_answer_preview(findings, display_chunks, document_map)

    scenario = str(evidence_root.get("scenario", "ad_hoc"))
    source = bronze.get("source", {}) or {}
    doc_name = source.get("name") or Path(str(evidence_root.get("requested_doc", "document"))).name

    timestamp_text = "Timestamp omitted (--no-timestamp)" if no_timestamp else datetime.now(timezone.utc).isoformat(timespec="seconds")

    body_class = "print-mode" if print_mode else ""

    section_rows: list[str] = []
    for section in document_map:
        sec_node_id = str(section.get("node_id", ""))
        sec_classes = ["map-section"]
        badges: list[str] = []
        if sec_node_id in retrieved_nodes:
            sec_classes.append("is-retrieved")
            badges.append('<span class="badge badge-ev">Evidence Used</span>')
        if sec_node_id in cited_nodes:
            badges.append('<span class="badge badge-ref">Referenced</span>')

        section_rows.append(
            "".join(
                [
                    f'<div class="{" ".join(sec_classes)}">',
                    f"<div><strong>Section { _html_escape(section.get('number', '')) } - { _html_escape(section.get('title', '')) }</strong></div>",
                    f'<div class="map-badges">{"".join(badges)}</div>',
                ]
            )
        )

        for clause in section.get("clauses", [])[:2]:
            clause_id = str(clause.get("node_id", ""))
            clause_classes = ["map-clause"]
            if clause_id in retrieved_nodes:
                clause_classes.append("is-retrieved")

            section_rows.append(
                "".join(
                    [
                        f'<div class="{" ".join(clause_classes)}">',
                        f"<span>{ _html_escape(clause.get('number', '')) } { _html_escape(clause.get('title', '')) }</span>",
                        "</div>",
                    ]
                )
            )

        section_rows.append("</div>")

    evidence_rows: list[str] = []
    for chunk in display_chunks:
        node_ids = ", ".join(str(node) for node in list(chunk.get("node_ids", []) or [])) or "(none)"
        clause_label = _chunk_clause_label(chunk, document_map)
        node_primary = str(list(chunk.get("node_ids", []) or ["(none)"])[0])
        evidence_rows.append(
            "\n".join(
                [
                    '<article class="chunk-card">',
                    '<div class="chunk-anchor">',
                    f"<div><strong>Clause:</strong> {_html_escape(clause_label)}</div>",
                    f"<div><strong>Span:</strong> {_html_escape(chunk.get('span_start', ''))}-{_html_escape(chunk.get('span_end', ''))}</div>",
                    f"<div><strong>Node:</strong> {_html_escape(node_primary)}</div>",
                    "</div>",
                    f"<p class=\"excerpt\">{_html_escape(chunk.get('excerpt', ''))}</p>",
                    "<div class=\"chunk-meta\">",
                    f"<span class=\"chip\">all nodes: {_html_escape(node_ids)}</span>",
                    f"<span class=\"diag-meta muted\">chunk_id: {_html_escape(chunk.get('chunk_id', 'chunk'))} | score: {_html_escape(chunk.get('score', 0))}</span>",
                    "</div>",
                    "</article>",
                ]
            )
        )

    step_rows: list[str] = []
    for idx, step in enumerate(trace, start=1):
        step_id = str(step.get("step_id", ""))
        label, subtitle = _friendly_step(step_id)
        step_rows.append(
            "\n".join(
                [
                    '<li class="step">',
                    f"<div class=\"step-index\">{idx}</div>",
                    "<div>",
                    f"<div><strong>{_html_escape(label)}</strong></div>",
                    f"<div class=\"muted\">{_html_escape(subtitle)}</div>",
                    f"<div class=\"muted\">step_id: {_html_escape(step_id)} | result_count: {_html_escape(step.get('result_count', 0))}</div>",
                    "</div>",
                    "</li>",
                ]
            )
        )

    finding_rows: list[str] = []
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        citation = finding.get("citation", {}) or {}
        finding_rows.append(
            "\n".join(
                [
                    '<article class="finding">',
                    f"<span class=\"severity {_severity_chip_class(severity)}\">{_html_escape(severity.upper())}</span>",
                    f"<div class=\"finding-msg\">{_html_escape(finding.get('message', ''))}</div>",
                    f"<div class=\"muted\">citation: {_html_escape(citation.get('node_id', '(none)'))} | span {_html_escape(citation.get('span_start', ''))}-{_html_escape(citation.get('span_end', ''))}</div>",
                    "</article>",
                ]
            )
        )

    why_list = "".join(f"<li>{_html_escape(reason)}</li>" for reason in translated_reasons)
    section_html = "".join(section_rows) if section_rows else '<p class="muted">No sections detected.</p>'
    evidence_html = "".join(evidence_rows) if evidence_rows else '<p class="muted">No evidence passages available.</p>'
    step_html = "".join(step_rows) if step_rows else '<li class="muted">No step trace available.</li>'
    findings_html = "".join(finding_rows) if finding_rows else '<p class="muted">No findings available.</p>'

    tree_only_content = "\n".join(
        [
            '<section class="row card">',
            '<h2>Contract Analyst Agent - Evidence View</h2>',
            f'<p class="muted">Document Type: {_html_escape(_format_doc_type(str(doc_type)))} | Analysis Mode: {_html_escape(_format_mode(str(mode)))} | Confidence: {_html_escape(f"{confidence * 100:.0f}%")}</p>',
            '</section>',
            tree_section_html,
        ]
    )

    full_content = f"""
        <section class=\"grid3\">
            <article class=\"card\">
                <h2>Ask and Routing</h2>
                <div class=\"answer-preview\">
                    <div class=\"headline\">Answer Preview</div>
                    <p>{_html_escape(answer_summary)}</p>
                    <p class=\"muted\">{_html_escape(answer_citations)}</p>
                </div>
                <h3>Query</h3>
                <p>{_html_escape(query)}</p>
                <h3>How the system interprets the request</h3>
                <p class=\"muted\">Determine contract type, choose review depth, and target relevant sections.</p>
                <h3>Why this path was chosen</h3>
                <ul>
                    {why_list}
                </ul>
                <h3>Selected Steps</h3>
                <p class=\"muted\">{_html_escape(' -> '.join(list(decision.get('selected_steps', []) or [])))}</p>
            </article>

            <article class=\"card\">
                <h2>Document Map</h2>
                <p class=\"muted\">Contracts are mapped into sections and clauses before analysis. Highlighted rows indicate evidence-used and referenced text.</p>
                {section_html}
            </article>

            <article class=\"card\">
                <h2>Evidence Used (Top 3)</h2>
                <p class=\"muted\">Top evidence passages selected from the contract map and used to generate the answer.</p>
                {evidence_html}
            </article>
        </section>

        {tree_section_html}

        <section class=\"row card\">
            <h2>DAG Execution Trace</h2>
            <p class=\"muted\">Transparent, reproducible sequence of analysis steps.</p>
            <ol class=\"stepper\">
                {step_html}
            </ol>
        </section>

        <section class=\"row card\">
            <h2>Findings</h2>
            <p class=\"muted\">Severity-tagged findings with citation references.</p>
            <div class=\"findings\">
                {findings_html}
            </div>
            <details>
                <summary>View raw artifacts</summary>
                <h3>Evidence Packet (raw)</h3>
                <pre>{_html_escape(json.dumps(evidence_root, indent=2, sort_keys=True))}</pre>
                <h3>Bronze Extraction (raw)</h3>
                <pre>{_html_escape(json.dumps(bronze, indent=2, sort_keys=True))}</pre>
            </details>
        </section>
        """

    html_text = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Contract Analyst Agent - Evidence View</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --card: #ffffff;
      --ink: #17222f;
      --muted: #556476;
      --line: #d8e0e8;
      --accent: #0a5c7a;
      --accent-soft: #d9eef5;
      --ok: #246b4a;
      --warn: #9a6700;
      --high: #a72b2b;
      --font: "Segoe UI", "Trebuchet MS", "Arial", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: radial-gradient(circle at 15% 5%, #e7f3fa 0%, var(--bg) 44%); color: var(--ink); font-family: var(--font); }}
    .page {{ max-width: 1320px; margin: 0 auto; padding: 18px; }}
    .header {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: 0 10px 26px rgba(23, 34, 47, 0.06); }}
    .title {{ font-size: 28px; margin: 0; letter-spacing: 0.2px; }}
    .subtitle {{ margin: 4px 0 0; color: var(--muted); }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .badge {{ border-radius: 999px; font-size: 12px; padding: 4px 10px; font-weight: 600; border: 1px solid transparent; }}
    .badge-type {{ background: #edf5ff; color: #184b85; border-color: #b7cff0; }}
    .badge-mode {{ background: #ecf8ef; color: #1a6c3f; border-color: #badfca; }}
    .badge-conf {{ background: #fff5e9; color: #8f4e00; border-color: #e8c8a2; }}
    .badge-ev {{ background: #e6f5eb; color: #1f6c45; border-color: #b9dfc8; }}
    .badge-ref {{ background: #edf0f8; color: #35507f; border-color: #c8d2e8; }}

    .callouts {{ margin-top: 12px; display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 10px; }}
    .callout {{ border: 1px solid var(--line); background: #fbfdff; border-radius: 10px; padding: 10px 12px; }}
    .callout strong {{ display: block; font-size: 13px; }}
    .callout span {{ color: var(--muted); font-size: 12px; }}

    .grid3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin-top: 14px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }}
    h2 {{ margin: 0 0 10px; font-size: 18px; }}
    h3 {{ margin: 14px 0 8px; font-size: 15px; }}
    p {{ margin: 0 0 10px; line-height: 1.45; }}
    ul {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 0 0 6px; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .chip {{ border: 1px solid var(--line); border-radius: 6px; padding: 2px 8px; font-size: 12px; background: #f8fafc; }}

    .answer-preview {{ background: linear-gradient(125deg, #f9fcff 0%, #edf6ff 100%); border: 1px solid #c8d9ec; border-radius: 10px; padding: 12px; margin-bottom: 12px; }}
    .answer-preview .headline {{ font-weight: 700; margin-bottom: 6px; }}

    .map-section {{ border-top: 1px solid #eff2f6; padding-top: 8px; margin-top: 8px; }}
    .map-section:first-child {{ border-top: 0; margin-top: 0; padding-top: 0; }}
    .map-clause {{ margin-left: 12px; display: block; color: #2e3e52; padding: 4px 0; }}
    .map-badges {{ display: inline-flex; gap: 6px; flex-wrap: wrap; }}
    .is-retrieved {{ background: #f3fbf5; border-radius: 8px; padding: 6px 8px; }}

        .chunk-card {{ border: 1px solid #ccd8e5; border-radius: 10px; padding: 12px; margin-bottom: 14px; background: #fdfefe; }}
    .chunk-card:last-child {{ margin-bottom: 0; }}
        .chunk-anchor {{ display: grid; gap: 3px; margin-bottom: 8px; font-size: 13px; color: #1e3244; }}
        .excerpt {{
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
    .chunk-meta {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .diag-meta {{ font-size: 11px; }}

    .row {{ margin-top: 14px; }}
    .stepper {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }}
    .step {{ display: grid; grid-template-columns: 34px 1fr; gap: 10px; align-items: start; border: 1px solid var(--line); border-radius: 10px; padding: 10px; background: #fbfdff; }}
    .step-index {{ width: 28px; height: 28px; border-radius: 50%; background: var(--accent-soft); color: var(--accent); display: flex; align-items: center; justify-content: center; font-weight: 700; }}

    .findings {{ display: grid; gap: 8px; }}
    .finding {{ border: 1px solid var(--line); border-radius: 10px; padding: 10px; background: #fff; }}
    .finding-msg {{ margin-top: 6px; margin-bottom: 5px; }}
    .severity {{ border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 700; }}
    .sev-info {{ background: #ecf7f0; color: var(--ok); }}
    .sev-warn {{ background: #fff5e8; color: var(--warn); }}
    .sev-high {{ background: #feeced; color: var(--high); }}

    details {{ margin-top: 10px; }}
    details summary {{ cursor: pointer; color: #1d4f80; font-weight: 600; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f7f9fc; border: 1px solid var(--line); border-radius: 8px; padding: 10px; max-height: 260px; overflow: auto; }}
    .footer {{ margin-top: 14px; color: var(--muted); font-size: 12px; border-top: 1px solid var(--line); padding-top: 10px; }}

    .print-mode .page {{ max-width: 1280px; padding: 10px; }}
    .print-mode .header, .print-mode .card {{ border-radius: 8px; }}
    .print-mode .grid3 {{ gap: 10px; }}
    .print-mode body {{ overflow: hidden; }}
    .print-mode .excerpt {{ -webkit-line-clamp: 2; }}
    .print-mode .diag-meta {{ display: none; }}

    .tree-card {{ overflow-x: auto; }}
    .tree-wrap {{ border: 1px solid #d8e0e8; border-radius: 10px; background: #fbfdff; padding: 8px; overflow: auto; }}
    .tree-legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 10px; }}
    .legend-item {{ font-size: 12px; color: #425365; display: inline-flex; align-items: center; gap: 6px; }}
    .legend-swatch {{ width: 12px; height: 12px; border-radius: 3px; border: 1px solid #b9c2cc; display: inline-block; }}
    .sw-ev {{ background: #e7f6ec; border-color: #54a173; }}
    .sw-ref {{ background: #edf2fb; border-color: #6e87b5; }}
    .sw-ut {{ background: #f3f5f7; border-color: #c4ccd5; }}
    .legend-line {{ width: 16px; height: 0; border-top: 2px solid #4f9c70; display: inline-block; }}

    @media (max-width: 1120px) {{
      .grid3 {{ grid-template-columns: 1fr; }}
      .callouts {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body class=\"{body_class}\">
  <main class=\"page\">
    <section class=\"header\">
      <h1 class=\"title\">Contract Analyst Agent - Evidence View</h1>
      <p class=\"subtitle\">Clause-by-Clause Contract Intelligence | Traceable, Structured, and Enterprise-Ready</p>
      <div class=\"meta\">
        <span class=\"badge badge-type\">Document Type: {_html_escape(_format_doc_type(str(doc_type)))}</span>
        <span class=\"badge badge-mode\">Analysis Mode: {_html_escape(_format_mode(str(mode)))}</span>
        <span class=\"badge badge-conf\">Confidence: {_html_escape(f'{confidence * 100:.0f}%')}</span>
      </div>
      <div class=\"callouts\">
        <div class=\"callout\"><strong>Structured reading</strong><span>Mapped into sections + clauses (like a human reviewer).</span></div>
        <div class=\"callout\"><strong>Evidence-first</strong><span>Only {_html_escape(len(display_chunks))} evidence snippets used for this answer.</span></div>
        <div class=\"callout\"><strong>Traceable</strong><span>Every finding links to an exact clause span.</span></div>
      </div>
    </section>

        {tree_only_content if tree_only else full_content}

    <footer class=\"footer\">
      <div>No citation, no answer.</div>
      <div>Scenario: {_html_escape(scenario)} | Document: {_html_escape(doc_name)} | Generated: {_html_escape(timestamp_text)}</div>
      <div>Bronze -> Structure -> Evidence -> Answer</div>
    </footer>
  </main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8")
    return html_text


def render_report(
    bronze_path: Path,
    evidence_path: Path,
    out_path: Path,
    print_mode: bool = False,
    no_timestamp: bool = False,
    tree_only: bool = False,
) -> dict[str, Any]:
    bronze = _load_json(bronze_path)
    evidence_root = _load_json(evidence_path)
    html_text = _render_html(
        bronze,
        evidence_root,
        out_path,
        print_mode=print_mode,
        no_timestamp=no_timestamp,
        tree_only=tree_only,
    )
    return {
        "out_path": str(out_path),
        "scenario": evidence_root.get("scenario", "ad_hoc"),
        "print_mode": print_mode,
        "no_timestamp": no_timestamp,
        "tree_only": tree_only,
        "bytes": len(html_text.encode("utf-8")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render evidence-first mock UI HTML from bronze + evidence packet")
    parser.add_argument("--bronze", required=True, help="Path to bronze extraction JSON")
    parser.add_argument("--evidence", required=True, help="Path to evidence packet JSON")
    parser.add_argument("--out", required=True, help="Output HTML path")
    parser.add_argument("--print", dest="print_mode", action="store_true", help="Enable screenshot-optimized print layout")
    parser.add_argument("--tree-only", action="store_true", help="Render only the Contract Map (Nodes Touched) page")
    parser.add_argument("--no-timestamp", action="store_true", help="Omit runtime timestamp for deterministic hashing")
    args = parser.parse_args()

    result = render_report(
        bronze_path=Path(args.bronze),
        evidence_path=Path(args.evidence),
        out_path=Path(args.out),
        print_mode=args.print_mode,
        no_timestamp=args.no_timestamp,
        tree_only=args.tree_only,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
