"""CAA doc-to-KB external-dependency smoke harness.

Runs items (a), (c), and (d) from `CAA_KB_VERIFICATION_2026-05-08.md`:

  --mode iam-smoke         single embed call to confirm IAM grant + vector dim
  --mode latency-bench     50 sequential calls; emits CSV + p50/p95/max/mean
  --mode cost-bench        same 50 calls; emits per-doc tokens + cost / 100 docs
  --mode latency-and-cost  combined run (single call train, both summaries)

The embedding adapter is a slimmed copy of `BedrockEmbedder` from
`MUFG/aida/aid_aida-backend/Bedrock_calls/embedding_gen.py` so the smoke is
self-contained and does not require the AiDa repo on PYTHONPATH. The proxy
shape (OAuth client-credentials → MUFG API GW → Bedrock) is preserved
unchanged from the source. Cert path defaults to the AiDa deploy convention;
override via env var `CAA_AIDA_CERT_PATH` if running off a non-AiDa host.

This is verification scaffolding, not production code. Do not import from CAA
runtime; do not promote to a CAA module. When item (a) lands GREEN, Step 7 of
the plan tree ports the adapter into CAA-side `bedrock_embedding.py` with
CAA-specific parameterization (its own secret path, OAuth scope, inference
profile ARN, model ID — not the AiDa values used here).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import statistics
import sys
import time
import urllib3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import boto3
import requests

logger = logging.getLogger("caa_kb_smoke")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Constants — copied verbatim from MUFG/aida/.../embedding_gen.py
# (production prd values; override via env vars for dev/uat smokes)
# ---------------------------------------------------------------------------

_NEW_API_NAME = os.environ.get(
    "CAA_AIDA_SECRET_NAME",
    "/application/aid/prod/aida-app-secret",
)
_NEW_API_INFERENCE_PROFILE = os.environ.get(
    "CAA_AIDA_INFERENCE_PROFILE",
    "arn:aws:bedrock:us-east-1:003231568750:application-inference-profile/fqs1gjwe2q7m",
)
_NEW_API_APIGW_ID = os.environ.get("CAA_AIDA_APIGW_ID", "cpvmmdvf08")
_REGION = os.environ.get("CAA_AIDA_REGION", "us-east-1")
_CERT_PATH = os.environ.get(
    "CAA_AIDA_CERT_PATH",
    "/apps/aida/backend/aidabackend/Bedrock_calls/universal_cert.pem",
)
_EMBED_MODEL_PAYLOAD_FIELD = os.environ.get(
    "CAA_AIDA_EMBED_MODEL", "amazon.titan-embed-text-v1"
)


# ---------------------------------------------------------------------------
# BedrockEmbedder — slimmed from AiDa source (embed() path only)
# ---------------------------------------------------------------------------


class BedrockEmbedder:
    """OAuth + API-GW proxy embedder. Mirrors AiDa's class-level token cache."""

    def __init__(self) -> None:
        self._secrets: dict | None = None
        self._oauth_token: str | None = None

    def _load_secrets(self) -> dict:
        if self._secrets is None:
            sm = boto3.client("secretsmanager", region_name=_REGION, verify=False)
            self._secrets = json.loads(
                sm.get_secret_value(SecretId=_NEW_API_NAME)["SecretString"]
            )
        return self._secrets

    def _get_oauth_token(self) -> str:
        if self._oauth_token:
            return self._oauth_token
        secrets = self._load_secrets()
        proxies = {"http": secrets["proxy_url"], "https": secrets["proxy_url"]}
        token_url = (
            f"https://login.microsoftonline.com/{secrets['tenant_id']}"
            "/oauth2/v2.0/token"
        )
        payload = {
            "grant_type": "client_credentials",
            "client_id": secrets["client_id"],
            "client_secret": secrets["client_secret"],
            "scope": "api://54638f69-6be4-4d65-942b-a0a6f19785e0/.default",
        }
        resp = requests.post(token_url, data=payload, verify=_CERT_PATH, proxies=proxies)
        resp.raise_for_status()
        self._oauth_token = resp.json()["access_token"]
        return self._oauth_token

    def embed(self, texts: list[str], retries: int = 3) -> tuple[list[list[float]], dict]:
        """Return (vectors, response_metadata).

        response_metadata carries any `usage` field the proxy returns (input_tokens,
        total_tokens) plus the raw response status code; cost-bench reads these.
        """
        secrets = self._load_secrets()
        payload = {
            "model": _EMBED_MODEL_PAYLOAD_FIELD,
            "input": texts,
            "inferenceProfileId": _NEW_API_INFERENCE_PROFILE,
        }
        embed_endpoint = secrets["api_endpoint"].replace("/invoke", "/embeddings")

        for attempt in range(1, retries + 1):
            token = self._get_oauth_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-apigw-api-id": _NEW_API_APIGW_ID,
            }
            try:
                resp = requests.post(
                    embed_endpoint,
                    headers=headers,
                    json=payload,
                    verify=_CERT_PATH,
                    timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()
                data = result.get("data", [])
                if not data:
                    raise ValueError("embed: empty 'data' in response")
                sorted_data = sorted(data, key=lambda x: x.get("index", 0))
                vectors = [item["embedding"] for item in sorted_data]
                meta = {
                    "status_code": resp.status_code,
                    "usage": result.get("usage", {}),
                }
                return vectors, meta
            except requests.exceptions.HTTPError:
                if resp.status_code == 401:
                    self._oauth_token = None
                elif resp.status_code == 502 and attempt < retries:
                    wait = attempt * 2
                    logger.info(f"502, retrying in {wait}s (attempt {attempt}/{retries})")
                    time.sleep(wait)
                    continue
                raise
            except requests.exceptions.Timeout:
                if attempt < retries:
                    logger.info(f"Timeout, retrying (attempt {attempt}/{retries})")
                    time.sleep(2)
                    continue
                raise
        raise RuntimeError("embed: all retries exhausted")


# ---------------------------------------------------------------------------
# Representative spine-doc corpus
#   50 strings, contract-clause shaped, varied length to mimic real spine
#   variance (~200-2000 chars). Built from a small clause vocabulary cycled
#   with deterministic length expansion so the corpus is reproducible across
#   runs and verifiers.
# ---------------------------------------------------------------------------


_CLAUSE_SEEDS = [
    "This Master Services Agreement is entered into between the parties identified above as of the Effective Date set forth herein.",
    "The Provider shall deliver the Services in accordance with the specifications set forth in Schedule A attached hereto.",
    "Each party agrees to indemnify and hold harmless the other party from and against any and all claims, losses, damages, liabilities, costs, and expenses arising out of or relating to a breach of this Agreement.",
    "Confidential Information shall not include information that (a) is or becomes generally known to the public through no fault of the receiving party, (b) was known to the receiving party prior to disclosure, or (c) is rightfully obtained from a third party without restriction.",
    "This Agreement shall commence on the Effective Date and continue for an initial term of three years, after which it shall automatically renew for successive one-year terms unless either party provides written notice of non-renewal at least ninety days prior to the end of the then-current term.",
    "The Provider warrants that the Services will be performed in a professional and workmanlike manner consistent with industry standards generally accepted by similarly situated providers in the relevant industry.",
    "Neither party shall be liable for any indirect, incidental, special, consequential, or punitive damages, including but not limited to loss of profits, loss of revenue, loss of business, or loss of data, arising out of or relating to this Agreement, regardless of the form of action and whether or not such party has been advised of the possibility of such damages.",
    "All notices required or permitted under this Agreement shall be in writing and shall be deemed given when delivered personally, sent by confirmed facsimile transmission, sent by certified or registered mail, return receipt requested, or sent by recognized overnight courier service.",
    "This Agreement shall be governed by and construed in accordance with the laws of the State of New York, without regard to its conflict of laws principles, and the parties hereby consent to the exclusive jurisdiction of the state and federal courts located in New York County, New York for the resolution of any dispute arising hereunder.",
    "The Customer shall pay all invoices within thirty days of receipt; any amounts not paid when due shall accrue interest at the lesser of one and one-half percent per month or the maximum rate permitted by applicable law.",
]


def build_corpus(n: int = 50) -> list[str]:
    """Return n contract-clause-sized strings, deterministic, varied length."""
    out: list[str] = []
    for i in range(n):
        seed = _CLAUSE_SEEDS[i % len(_CLAUSE_SEEDS)]
        # Expand by repeating the seed 1..5 times so length varies across the run
        repeats = 1 + (i % 5)
        out.append(" ".join([seed] * repeats))
    return out


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


@dataclass
class CallRecord:
    idx: int
    request_bytes: int
    response_ms: float
    vector_len: int
    input_tokens: int  # 0 if proxy did not return usage


def _approx_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def run_iam_smoke() -> int:
    embedder = BedrockEmbedder()
    text = (
        "This Master Services Agreement is entered into between the parties "
        "identified above as of the Effective Date set forth herein."
    )
    logger.info("Calling embed([<200-char contract clause>]) ...")
    t0 = time.perf_counter()
    vectors, meta = embedder.embed([text])
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert isinstance(vectors, list) and len(vectors) == 1, "expected one vector back"
    v = vectors[0]
    assert isinstance(v, list) and len(v) > 100, f"vector too short: len={len(v)}"
    print("IAM SMOKE PASS")
    print(f"  status_code:      {meta['status_code']}")
    print(f"  vector_length:    {len(v)}")
    print(f"  first_5_dims:     {v[:5]}")
    print(f"  round_trip_ms:    {elapsed_ms:.1f}")
    print(f"  proxy_usage:      {meta['usage']}")
    return 0


def _bench_loop(n: int) -> list[CallRecord]:
    embedder = BedrockEmbedder()
    corpus = build_corpus(n)
    records: list[CallRecord] = []
    for i, text in enumerate(corpus):
        request_bytes = len(text.encode("utf-8"))
        t0 = time.perf_counter()
        vectors, meta = embedder.embed([text])
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        usage = meta.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        if input_tokens == 0:
            input_tokens = _approx_tokens(text)
        records.append(
            CallRecord(
                idx=i,
                request_bytes=request_bytes,
                response_ms=elapsed_ms,
                vector_len=len(vectors[0]),
                input_tokens=input_tokens,
            )
        )
        if (i + 1) % 10 == 0:
            logger.info(f"  ... {i + 1}/{n} done")
    return records


def _write_csv(records: Iterable[CallRecord], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "request_bytes", "response_ms", "vector_len", "input_tokens"])
        for r in records:
            w.writerow([r.idx, r.request_bytes, f"{r.response_ms:.2f}", r.vector_len, r.input_tokens])


