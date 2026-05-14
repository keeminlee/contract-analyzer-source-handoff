# CAA doc-to-KB — MUFG-Side Verification Instructions

> **Date authored:** 2026-05-08
> **From:** HQ (Contract Analyzer Agent doc-to-KB workstream)
> **To:** MUFG-side verifier (Keemin, MUFG hat)
> **Scope:** External-dependency verification gating Step 0 of `caa-doc-to-kb-comparison` plan tree
> **Companion files in this packet:**
> - `CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md` — fill out and return
> - `CAA_KB_PACKAGE_MANIFEST_2026-05-08.md` — manifest of this packet
> - `caa_kb_smoke_test.py` — runnable smoke harness for items (a), (c), (d)

---

## Why this packet exists

The doc-to-KB plan tree (`docs/week_7/05_08_2026/PLANS/caa-doc-to-kb-comparison/`) extends Contract Analyzer Agent (CAA) from a 1:1 doc-vs-doc surface into a 1:k doc-vs-knowledge-base surface. Steps 5-9 land Bedrock per-document embeddings + SingleStore vector retrieval + 1-to-k orchestration. None of those steps can land cleanly until four external dependencies are verified MUFG-side. This packet asks the MUFG verifier to confirm those dependencies and return measured values.

The four items split into two classes:

| Class | Item | Description |
|-------|------|-------------|
| **Blocking gate** | (a) | `bedrock:InvokeModel` IAM grant on `AIH_Operator_SBX` confirmed + smoke `embed(["test contract clause text..."])` succeeds |
| **Blocking gate** | (b) | MUFG SingleStore version supports needed vector ops (one of `DOT_PRODUCT` / `JSON_ARRAY_PACK` / native `VECTOR` column type) — confirmed by MUFG DBA |
| **Decision input** | (c) | Measured Bedrock embedding-call latency p50/p95 from CAA deploy env, against representative spine-doc-sized strings (not single `["test"]`) |
| **Decision input** | (d) | Measured Titan-v2 cost per 100 docs at the chosen embedding granularity (per-document for v1) |

Step 0 closes GREEN if and only if (a) and (b) both PASS. (c) and (d) close as DONE regardless of the values themselves; the values feed Step 6 (alert-threshold seeding) and Step 7 (model-choice confirmation).

---

## Environment expected MUFG-side

```text
Python: 3.11+ (3.13 confirmed working in prior cycle)
OS: any — local laptop or CAA deploy env (deploy env preferred for item (c))
Env vars / config required:
  - AWS Secrets Manager access on `/application/aid/prod/aida-app-secret`
    (or the equivalent dev/uat path for the AIH_Operator_SBX role under test)
  - `AWS_CA_BUNDLE` / `CAA_CONNECT_PROXY` set per AiDa deploy convention
  - `boto3`, `requests`, `urllib3`, `python-dotenv` installed
SingleStore client:
  - `mysql.connector` (Python) OR singlestore CLI / DataGrip access on the
    MUFG-side instance, with privileges sufficient to run
    `SHOW VARIABLES`, `CREATE TABLE`, `INSERT`, `SELECT`, `DROP TABLE`
    on a temporary schema
```

---

## What to install / configure

1. **Pull the AiDa Bedrock embedding adapter** — the smoke script depends on the OAuth + API GW proxy pattern in `MUFG/aida/aid_aida-backend/Bedrock_calls/embedding_gen.py`. The smoke script imports a slimmed copy of `BedrockEmbedder` inline so no editable install is needed; just confirm the proxy `universal_cert.pem` path resolves on the MUFG host (default in script: `/apps/aida/backend/aidabackend/Bedrock_calls/universal_cert.pem`; override via `CAA_AIDA_CERT_PATH` env var if elsewhere).

