export type UploadStatus = "idle" | "validating" | "uploading" | "analyzing" | "complete" | "error";

export type ApiErrorCode =
  | "unsupported_extension"
  | "oversized_file"
  | "empty_file"
  | "upload_failed"
  | "analysis_unavailable"
  | "chat_unavailable"
  | "auth_failure"
  | "timeout";

export interface UiError {
  code: ApiErrorCode;
  title: string;
  detail: string;
}

export interface UploadResponse {
  schema_version: "contract_analyzer_upload_v1";
  analysis_id: string;
  session_id: string;
  filename: string;
  extension: string;
  status: "accepted";
  bronze?: {
    text?: { full?: string; char_count?: number };
    extracted_text?: string;
    source?: Record<string, unknown>;
  };
  artifacts?: Record<string, unknown>;
}

export interface Citation {
  citation_id: string;
  document_role: "primary" | "baseline" | string;
  analysis_id?: string;
  chunk_id: string;
  source_node_ids?: string[];
  span_start: number;
  span_end: number;
  excerpt: string;
  source_document?: Record<string, unknown>;
  // Layer 3: page provenance and PDF serving
  page_start?: number | null;
  page_end?: number | null;
  pdf_url?: string | null;
}

export interface Finding {
  finding_id: string;
  finding_type: string;
  severity: "info" | "low" | "medium" | "high" | string;
  summary: string;
  citation_ids: string[];
  confidence?: string;
}

export interface InsightPacket {
  schema_version: "contract_analyzer_insight_answer_packet_v1";
  query: string;
  findings: Finding[];
  citations: Citation[];
  chunks: Array<{
    citation_id: string;
    document_role: string;
    chunk_id: string;
    span_start: number;
    span_end: number;
    excerpt: string;
  }>;
  source_documents: Array<{ role: string; analysis_id?: string; source?: Record<string, unknown> }>;
  confidence: "low" | "medium" | "high" | string;
  grounding: "grounded" | "not_grounded" | "grounded_no_diff" | string;
  answer_text: string;
  warnings: string[];
  abstention_reason?: string | null;
  trace_metadata?: Record<string, unknown>;
}

export interface AnalysisSession {
  analysisId: string;
  sessionId: string;
  filename: string;
  upload: UploadResponse;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations: string[];
  state: "sent" | "grounded" | "abstained" | "error";
}

export interface ChatResponse {
  schema_version: "contract_analyzer_grounded_answer_v1" | "contract_analyzer_insight_answer_packet_v1";
  answer_text: string;
  citations?: string[];
  citation_ids?: string[];
  citation_objects?: Citation[];
  grounding_state?: string;
  grounding?: string;
  abstention_reason?: string | null;
  warnings?: string[];
}
