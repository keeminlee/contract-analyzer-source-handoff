from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.demo_e2e import run_scenario
from scripts.render_mock_ui import render_report

SCENARIO_TO_BRONZE = {
    "credit_precision": "docs/bronze/sample_credit_agreement.bronze.json",
    "nda_overview": "docs/bronze/sample_nda.bronze.json",
}


def run_generation(
    scenario: str,
    print_mode: bool,
    no_timestamp: bool,
    tree_only: bool,
    quiet: bool,
    no_sim_delay: bool,
    speed: float,
    retrieval_override: str,
) -> dict[str, Any]:
    demo_result = run_scenario(
        name=scenario,
        persist=True,
        verbose_flow=not quiet,
        simulate_latency=not no_sim_delay,
        speed_multiplier=speed,
        retrieval_override_path=Path(retrieval_override) if retrieval_override else None,
    )

    evidence_path = Path(str(demo_result["output_path"]))
    bronze_path = ROOT / SCENARIO_TO_BRONZE.get(scenario, "docs/bronze/sample_credit_agreement.bronze.json")
    out_suffix = "tree" if tree_only else "mock_ui"
    out_path = ROOT / "demo_reports" / f"{scenario}_{out_suffix}.html"

    render_result = render_report(
        bronze_path=bronze_path,
        evidence_path=evidence_path,
        out_path=out_path,
        print_mode=print_mode,
        no_timestamp=no_timestamp,
        tree_only=tree_only,
    )

    return {
        "scenario": scenario,
        "bronze": str(bronze_path),
        "evidence": str(evidence_path),
        "out": str(out_path),
        "print_mode": print_mode,
        "no_timestamp": no_timestamp,
        "tree_only": tree_only,
        "doc_type": demo_result.get("doc_type"),
        "mode": demo_result.get("mode"),
        "citations": demo_result.get("citations"),
        "retrieval_chunks": demo_result.get("retrieval_chunks"),
        "render_bytes": render_result.get("bytes"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evidence packet and render mock UI HTML in one command")
    parser.add_argument("--scenario", choices=["credit_precision", "nda_overview"], default="credit_precision")
    parser.add_argument("--print", dest="print_mode", action="store_true", help="Enable screenshot-optimized print layout")
    parser.add_argument("--tree-only", action="store_true", help="Generate only the Contract Map (Nodes Touched) page")
    parser.add_argument("--no-timestamp", action="store_true", help="Omit runtime timestamp for deterministic hashing")
    parser.add_argument("--quiet", action="store_true", help="Suppress demo flow logs")
    parser.add_argument("--no-sim-delay", action="store_true", help="Disable simulated delay in demo pipeline")
    parser.add_argument("--speed", type=float, default=1.0, help="Simulated latency multiplier for demo_e2e")
    parser.add_argument("--retrieval-override", default="", help="Optional path to replay retrieval from an existing evidence packet")
    args = parser.parse_args()

    result = run_generation(
        scenario=args.scenario,
        print_mode=args.print_mode,
        no_timestamp=args.no_timestamp,
        tree_only=args.tree_only,
        quiet=args.quiet,
        no_sim_delay=args.no_sim_delay,
        speed=args.speed,
        retrieval_override=args.retrieval_override,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