2. **Confirm IAM grant exists on `AIH_Operator_SBX`.** Open the AWS console → IAM → Roles → `AIH_Operator_SBX` → Permissions. The role must have a policy granting (at minimum) `bedrock:InvokeModel` on resource `arn:aws:bedrock:us-east-1:003231568750:application-inference-profile/fqs1gjwe2q7m` (the inference profile ARN used by AiDa's Bedrock proxy). Capture a screenshot or JSON snippet of the policy statement for evidence return.

3. **No new MUFG-side software needed for SingleStore item (b)** — DBA confirmation + a one-shot smoke against an ephemeral test table is enough; see step 5 below.

---

## What to run

Run the four checks in order. Capture outputs into `CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md` as you go.

### Item (a) — Bedrock IAM grant + smoke embedding call

**Goal:** Confirm `bedrock:InvokeModel` on `AIH_Operator_SBX` is live and a one-shot call returns a vector of expected dimensionality (1024 for Titan-v2; 1536 for Titan-v1 — the AiDa source uses `amazon.titan-embed-text-v1` in the payload model field via the proxy).

```bash
python caa_kb_smoke_test.py --mode iam-smoke
```

The script:
- Instantiates `BedrockEmbedder()` (slimmed from AiDa source)
- Calls `embed(["This Master Services Agreement is entered into between the parties identified above as of the Effective Date set forth herein."])` — a representative contract-clause-sized string (~200 chars), not the trivial `["test"]`
- Asserts response is a `list[list[float]]` with one inner list, length > 100
- Prints: HTTP status code (or "no HTTPError raised"), vector length, first 5 dims, total round-trip ms

**Evidence to capture for (a):**
- IAM policy JSON snippet (statement granting `bedrock:InvokeModel`) — copy from console
- Smoke-call stdout (vector length, first 5 dims, status, ms)
- If failure: full traceback + AWS request-id from response headers

### Item (b) — SingleStore vector-ops capability

**Goal:** Confirm the MUFG-side SingleStore instance supports the vector ops the retrieval path needs. Step 8 of the plan tree picks one of: (i) native `VECTOR(N)` column type + `DOT_PRODUCT` operator (preferred), (ii) `JSON_ARRAY_PACK` + cosine similarity via `JSON_EXTRACT` math (fallback), (iii) neither — in which case Step 8 needs a substrate re-decision and the tree pauses for re-scoping.

**(b1) DBA confirmation pass:**

```sql
-- Run on the MUFG-side SingleStore instance (any schema)
SELECT @@version;
SHOW VARIABLES LIKE '%vector%';
SHOW VARIABLES LIKE '%json%';
```

Capture the version string and the relevant variables. If `vector_type_project_format` (or any `vector_*` var) appears, native VECTOR is in scope. If only the JSON variables appear, fallback path is in scope.

**(b2) Smoke against an ephemeral test table:**

Pick whichever is supported and run a smoke. Replace `<your_test_schema>` with whatever schema you have CREATE rights on.

```sql
-- Preferred path: native VECTOR + DOT_PRODUCT
USE <your_test_schema>;
CREATE TABLE caa_kb_vector_smoke (
  id INT PRIMARY KEY,
  v VECTOR(8) NOT NULL
);
INSERT INTO caa_kb_vector_smoke VALUES
  (1, '[1,0,0,0,0,0,0,0]'),
  (2, '[0.7,0.7,0,0,0,0,0,0]'),
  (3, '[0,0,0,0,0,0,0,1]');
SELECT id, DOT_PRODUCT(v, '[1,0,0,0,0,0,0,0]' :> VECTOR(8)) AS sim
FROM caa_kb_vector_smoke
ORDER BY sim DESC;
DROP TABLE caa_kb_vector_smoke;
```

If the preferred path errors on `VECTOR(8)`, run the fallback:

```sql
-- Fallback path: JSON_ARRAY_PACK
USE <your_test_schema>;
CREATE TABLE caa_kb_vector_smoke (
  id INT PRIMARY KEY,
  v BLOB NOT NULL
);
INSERT INTO caa_kb_vector_smoke VALUES
  (1, JSON_ARRAY_PACK('[1,0,0,0,0,0,0,0]')),
  (2, JSON_ARRAY_PACK('[0.7,0.7,0,0,0,0,0,0]')),
  (3, JSON_ARRAY_PACK('[0,0,0,0,0,0,0,1]'));
SELECT id, DOT_PRODUCT(v, JSON_ARRAY_PACK('[1,0,0,0,0,0,0,0]')) AS sim
FROM caa_kb_vector_smoke
ORDER BY sim DESC;
DROP TABLE caa_kb_vector_smoke;
```

If both error: capture both error messages — Step 8 needs the re-scope decision.

**Evidence to capture for (b):**
- `@@version` output
- `SHOW VARIABLES` output (both queries)
- Which path you ran (preferred / fallback / neither worked)
- The `DOT_PRODUCT` result rows (id 1 should rank highest)
- DBA sign-off: free-text confirmation that the vector ops are usable for production CAA workloads (not just smoke), with any caveats

### Item (c) — Bedrock embedding-call latency p50/p95

**Goal:** Measure end-to-end embedding latency from the CAA deploy environment (NOT a local laptop unless the deploy env is unreachable; if local, note it in the return template as a caveat).

```bash
python caa_kb_smoke_test.py --mode latency-bench --n 50
```

The script:
- Instantiates `BedrockEmbedder()` once (token cached after first call)
- Loops 50 representative spine-doc-sized strings (built from a contract-clause corpus baked into the script — ~200-2000 chars each, varied by length to mimic real spine variance)
- Sequential calls (not parallel — we want serial latency, not throughput)
- Captures per-call: request bytes, response ms, vector length
- Computes: p50, p95, max, mean across the 50 calls
- Writes a CSV: `caa_kb_latency_bench_<timestamp>.csv` (50 rows + summary line)

**Evidence to capture for (c):**
- The CSV file (attach to evidence packet)
- Summary line: `n=50, p50=<ms>, p95=<ms>, max=<ms>, mean=<ms>`
- Environment hostname / deploy env name (so future readers know this isn't a laptop number)

### Item (d) — Titan-v2 cost per 100 docs at per-document granularity

**Goal:** Compute cost per 100 docs at v1's chosen granularity (one Bedrock call per doc, one vector per doc).

```bash
python caa_kb_smoke_test.py --mode cost-bench --n 50
```

The script:
- Reuses the same 50-doc corpus from item (c) (one-shot run can produce both deliverables; pass `--mode latency-and-cost` to combine)
- For each doc, captures: input token count (estimated from the response payload's `usage.input_tokens` field if the proxy returns it; otherwise approximated as `ceil(char_count / 4)`)
- Computes total tokens for the 50 docs
- Multiplies by Titan-v2 published pricing (current AWS list price: **$0.00002 per 1K input tokens** as of 2026-05-08 — verify against the AWS pricing page at run time and overwrite if changed)
- Extrapolates: `cost_per_100_docs = (total_tokens / 50) * 100 * (price_per_1k_tokens / 1000)`

**Evidence to capture for (d):**
- Total tokens across 50 docs
- Per-doc mean tokens
- Pricing source (AWS pricing page URL + screenshot or quoted figure)
- Final `$/100 docs` figure

---

## What to capture

All evidence goes into `CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md` (companion file in this packet). The template's section structure mirrors the prior cycle's `EVIDENCE_RETURN_TEMPLATE.md` exactly, adapted to this scope:

- **Package** — verifier name, date, environment
- **Environment Versions** — Python, AWS CLI, SingleStore client, deploy env name
- **Product Validation** — items (a) and (b) gate-pass evidence
- **Live Endpoint Validation** — replaced with **"Vector-ops Smoke"** (item (b) SQL outputs) and **"Embedding Smoke"** (item (a) script output)
- **Decision Input Measurements** — items (c) and (d) measured values
- **Screenshots / Attachments** — IAM policy screenshot, AWS pricing screenshot, latency CSV path
- **Blockers** — anything that prevented capturing evidence
- **Final Recommendation** — `GREEN` / `YELLOW` / `BLOCKED` (same convention as prior packet; see template for criteria)

---

## How to return

1. Fill in `CAA_KB_EVIDENCE_RETURN_TEMPLATE_2026-05-08.md`. Save it (and any attachments — CSVs, screenshots) as `CAA_KB_VERIFICATION_RETURN_2026-05-{DD}.md` (`{DD}` = the day you ran verification).
2. Bundle the return doc + attachments into a zip: `CAA_kb_verification_return_2026-05-{DD}.zip`.
3. Drop the zip at `MUFG/packets/2026-05-{DD}/CAA_kb_verification_return_2026-05-{DD}.zip` (the standard MUFG-side inbound location).
4. Notify HQ via the same channel used for the prior cycle (no new comms surface needed).

HQ's Step 0 closeout writes when the return zip lands. Tree Steps 1-13 stay in `NOT_STARTED` until then; Steps 1-4 may begin under MUFG verification in flight per the plan tree's preconditions section, but Step 5 onward is hard-gated on items (a) and (b) PASS.

---

## Provenance

- **Authored by:** `oh-my-claudecode:executor` agent under HQ runtime, OMC lane
- **Authored for:** `caa-doc-to-kb-comparison/0_mufg-external-dependency-verification` Step 0 packet-out
- **Mirrors shape of:** `MUFG/contract-analyzer-agent/handoff/EVIDENCE_RETURN_TEMPLATE.md` (prior cycle, returned GREEN 2026-05-06)
- **Source-of-truth references:**
  - `MUFG/aida/notes/AIDA_ENTERPRISE_READINESS_NOTES_2026-05-08.md` §2 (SingleStore), §3 (Bedrock proxy)
  - `MUFG/aida/aid_aida-backend/Bedrock_calls/embedding_gen.py` (slimmed into `caa_kb_smoke_test.py`)
- Session: 2026-05-08 evening, executor agent invocation `a5a55bfcd67bf1cad`
