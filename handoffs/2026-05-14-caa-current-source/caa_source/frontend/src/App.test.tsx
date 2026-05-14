import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const uploadPayload = {
  schema_version: "contract_analyzer_upload_v1",
  analysis_id: "analysis_test_1",
  session_id: "analysis_test_1",
  filename: "credit.txt",
  extension: ".txt",
  status: "accepted",
  bronze: {
    text: {
      full: "The Borrower shall pay interest at 9 percent. Failure to pay is an Event of Default.",
      char_count: 83
    }
  },
  artifacts: {}
};

const insightPayload = {
  schema_version: "contract_analyzer_insight_answer_packet_v1",
  query: "Compare risk obligations",
  findings: [
    {
      finding_id: "comparison_deviation_1",
      finding_type: "comparison_deviation",
      severity: "medium",
      summary: "Primary contract language materially differs from the uploaded baseline.",
      citation_ids: ["primary_chunk_1", "baseline_chunk_1"],
      confidence: "medium"
    }
  ],
  citations: [
    {
      citation_id: "primary_chunk_1",
      document_role: "primary",
      analysis_id: "analysis_test_1",
      chunk_id: "chunk_1",
      source_node_ids: ["spine_1"],
      span_start: 0,
      span_end: 44,
      excerpt: "The Borrower shall pay interest at 9 percent.",
      source_document: { name: "credit.txt" }
    },
    {
      citation_id: "baseline_chunk_1",
      document_role: "baseline",
      analysis_id: "baseline_test_1",
      chunk_id: "chunk_1",
      source_node_ids: ["spine_2"],
      span_start: 0,
      span_end: 44,
      excerpt: "The Borrower shall pay interest at 5 percent.",
      source_document: { name: "baseline.txt" }
    }
  ],
  chunks: [
    {
      citation_id: "primary_chunk_1",
      document_role: "primary",
      chunk_id: "chunk_1",
      span_start: 0,
      span_end: 44,
      excerpt: "The Borrower shall pay interest at 9 percent."
    }
  ],
  source_documents: [
    { role: "primary", analysis_id: "analysis_test_1", source: { name: "credit.txt" } },
    { role: "baseline", analysis_id: "baseline_test_1", source: { name: "baseline.txt" } }
  ],
  confidence: "medium",
  grounding: "grounded",
  answer_text: "Primary contract language materially differs [primary_chunk_1].",
  warnings: [],
  abstention_reason: null,
  trace_metadata: { engine: "contract_insights.analyze_contract_insights" }
};

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }));
}

function uploadFile(file: File) {
  fireEvent.change(screen.getByLabelText(/upload contract/i), { target: { files: [file] } });
}

describe("Contract Analyzer frontend", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts as a usable upload workbench", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: /evidence-first contract workbench/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/upload contract/i)).toBeInTheDocument();
    expect(screen.getByText(/no analysis loaded/i)).toBeInTheDocument();
  });

  it("shows unsupported upload errors before calling the backend", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    render(<App />);

    uploadFile(new File(["bad"], "image.png", { type: "image/png" }));

    expect(await screen.findByText(/unsupported file/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads a contract, renders findings, and connects citations", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() => jsonResponse(uploadPayload))
      .mockImplementationOnce(() => jsonResponse(insightPayload));

    render(<App />);
    uploadFile(new File(["contract"], "credit.txt", { type: "text/plain" }));

    expect(await screen.findAllByText("analysis_test_1")).toHaveLength(2);
    expect(screen.getByText(/materially differs from the uploaded baseline/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /primary · chunk_1/i })).toHaveAttribute("href", "#citation-primary_chunk_1");
    expect(screen.getByText(/9 percent/i)).toBeInTheDocument();
  });

  it("keeps chat messages in the session and renders cited answers", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() => jsonResponse(uploadPayload))
      .mockImplementationOnce(() => jsonResponse(insightPayload))
      .mockImplementationOnce(() =>
        jsonResponse({
          schema_version: "contract_analyzer_grounded_answer_v1",
          answer_text: "The default appears in the cited evidence [chunk_1].",
          citations: ["chunk_1"],
          grounding_state: "grounded",
          warnings: []
        })
      );

    render(<App />);
    uploadFile(new File(["contract"], "credit.txt", { type: "text/plain" }));
    await user.type(await screen.findByLabelText(/ask a contract question/i), "Where is default defined?");
    await user.click(screen.getByRole("button", { name: /send question/i }));

    expect(await screen.findByText(/where is default defined/i)).toBeInTheDocument();
    expect(screen.getByText(/default appears in the cited evidence/i)).toBeInTheDocument();
    const chat = screen.getByLabelText(/persistent chat/i);
    expect(within(chat).getByText("chunk_1")).toBeInTheDocument();
  });

  it("shows recoverable backend failure states for unavailable chat", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() => jsonResponse(uploadPayload))
      .mockImplementationOnce(() => jsonResponse(insightPayload))
      .mockImplementationOnce(() => jsonResponse({ error: { message: "Proxy timed out." } }, 504));

    render(<App />);
    uploadFile(new File(["contract"], "credit.txt", { type: "text/plain" }));
    await user.type(await screen.findByLabelText(/ask a contract question/i), "Summarize risk");
    await user.click(screen.getByRole("button", { name: /send question/i }));

    expect(await screen.findByText(/request timed out: proxy timed out/i)).toBeInTheDocument();
  });

  it("renders low-evidence fallback when analysis endpoint is unavailable", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementationOnce(() => jsonResponse(uploadPayload)).mockImplementationOnce(() => jsonResponse({ error: { message: "Not found" } }, 404));

    render(<App />);
    uploadFile(new File(["contract"], "credit.txt", { type: "text/plain" }));

    expect(await screen.findByText(/analysis unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/upload accepted/i)).toBeInTheDocument();
    expect(screen.getByText(/analysis_endpoint_not_connected/i)).toBeInTheDocument();
  });
});