def _summarize_latency(records: list[CallRecord]) -> dict:
    times = [r.response_ms for r in records]
    times_sorted = sorted(times)
    n = len(times_sorted)

    def pct(p: float) -> float:
        if n == 0:
            return 0.0
        k = max(0, min(n - 1, int(round(p * (n - 1)))))
        return times_sorted[k]

    return {
        "n": n,
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "max_ms": max(times) if times else 0.0,
        "mean_ms": statistics.mean(times) if times else 0.0,
    }


def _summarize_cost(records: list[CallRecord], price_per_1k_input_tokens: float) -> dict:
    total_tokens = sum(r.input_tokens for r in records)
    n = len(records)
    mean_tokens = total_tokens / n if n else 0
    cost_per_100_docs = (total_tokens / n * 100 * (price_per_1k_input_tokens / 1000.0)) if n else 0.0
    return {
        "n": n,
        "total_tokens": total_tokens,
        "mean_tokens_per_doc": mean_tokens,
        "price_per_1k_input_tokens_usd": price_per_1k_input_tokens,
        "cost_per_100_docs_usd": cost_per_100_docs,
    }


def run_latency_bench(n: int, csv_path: Path) -> int:
    logger.info(f"Latency bench: n={n}")
    records = _bench_loop(n)
    _write_csv(records, csv_path)
    summary = _summarize_latency(records)
    print("LATENCY BENCH")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  csv: {csv_path}")
    return 0


