from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from tools.clause_classifier import classify
from tools.obligation_extractor import extract as extract_obligations
from tools.playbook_compare import compare
from tools.spine_builder import (
    detect_headings,
    detect_numbered_clauses,
    extract_definitions,
)


@dataclass(frozen=True)
class ToolBinding:
    output_key: str
    runner: Callable[[dict[str, Any]], Any]


def _candidate_nodes(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [*context.get("headings", []), *context.get("clauses", [])]


TOOL_REGISTRY: dict[str, ToolBinding] = {
    "spine_builder.detect_headings": ToolBinding(
        output_key="headings",
        runner=lambda context: detect_headings(context["text"]),
    ),
    "spine_builder.detect_numbered_clauses": ToolBinding(
        output_key="clauses",
        runner=lambda context: detect_numbered_clauses(context["text"]),
    ),
    "spine_builder.extract_definitions": ToolBinding(
        output_key="definitions",
        runner=lambda context: extract_definitions(context["text"]),
    ),
    "clause_classifier.classify": ToolBinding(
        output_key="classified_nodes",
        runner=lambda context: classify(_candidate_nodes(context)),
    ),
    "obligation_extractor.extract": ToolBinding(
        output_key="obligations",
        runner=lambda context: extract_obligations(
            context.get("classified_nodes", []),
            context["text"],
        ),
    ),
    "playbook_compare.compare": ToolBinding(
        output_key="findings",
        runner=lambda context: compare(
            context.get("classified_nodes", []),
            context["baseline_path"],
        ),
    ),
}


def load_template(template_path: Path) -> dict[str, Any]:
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    return yaml.safe_load(template_path.read_text(encoding="utf-8"))


def run_template_dag(
    template_path: Path,
    mode: str,
    initial_context: dict[str, Any],
    requested_steps: list[str] | None = None,
) -> dict[str, Any]:
    template = load_template(template_path)
    routing = template.get("routing", {})

    if mode not in routing:
        raise ValueError(f"Mode '{mode}' is not defined in template routing")

    template_route_steps = routing[mode].get("execute", [])
    selected_steps = requested_steps if requested_steps else template_route_steps
    nodes = template.get("nodes", [])
    nodes_by_id = {node["id"]: node for node in nodes}

    context: dict[str, Any] = dict(initial_context)
    visited: set[str] = set()
    trace: list[dict[str, Any]] = []

    def execute_step(step_id: str) -> None:
        if step_id in visited:
            return

        if step_id not in nodes_by_id:
            raise ValueError(f"Unknown DAG step: {step_id}")

        node = nodes_by_id[step_id]
        for dep in node.get("depends_on", []):
            execute_step(dep)

        tool_name = node.get("tool")
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"No tool binding found for: {tool_name}")

        binding = TOOL_REGISTRY[tool_name]
        result = binding.runner(context)
        context[binding.output_key] = result
        visited.add(step_id)

        result_count = len(result) if isinstance(result, list) else 1
        trace.append(
            {
                "step_id": step_id,
                "tool": tool_name,
                "output_key": binding.output_key,
                "depends_on": node.get("depends_on", []),
                "result_count": result_count,
            }
        )

    for step in selected_steps:
        execute_step(step)

    return {
        "template_id": template.get("template_id"),
        "doc_type": template.get("doc_type"),
        "mode": mode,
        "selected_steps": selected_steps,
        "template_route_steps": template_route_steps,
        "citation_policy": template.get("citation_policy", {}),
        "executed_steps": [item["step_id"] for item in trace],
        "trace": trace,
        "context": context,
    }
