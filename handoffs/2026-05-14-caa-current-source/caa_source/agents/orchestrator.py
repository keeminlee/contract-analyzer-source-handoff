from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.bronze_extractor import extract_bronze
from tools.dag_runner import run_template_dag, load_template
from tools.mock_router import decide_mock_flow, choose_subtree_steps, resolve_dynamic_retrieval

from agents.overview_agent import run_overview
from agents.precision_agent import run_precision

PRECEDENT_DIR = ROOT / "precedent_store"
TEMPLATES_DIR = ROOT / "templates"
BRONZE_DIR = ROOT / "docs" / "bronze"
SILVER_DIR = ROOT / "docs" / "silver"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _select_baseline(doc_type: str) -> Path:
    baseline = PRECEDENT_DIR / f"{doc_type}_baseline.json"
    if not baseline.exists():
        raise FileNotFoundError(f"No baseline found for doc type: {doc_type}")
    return baseline


def _persist_bronze_artifact(doc_path: Path, bronze: dict[str, Any]) -> Path:
    bronze_path = BRONZE_DIR / f"{doc_path.stem}.bronze.json"
    _write_json(bronze_path, bronze)
    return bronze_path


def _persist_silver_artifact(
    doc_path: Path,
    mode: str,
    doc_type: str,
    spine: dict[str, list[dict[str, Any]]],
    classified_nodes: list[dict[str, Any]],
    bronze_path: Path,
    dag_execution: dict[str, Any],
    evidence_packet: dict[str, Any],
    orchestrator_decision: dict[str, Any],
) -> Path:
    silver_payload = {
        "document": {
            "path": str(doc_path),
            "doc_type": doc_type,
            "mode": mode,
            "processed_utc": datetime.now(tz=timezone.utc).isoformat(),
        },
        "bronze_artifact": str(bronze_path),
        "spine": spine,
        "classified_nodes": classified_nodes,
        "dag_execution": dag_execution,
        "evidence_packet": evidence_packet,
        "orchestrator_decision": orchestrator_decision,
    }
    silver_path = SILVER_DIR / f"{doc_path.stem}.{doc_type}.{mode}.silver.json"
    _write_json(silver_path, silver_payload)
    return silver_path


def _select_template(doc_type: str) -> Path:
    template_path = TEMPLATES_DIR / f"{doc_type}.yml"
    if not template_path.exists():
        raise FileNotFoundError(f"No template found for doc type: {doc_type}")
    return template_path


def _build_evidence_packet(
    mode: str,
    doc_type: str,
    dag_execution: dict[str, Any],
    findings: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
    classified_nodes: list[dict[str, Any]],
    retrieval: dict[str, Any],
) -> dict[str, Any]:
    cited_findings = [
        finding
        for finding in findings
        if isinstance(finding.get("citation"), dict)
        and all(key in finding["citation"] for key in ("node_id", "span_start", "span_end"))
    ]
    top_classified = sorted(
        classified_nodes,
        key=lambda node: float(node.get("confidence", 0.0)),
        reverse=True,
    )[:8]

    return {
        "mode": mode,
        "doc_type": doc_type,
        "executed_steps": dag_execution.get("executed_steps", []),
        "citations": [finding["citation"] for finding in cited_findings],
        "findings": cited_findings,
        "obligations": obligations,
        "classified_nodes": top_classified,
        "retrieval": retrieval,
    }


