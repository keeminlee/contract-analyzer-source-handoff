from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.orchestrator import run_pipeline


SCENARIOS: dict[str, dict[str, str]] = {
    "nda_overview": {
        "doc": "docs/cache/sample_nda.txt",
        "query": "Give me a high-level summary and classify the major clauses.",
    },
    "credit_precision": {
        "doc": "docs/cache/sample_credit_agreement.txt",
        "query": "Quote events of default and compare against baseline risk requirements.",
    },
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(title: str, detail: str) -> None:
    print(f"[{_now()}] {title}")
    print(f"         {detail}")


def _wait(seconds: float, enabled: bool) -> None:
    if enabled and seconds > 0:
        time.sleep(seconds)


def _step_delay(step_id: str, speed: float) -> float:
    base = {
        "detect_headings": 0.20,
        "detect_numbered_clauses": 0.25,
        "extract_definitions": 0.22,
        "clause_classifier": 0.30,
        "obligation_extractor": 0.45,
        "playbook_compare": 0.65,
    }.get(step_id, 0.20)
    return max(0.05, base * max(0.1, speed))


def _print_decision_summary(decision: dict[str, Any]) -> None:
    rows = [
        ("Spine Source", str(decision.get("spine_source", ""))),
        ("Mode", str(decision.get("mode", ""))),
        ("Doc Type", str(decision.get("doc_type", ""))),
        ("Subtree Profile", str(decision.get("subtree_profile", ""))),
        ("Confidence", str(decision.get("confidence", ""))),
        (
            "Selected Steps",
            " -> ".join(decision.get("selected_steps", [])) if decision.get("selected_steps") else "(none)",
        ),
    ]
    key_width = max(len(key) for key, _ in rows)
    print("         +" + "-" * (key_width + 2) + "+" + "-" * 72 + "+")
    for key, value in rows:
        clipped_value = value[:72]
        print(f"         | {key.ljust(key_width)} | {clipped_value.ljust(72)}|")
    print("         +" + "-" * (key_width + 2) + "+" + "-" * 72 + "+")


def _load_retrieval_override(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    retrieval = payload.get("evidence_packet", {}).get("retrieval")
    if retrieval is None and isinstance(payload.get("retrieval"), dict):
        retrieval = payload.get("retrieval")

    if not isinstance(retrieval, dict):
        raise ValueError("retrieval override file must include evidence_packet.retrieval or retrieval object")

    spine_source = (
        payload.get("orchestrator_decision", {}).get("spine_source")
        or payload.get("spine_source")
        or "replay"
    )
    return {
        "spine_source": spine_source,
        "retrieval": retrieval,
    }


def run_scenario(
    name: str,
    persist: bool = True,
    verbose_flow: bool = True,
    simulate_latency: bool = True,
    speed_multiplier: float = 1.0,
    retrieval_override_path: Path | None = None,
) -> dict[str, Any]:
    if name not in SCENARIOS:
        valid = ", ".join(sorted(SCENARIOS.keys()))
        raise ValueError(f"Unknown scenario '{name}'. Valid scenarios: {valid}")

    scenario = SCENARIOS[name]
    requested_doc_path = ROOT / scenario["doc"]
    query = scenario["query"]
    retrieval_override = _load_retrieval_override(retrieval_override_path) if retrieval_override_path else None

    if verbose_flow:
        print("\n=== CONTRACT ANALYST AGENT • ONLINE FLOW DEMO ===")
        _log("1) Query Intake", f"Scenario='{name}' | RequestedDoc='{scenario['doc']}'")
        _log("   User Query", query)
        _wait(0.25 * speed_multiplier, simulate_latency)

        if retrieval_override:
            _log("2) Retrieval Source", f"Replay override loaded from {retrieval_override_path}")
        else:
            _log("2) Retrieval Source", "Delegating retrieval to orchestrator runtime")
        _wait(0.25 * speed_multiplier, simulate_latency)
        _log("3) Orchestrator Run", "Executing auto route with shared spine resolver + dynamic chunking")

    output = run_pipeline(
        doc_path=requested_doc_path,
        mode="auto",
        doc_type="auto",
        persist=persist,
        query=query,
        retrieval_override=retrieval_override,
    )

    decision = output.get("orchestrator_decision", {})

    evidence_packet = output.get("evidence_packet", {})
    evidence_payload = {
        "scenario": name,
        "query": scenario["query"],
        "requested_doc": scenario["doc"],
        "retrieval_override": str(retrieval_override_path) if retrieval_override_path else None,
        "doc_type": output.get("doc_type"),
        "mode": output.get("mode"),
        "orchestrator_decision": decision,
        "dag_execution": output.get("dag_execution", {}),
        "evidence_packet": evidence_packet,
    }

    out_path = ROOT / "docs" / "cache" / "demo_outputs" / f"{name}.evidence_packet.json"
    _write_json(out_path, evidence_payload)

    if verbose_flow:
        _wait(0.2 * speed_multiplier, simulate_latency)
        _log("4) Decision Summary", "Runtime routing and retrieval summary")
        _print_decision_summary(decision)

        selected_steps = decision.get("selected_steps", [])
        _log("5) Conditional DAG Plan", "Executed online plan:")
        print(f"         {' -> '.join(selected_steps) if selected_steps else '(none)'}")
        for idx, step_id in enumerate(selected_steps, start=1):
            _wait(_step_delay(step_id, speed_multiplier), simulate_latency)
            _log(f"   5.{idx} Executed Step", f"{step_id}")

        _wait(0.25 * speed_multiplier, simulate_latency)
        _log("6) Runtime Complete", f"doc_type={output.get('doc_type')} | mode={output.get('mode')} | chunks={len(evidence_packet.get('retrieval', {}).get('chunks', []))} | output={out_path}")
        print("=== END ONLINE FLOW DEMO ===\n")

    return {
        "scenario": name,
        "output_path": str(out_path),
        "document": str(requested_doc_path),
        "doc_type": output.get("doc_type"),
        "mode": output.get("mode"),
        "citations": len(evidence_packet.get("citations", [])),
        "retrieval_chunks": len(evidence_packet.get("retrieval", {}).get("chunks", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run demo E2E flow from query+doc to Evidence Packet")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS.keys()), default="credit_precision")
    parser.add_argument(
        "--retrieval-override",
        default="",
        help="Path to an evidence packet JSON whose evidence_packet.retrieval will be replayed",
    )
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Suppress formatted online-flow logging")
    parser.add_argument("--no-sim-delay", action="store_true", help="Disable artificial delay between online flow steps")
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Latency multiplier for simulated runtime (e.g., 0.7 faster, 1.4 slower)",
    )
    args = parser.parse_args()

    result = run_scenario(
        args.scenario,
        persist=not args.no_persist,
        verbose_flow=not args.quiet,
        simulate_latency=not args.no_sim_delay,
        speed_multiplier=args.speed,
        retrieval_override_path=Path(args.retrieval_override) if args.retrieval_override else None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
