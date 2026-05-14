import type { ChatResponse, InsightPacket, UiError, UploadResponse } from "./types";

const API_BASE = import.meta.env.VITE_CONTRACT_ANALYZER_API_BASE ?? "";
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = [".txt", ".pdf", ".docx"];

export function validateUploadFile(file: File): UiError | null {
  const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    return {
      code: "unsupported_extension",
      title: "Unsupported file",
      detail: "Upload a TXT, PDF, or DOCX contract."
    };
  }
  if (file.size === 0) {
    return {
      code: "empty_file",
      title: "Empty file",
      detail: "The selected file has no extractable bytes."
    };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      code: "oversized_file",
      title: "File too large",
      detail: "Use a contract under 25 MB for this v1 upload flow."
    };
  }
  return null;
}

async function parseError(response: Response, fallbackCode: UiError["code"], fallbackTitle: string): Promise<UiError> {
  let detail = response.statusText || "Request failed.";
  try {
    const payload = await response.json();
    detail = payload?.error?.message ?? detail;
  } catch {
    // Keep HTTP status text when a backend error body is not JSON.
  }
  if (response.status === 401 || response.status === 403) {
    return { code: "auth_failure", title: "Authentication failed", detail };
  }
  if (response.status === 408 || response.status === 504) {
    return { code: "timeout", title: "Request timed out", detail };
  }
  return { code: fallbackCode, title: fallbackTitle, detail };
}

export async function uploadContract(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/v1/uploads`, {
    method: "POST",
    body: form
  });
  if (!response.ok) {
    throw await parseError(response, "upload_failed", "Upload failed");
  }
  return response.json() as Promise<UploadResponse>;
}

export async function fetchInsightPacket(analysisId: string): Promise<InsightPacket> {
  const response = await fetch(`${API_BASE}/api/v1/analyses/${analysisId}/insights`);
  if (!response.ok) {
    throw await parseError(response, "analysis_unavailable", "Analysis unavailable");
  }
  return response.json() as Promise<InsightPacket>;
}

export async function sendChatMessage(analysisId: string, message: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/api/v1/analyses/${analysisId}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query: message })
  });
  if (!response.ok) {
    throw await parseError(response, "chat_unavailable", "Chat unavailable");
  }
  return response.json() as Promise<ChatResponse>;
}

export function buildUploadFallbackPacket(upload: UploadResponse): InsightPacket {
  const fullText = upload.bronze?.text?.full ?? upload.bronze?.extracted_text ?? "";
  const excerpt = fullText.slice(0, 700);
  return {
    schema_version: "contract_analyzer_insight_answer_packet_v1",
    query: "Upload intake",
    findings: excerpt
      ? [
          {
            finding_id: "upload_intake",
            finding_type: "upload_state",
            severity: "info",
            summary: "Document was accepted and bronze text is available for downstream analysis.",
            citation_ids: ["upload_excerpt"]
          }
        ]
      : [],
    citations: excerpt
      ? [
          {
            citation_id: "upload_excerpt",
            document_role: "primary",
            analysis_id: upload.analysis_id,
            chunk_id: "bronze_excerpt_1",
            source_node_ids: [],
            span_start: 0,
            span_end: excerpt.length,
            excerpt,
            source_document: { name: upload.filename, extension: upload.extension }
          }
        ]
      : [],
    chunks: excerpt
      ? [
          {
            citation_id: "upload_excerpt",
            document_role: "primary",
            chunk_id: "bronze_excerpt_1",
            span_start: 0,
            span_end: excerpt.length,
            excerpt
          }
        ]
      : [],
    source_documents: [{ role: "primary", analysis_id: upload.analysis_id, source: { name: upload.filename } }],
    confidence: excerpt ? "low" : "low",
    grounding: excerpt ? "grounded" : "not_grounded",
    answer_text: excerpt ? "Upload accepted. Full insight analysis is pending the live analysis endpoint [upload_excerpt]." : "",
    warnings: ["analysis_endpoint_not_connected"],
    abstention_reason: excerpt ? null : "No extractable upload evidence is available.",
    trace_metadata: {
      source: "live_upload_response",
      note: "Derived from upload API response, not static mock report data."
    }
  };
}
