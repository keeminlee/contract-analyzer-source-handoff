// Layer 3 E2E tests: citation click-through, CitationSourcePanel, SourcePdfViewerPanel.
// Mocks: POST uploads, GET insights, GET analyses pdf

import { expect, test } from "@playwright/test";

const ANALYSIS_ID = "layer3_test_analysis";

// A minimal valid-looking PDF (just enough bytes that the browser loads it).
const MINI_PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
    "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
    "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n" +
    "xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n" +
    "0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
);

const uploadPayload = {
  schema_version: "contract_analyzer_upload_v1",
  analysis_id: ANALYSIS_ID,
  session_id: ANALYSIS_ID,
  filename: "sample-credit.pdf",
  extension: ".pdf",
  status: "accepted",
  bronze: {
    text: { full: "Borrower shall default if payment is not made within 30 days.", char_count: 61 },
    extracted_text: "Borrower shall default if payment is not made within 30 days.",
    metadata: {
      page_spans: [{ page_number: 1, span_start: 0, span_end: 61 }],
      page_count: 1
    }
  },
  artifacts: {}
};

const insightPayload = {
  schema_version: "contract_analyzer_insight_answer_packet_v1",
  query: "What triggers default?",
  findings: [
    {
      finding_id: "risk_default_1",
      finding_type: "risk_flag",
      severity: "high",
      summary: "Borrower defaults if payment is missed after 30 days.",
      citation_ids: [`${ANALYSIS_ID}_chunk_1`],
      confidence: "high"
    }
  ],
  citations: [
    {
      citation_id: `${ANALYSIS_ID}_chunk_1`,
      document_role: "primary",
      analysis_id: ANALYSIS_ID,
      chunk_id: "chunk_1",
      source_node_ids: ["auto_1"],
      span_start: 0,
      span_end: 61,
      excerpt: "Borrower shall default if payment is not made within 30 days.",
      source_document: { name: "sample-credit.pdf", extension: ".pdf" },
      page_start: 1,
      page_end: 1,
      pdf_url: `/api/v1/analyses/${ANALYSIS_ID}/pdf`
    }
  ],
  chunks: [],
  source_documents: [{ role: "primary", analysis_id: ANALYSIS_ID, source: { name: "sample-credit.pdf" } }],
  confidence: "high",
  grounding: "grounded",
  answer_text: "Default is triggered when payment is missed after 30 days [chunk_1].",
  warnings: [],
  abstention_reason: null
};

test.beforeEach(async ({ page }) => {
  // Mock upload
  await page.route(`**/api/v1/uploads`, (route) =>
    route.fulfill({ json: uploadPayload })
  );

  // Mock insights
  await page.route(`**/api/v1/analyses/${ANALYSIS_ID}/insights`, (route) =>
    route.fulfill({ json: insightPayload })
  );

  // Mock PDF serving — return minimal PDF bytes
  await page.route(`**/api/v1/analyses/${ANALYSIS_ID}/pdf`, (route) =>
    route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `inline; filename="sample-credit.pdf"`,
        "Content-Length": String(MINI_PDF.length)
      },
      body: MINI_PDF
    })
  );

  await page.goto("/");

  // Upload
  await page.getByLabel(/upload contract/i).setInputFiles({
    name: "sample-credit.pdf",
    mimeType: "application/pdf",
    buffer: MINI_PDF
  });

  // Wait for analysis to complete
  await expect(page.getByText(ANALYSIS_ID).first()).toBeVisible({ timeout: 10_000 });
});

test("layer3: evidence rows are clickable and show citation source panel", async ({ page }, testInfo) => {
  // Evidence panel should have citation with page badge
  const evidenceRow = page.getByTestId(`citation-row-chunk_1`);
  await expect(evidenceRow).toBeVisible();

  // Page badge present (page_start=1)
  await expect(evidenceRow.getByTestId("page-badge")).toHaveText(/p\.1/);

  // Provenance panels not yet shown
  await expect(page.getByTestId("provenance-panels")).not.toBeVisible();

  // Click the evidence row
  await evidenceRow.click();

  // Provenance panels should now appear
  await expect(page.getByTestId("provenance-panels")).toBeVisible();

  // CitationSourcePanel: excerpt and meta
  await expect(page.getByTestId("citation-meta")).toBeVisible();
  await expect(page.getByTestId("citation-page-label")).toHaveText(/p\.\s*1/);
  await expect(page.getByTestId("citation-excerpt")).toContainText("Borrower shall default");

  await page.screenshot({
    path: `test-results/layer3-citation-panel-${testInfo.project.name}.png`,
    fullPage: true
  });
});

test("layer3: open-in-viewer button shows PDF iframe", async ({ page }, testInfo) => {
  // Click evidence row to select citation
  await page.getByTestId(`citation-row-chunk_1`).click();
  await expect(page.getByTestId("provenance-panels")).toBeVisible();

  // Source viewer should show placeholder before clicking button
  // (citation has pdf_url so viewer is shown automatically when citation has pdf_url)
  const viewerPanel = page.getByTestId("source-viewer-panel");
  await expect(viewerPanel).toBeVisible();

  // PDF iframe should appear (citation.pdf_url is set so it's shown directly)
  const iframe = page.getByTestId("pdf-iframe");
  await expect(iframe).toBeVisible();

  // Iframe src should include analysis_id and page hash
  const iframeSrc = await iframe.getAttribute("src");
  expect(iframeSrc).toContain(ANALYSIS_ID);
  expect(iframeSrc).toContain("#page=1");

  // Page label in toolbar
  await expect(page.getByTestId("viewer-page-label")).toHaveText(/Page 1/);

  await page.screenshot({
    path: `test-results/layer3-pdf-viewer-${testInfo.project.name}.png`,
    fullPage: true
  });
});

test("layer3: citation-empty state shown before any click", async ({ page }) => {
  // Before selecting a citation, provenance panels are hidden
  await expect(page.getByTestId("provenance-panels")).not.toBeVisible();
  // The viewer placeholder is not yet mounted
  await expect(page.getByTestId("viewer-placeholder")).not.toBeVisible();
});