def run_pipeline(
    doc_path: Path,
    mode: str,
    doc_type: str,
    persist: bool = True,
    query: str | None = None,
    retrieval_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bronze = extract_bronze(doc_path)
    text = bronze["extracted_text"]
    router_decision = decide_mock_flow(
        query=query,
        document_text=text,
        requested_mode=mode,
        requested_doc_type=doc_type,
    )

    resolved_mode = router_decision["mode"]
    resolved_doc_type = router_decision["doc_type"]
    baseline_path = _select_baseline(resolved_doc_type)
    template_path = _select_template(resolved_doc_type)

    template = load_template(template_path)
    available_step_ids = [node["id"] for node in template.get("nodes", [])]
    selected_steps = choose_subtree_steps(
        profile=router_decision["subtree_profile"],
        available_step_ids=available_step_ids,
        mode=resolved_mode,
    )
    router_decision["selected_steps"] = selected_steps
    router_decision["available_steps"] = available_step_ids

    if mode == "auto" or doc_type == "auto":
        silver_candidate = SILVER_DIR / f"{doc_path.stem}.auto.auto.silver.json"
    else:
        silver_candidate = SILVER_DIR / f"{doc_path.stem}.{resolved_doc_type}.{resolved_mode}.silver.json"

    if retrieval_override is None:
        retrieval_result = resolve_dynamic_retrieval(
            query=query,
            doc_path=doc_path,
            doc_type=resolved_doc_type,
            mode=resolved_mode,
            bronze_path=BRONZE_DIR / f"{doc_path.stem}.bronze.json",
            silver_path=silver_candidate,
            k=3,
            params={"window": 6},
        )
    else:
        retrieval_result = retrieval_override

    router_decision["spine_source"] = retrieval_result.get("spine_source", "auto")
    router_decision["retrieval"] = retrieval_result.get("retrieval", {})

    dag_result = run_template_dag(
        template_path=template_path,
        mode=resolved_mode,
        initial_context={
            "text": text,
            "baseline_path": baseline_path,
        },
        requested_steps=selected_steps,
    )
    dag_context = dag_result["context"]

    spine = {
        "headings": dag_context.get("headings", []),
        "clauses": dag_context.get("clauses", []),
        "definitions": dag_context.get("definitions", []),
    }
    classified_nodes = dag_context.get("classified_nodes", [])
    findings = dag_context.get("findings", [])
    obligations = dag_context.get("obligations", [])
    dag_execution = {
        "template_id": dag_result.get("template_id"),
        "doc_type": dag_result.get("doc_type"),
        "mode": dag_result.get("mode"),
        "selected_steps": dag_result.get("selected_steps", []),
        "template_route_steps": dag_result.get("template_route_steps", []),
        "citation_policy": dag_result.get("citation_policy", {}),
        "executed_steps": dag_result.get("executed_steps", []),
        "trace": dag_result.get("trace", []),
    }

    evidence_packet = _build_evidence_packet(
        mode=resolved_mode,
        doc_type=resolved_doc_type,
        dag_execution=dag_execution,
        findings=findings,
        obligations=obligations,
        classified_nodes=classified_nodes,
        retrieval=router_decision.get("retrieval", {}),
    )

    bronze_path: Path | None = None
    silver_path: Path | None = None
    if persist:
        bronze_path = _persist_bronze_artifact(doc_path, bronze)
        silver_path = _persist_silver_artifact(
            doc_path,
            resolved_mode,
            resolved_doc_type,
            spine,
            classified_nodes,
            bronze_path,
            dag_execution,
            evidence_packet,
            router_decision,
        )

    if resolved_mode == "overview":
        output = {
            "document": str(doc_path),
            "doc_type": resolved_doc_type,
            "mode": resolved_mode,
            "query": query,
            "spine_stats": {
                "headings": len(spine["headings"]),
                "clauses": len(spine["clauses"]),
                "definitions": len(spine["definitions"]),
            },
            "orchestrator_decision": router_decision,
            "dag_execution": dag_execution,
            "evidence_packet": evidence_packet,
            "result": run_overview(classified_nodes),
        }
        if bronze_path and silver_path:
            output["artifacts"] = {
                "bronze": str(bronze_path),
                "silver": str(silver_path),
            }
        return output

    precision = run_precision(findings, router_decision.get("retrieval", {}).get("chunks", []))
    output = {
        "document": str(doc_path),
        "doc_type": resolved_doc_type,
        "mode": resolved_mode,
        "query": query,
        "spine_stats": {
            "headings": len(spine["headings"]),
            "clauses": len(spine["clauses"]),
            "definitions": len(spine["definitions"]),
        },
        "orchestrator_decision": router_decision,
        "dag_execution": dag_execution,
        "evidence_packet": evidence_packet,
        "obligations_detected": len(obligations),
        "result": precision,
    }
    if bronze_path and silver_path:
        output["artifacts"] = {
            "bronze": str(bronze_path),
            "silver": str(silver_path),
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Contract Analyst Agent orchestrator")
    parser.add_argument("--doc", required=True, help="Path to contract file (.txt, .pdf, .docx)")
    parser.add_argument("--mode", choices=["auto", "overview", "precision"], default="auto")
    parser.add_argument(
        "--doc-type",
        choices=["auto", "nda", "msa", "credit_agreement", "loan_agreement"],
        default="auto",
    )
    parser.add_argument(
        "--query",
        default="",
        help="User query string used by the mock orchestrator router",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Disable writing Bronze/Silver artifacts to docs/bronze and docs/silver",
    )
    args = parser.parse_args()

    output = run_pipeline(
        Path(args.doc),
        args.mode,
        args.doc_type,
        persist=not args.no_persist,
        query=args.query,
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
