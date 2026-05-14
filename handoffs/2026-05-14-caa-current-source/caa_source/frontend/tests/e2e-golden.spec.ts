import { expect, test } from "@playwright/test";

const uploadPayload = {
  schema_version: "contract_analyzer_upload_v1",
  analysis_id: "analysis_step8",
  session_id: "analysis_step8",
  filename: "primary-credit.txt",
  extension: ".txt",
  status: "accepted",
  bronze: {
    text: {
      full: "Failure to pay principal or interest when due is an Event of Default after a 30 day cure period.",
      char_count: 94
    },
    extracted_text: "Failure to pay principal or interest when due is an Event of Default after a 30 day cure period."
  },
  artifacts: {}
};

const insightPayload = {
  schema_version: "contract_analyzer_insight_answer_packet_v1",
  query: "Compare risk obligations",
  findings: [
    {
      finding_id: "risk_event_default_1",
      finding_type: "risk_flag",
      severity: "medium",
      summary: "Risk signal 'default' appears in primary contract evidence.",
      citation_ids: ["primary_chunk_1"],
      confidence: "medium"
    }
  ],
  citations: [
    {
      citation_id: "primary_chunk_1",
      document_role: "primary",
      analysis_id: "analysis_step8",
      chunk_id: "chunk_1",
      source_node_ids: ["spine_event_default"],
      span_start: 0,
      span_end: 94,
      excerpt: "Failure to pay principal or interest when due is an Event of Default after a 30 day cure period.",
      source_document: { name: "primary-credit.txt", extension: ".txt" }
    }
  ],
  chunks: [
    {
      citation_id: "primary_chunk_1",
      document_role: "primary",
      chunk_id: "chunk_1",
      span_start: 0,
      span_end: 94,
      excerpt: "Failure to pay principal or interest when due is an Event of Default after a 30 day cure period."
    }
  ],
  source_documents: [{ role: "primary", analysis_id: "analysis_step8", source: { name: "primary-credit.txt" } }],
  confidence: "medium",
  grounding: "grounded",
  answer_text: "Risk signal 'default' appears in primary contract evidence [primary_chunk_1].",
  warnings: [],
  abstention_reason: null,
  trace_metadata: { engine: "contract_insights.analyze_contract_insights" }
};

test("Step 8 golden path renders cited analysis and chat evidence", async ({ page }, testInfo) => {
  await page.route("**/api/v1/uploads", async (route) => {
    await route.fulfill({ json: uploadPayload });
  });
  await page.route("**/api/v1/analyses/analysis_step8/insights", async (route) => {
    await route.fulfill({ json: insightPayload });
  });
  await page.route("**/api/v1/analyses/analysis_step8/chat", async (route) => {
    await route.fulfill({
      json: {
        schema_version: "contract_analyzer_grounded_answer_v1",
        answer_text: "Default is supported by the cited event-of-default evidence [primary_chunk_1].",
        citations: ["primary_chunk_1"],
        grounding_state: "grounded",
        warnings: []
      }
    });
  });

  await page.goto("/");
  await page.getByLabel(/upload contract/i).setInputFiles({
    name: "primary-credit.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("credit contract")
  });

  await expect(page.getByText("analysis_step8").first()).toBeVisible();
  await expect(page.getByLabel(/findings/i).getByText("Risk signal 'default' appears in primary contract evidence.")).toBeVisible();
  await expect(page.getByRole("link", { name: /primary · chunk_1/i })).toHaveAttribute("href", "#citation-primary_chunk_1");
  await expect(page.getByLabel(/evidence citations/i).getByText(/Event of Default/i)).toBeVisible();

  await page.getByLabel(/ask a contract question/i).fill("Where is default cited?");
  await page.getByRole("button", { name: /send question/i }).click();

  await expect(page.getByText(/Where is default cited/i)).toBeVisible();
  await expect(page.getByText(/Default is supported/i)).toBeVisible();
  await expect(page.getByLabel(/persistent chat/i).getByText("primary_chunk_1", { exact: true })).toBeVisible();

  await page.screenshot({
    path: `test-results/step8-golden-${testInfo.project.name}.png`,
    fullPage: true
  });
});
