# Mock UI Reports

Generate a screenshottable, business-readable HTML report from Bronze + Evidence artifacts.

## One-command flow (recommended)

```bash
python scripts/generate_mock_report.py --scenario credit_precision --print
```

Output:

- `demo_reports/credit_precision_mock_ui.html`
- `demo_reports/credit_precision_tree.html` (when `--tree-only` is used)

## Direct renderer flow

```bash
python scripts/render_mock_ui.py \
  --bronze docs/bronze/sample_credit_agreement.bronze.json \
  --evidence docs/cache/demo_outputs/credit_precision.evidence_packet.json \
  --out demo_reports/credit_precision_mock_ui.html \
  --print
```

Tree-only render:

```bash
python scripts/render_mock_ui.py \
  --bronze docs/bronze/sample_credit_agreement.bronze.json \
  --evidence docs/cache/demo_outputs/credit_precision.evidence_packet.json \
  --out demo_reports/credit_precision_tree.html \
  --tree-only
```

## Deterministic hashing mode

Use `--no-timestamp` to suppress runtime timestamp text in the footer for stable file hashing.

```bash
python scripts/render_mock_ui.py \
  --bronze docs/bronze/sample_credit_agreement.bronze.json \
  --evidence docs/cache/demo_outputs/credit_precision.evidence_packet.json \
  --out demo_reports/credit_precision_mock_ui.html \
  --no-timestamp
```

For one-command tree-only generation:

```bash
python scripts/generate_mock_report.py --scenario credit_precision --tree-only --no-timestamp
```

## Screenshot workflow (<2 minutes)

1. Open `demo_reports/credit_precision_mock_ui.html` in Chrome.
2. Set browser zoom to `110%`.
3. Capture screenshot A: top section with `Ask and Routing + Document Map + Evidence Used`.
4. Capture screenshot B: `DAG Execution Trace + Findings`.

Capture methods:

- Chrome DevTools: `Ctrl+Shift+I` -> `Ctrl+Shift+P` -> "Capture full size screenshot"
- Windows Snipping Tool for selective crop

## Notes

- The report follows the evidence-first policy: no citation, no answer.
- Raw JSON is available in a collapsed `View raw artifacts` section and hidden by default.
- Displayed evidence snippets are top-3 ranked chunks from the evidence packet.
- Tree highlights are span-based and deterministic: evidence path uses only displayed evidence spans and citation spans.