def run_cost_bench(n: int, price: float, csv_path: Path) -> int:
    logger.info(f"Cost bench: n={n}, price/1K={price}")
    records = _bench_loop(n)
    _write_csv(records, csv_path)
    summary = _summarize_cost(records, price)
    print("COST BENCH")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  csv: {csv_path}")
    return 0


def run_latency_and_cost(n: int, price: float, csv_path: Path) -> int:
    logger.info(f"Latency-and-cost combined: n={n}, price/1K={price}")
    records = _bench_loop(n)
    _write_csv(records, csv_path)
    lat = _summarize_latency(records)
    cost = _summarize_cost(records, price)
    print("LATENCY BENCH")
    for k, v in lat.items():
        print(f"  {k}: {v}")
    print("COST BENCH")
    for k, v in cost.items():
        print(f"  {k}: {v}")
    print(f"  csv: {csv_path}")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAA doc-to-KB smoke harness")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["iam-smoke", "latency-bench", "cost-bench", "latency-and-cost"],
    )
    parser.add_argument("--n", type=int, default=50, help="bench loop size (latency/cost)")
    parser.add_argument(
        "--price-per-1k",
        type=float,
        default=0.00002,
        help="USD price per 1K input tokens (Titan-v2 list as of 2026-05-08; override per AWS pricing page at run time)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path.cwd(),
        help="directory to write CSV outputs (default: CWD)",
    )
    args = parser.parse_args(argv)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = args.out_dir / f"caa_kb_{args.mode}_{timestamp}.csv"

    if args.mode == "iam-smoke":
        return run_iam_smoke()
    if args.mode == "latency-bench":
        return run_latency_bench(args.n, csv_path)
    if args.mode == "cost-bench":
        return run_cost_bench(args.n, args.price_per_1k, csv_path)
    if args.mode == "latency-and-cost":
        return run_latency_and_cost(args.n, args.price_per_1k, csv_path)
    return 2


if __name__ == "__main__":
    sys.exit(main())
