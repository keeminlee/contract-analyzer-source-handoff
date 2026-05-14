# CAA doc-to-KB — Evidence Return Template

> Fill this out after MUFG-side verification and return it (with attachments) as
> `CAA_KB_VERIFICATION_RETURN_2026-05-{DD}.md` per `CAA_KB_VERIFICATION_2026-05-08.md` § "How to return".

---

## Package

- Source packet name: `CAA_kb_verification_request_2026-05-08`
- Source packet contents: `CAA_KB_VERIFICATION_2026-05-08.md` + this template + `CAA_KB_PACKAGE_MANIFEST_2026-05-08.md` + `caa_kb_smoke_test.py`
- Verification date: 2026-05-{DD}
- Verifier: <name> (MUFG-side)
- Environment: <CAA deploy env name OR `local laptop` with caveat>
- Hostname / instance id: `<host>`

## Environment Versions

```text
python --version: <e.g. Python 3.13.0>
pip --version: <e.g. pip 26.0.1>
boto3 version: <pip show boto3 | grep Version>
requests version: <pip show requests | grep Version>
AWS region: us-east-1
SingleStore version (@@version): <e.g. 8.5.x>
SingleStore client used: <mysql.connector / DataGrip / singlestore CLI>
Bedrock proxy cert path resolved: <path used; default `/apps/aida/backend/aidabackend/Bedrock_calls/universal_cert.pem`>
OS / runtime: <e.g. Windows 11 / RHEL 8 / Amazon Linux 2>
```

---

## Product Validation — Blocking Gate Items

These two items must both PASS for Step 0 to close GREEN.

### (a) Bedrock IAM grant + smoke embedding call

| Check | Command / source | Result | Notes / evidence |
|-------|------------------|--------|------------------|
| `bedrock:InvokeModel` granted on `AIH_Operator_SBX` (or actual deploy role) | AWS Console → IAM → Roles → `<role>` → Permissions | <PASS / FAIL> | Policy JSON snippet in Attachments §Screenshots; resource ARN: `arn:aws:bedrock:us-east-1:003231568750:application-inference-profile/fqs1gjwe2q7m` |
| Smoke embedding call returns vector | `python caa_kb_smoke_test.py --mode iam-smoke` | <PASS / FAIL> | Vector length: `<n>`; first 5 dims: `[<...>]`; round-trip ms: `<n>` |

If FAIL — paste the full traceback + AWS request id here:

```text
<traceback or "N/A — passed">
```

### (b) SingleStore vector-ops capability

| Check | Command / source | Result | Notes / evidence |
|-------|------------------|--------|------------------|
| `@@version` captured | `SELECT @@version;` | <output> | — |
| `SHOW VARIABLES LIKE '%vector%';` | (SQL) | <output rows> | Native VECTOR support: <YES / NO> |
| `SHOW VARIABLES LIKE '%json%';` | (SQL) | <output rows> | JSON_ARRAY_PACK available: <YES / NO> |
| Smoke smoke ran on path | preferred (native VECTOR + DOT_PRODUCT) / fallback (JSON_ARRAY_PACK) / neither | <one of three> | If `neither`, see Blockers — Step 8 needs re-scope |
| Smoke `DOT_PRODUCT` ranking correct (id 1 highest) | (SQL) | <PASS / FAIL> | Result rows: `<id, sim>` × 3 |
| MUFG DBA sign-off | DBA name + free-text | <PASS / FAIL> | DBA: `<name>`; caveats: `<text>` |

If FAIL on the smoke — paste both error messages (preferred and fallback) here:

```text
<errors or "N/A — passed">
```

---

## Vector-ops Smoke (item (b) raw output)

```sql
-- @@version
<paste here>

-- SHOW VARIABLES LIKE '%vector%';
<paste here>

-- SHOW VARIABLES LIKE '%json%';
<paste here>

-- DOT_PRODUCT smoke (preferred or fallback path)
<paste CREATE / INSERT / SELECT output here>
```

---

## Embedding Smoke (item (a) raw output)

```text
$ python caa_kb_smoke_test.py --mode iam-smoke
<paste stdout here, including vector length, first 5 dims, round-trip ms, status>
```

---

## Decision Input Measurements

These two items must return with measured values; any value passes the step. Values feed Step 6 (alert threshold) and Step 7 (model confirmation).

### (c) Bedrock embedding-call latency p50/p95

| Field | Value |
|-------|-------|
| Run command | `python caa_kb_smoke_test.py --mode latency-bench --n 50` |
| n (calls) | 50 |
| Environment (deploy / laptop) | <one of> |
| p50 ms | `<n>` |
| p95 ms | `<n>` |
| max ms | `<n>` |
| mean ms | `<n>` |
| CSV attachment path | `caa_kb_latency_bench_<timestamp>.csv` (in zip) |
| Caveats | <e.g. ran on local laptop because deploy env not yet provisioned> |

### (d) Titan-v2 cost per 100 docs at per-document granularity

| Field | Value |
|-------|-------|
| Run command | `python caa_kb_smoke_test.py --mode cost-bench --n 50` (or `--mode latency-and-cost`) |
| Total tokens across 50 docs | `<n>` |
| Mean tokens per doc | `<n>` |
| Pricing source | <AWS pricing page URL + screenshot in Attachments> |
| Price per 1K input tokens (Titan-v2) | `$<n>` |
| Computed cost per 100 docs | `$<n>` |
| Caveats | <e.g. token count approximated from char/4 because proxy did not return usage> |

---

## Screenshots / Attachments

| Item | Filename in zip | Notes |
|------|-----------------|-------|
| IAM policy screenshot or JSON snippet | `iam_AIH_Operator_SBX_bedrock_invoke.<png/json>` | item (a) evidence |
| Latency CSV | `caa_kb_latency_bench_<timestamp>.csv` | item (c) evidence |
| AWS Titan-v2 pricing screenshot | `titan_v2_pricing_2026-05-{DD}.png` | item (d) evidence |
| DBA sign-off email or chat snippet (optional) | `dba_signoff_2026-05-{DD}.<png/txt>` | item (b) evidence |
| Logs (any failed-call tracebacks) | `failed_calls.log` | only if failures |

---

## Blockers

| Blocker | Owner | Exact error | Recommended next action |
|---------|-------|-------------|-------------------------|
| <e.g. IAM grant not yet applied> | <e.g. MUFG IAM admin> | `<paste error>` | <e.g. Re-run after grant applied; expected ETA <date>> |
| ... | ... | ... | ... |

(If no blockers, write "None.")

---

## Final Recommendation

Choose one:

- `GREEN` — Both gate items (a) and (b) PASS; both decision-input items (c) and (d) measured. Step 0 closes GREEN; tree Steps 5-9 unblock.
- `YELLOW` — One gate item PASS, one FAIL (or one decision-input item missing for non-blocking environment reasons). Step 0 closes YELLOW; named gate item re-runs on next packet cycle.
- `BLOCKED` — Both gate items FAIL, OR item (b) returns "neither path supported" (Step 8 re-scope required). Step 0 closes BLOCKED; tree pauses for principal re-decision.

Recommendation: `<GREEN / YELLOW / BLOCKED>`

Rationale: <one paragraph explaining the verdict against the criteria above. If GREEN, summarize the four pieces of evidence in one sentence each. If YELLOW or BLOCKED, name the specific failure mode and the expected resolution path.>

---

## Provenance

- Verifier: <name>
- Date: 2026-05-{DD}
- Source packet: `CAA_kb_verification_request_2026-05-08` (HQ-authored 2026-05-08 evening, executor agent invocation `a5a55bfcd67bf1cad`)
- Return zip: `MUFG/packets/2026-05-{DD}/CAA_kb_verification_return_2026-05-{DD}.zip`
