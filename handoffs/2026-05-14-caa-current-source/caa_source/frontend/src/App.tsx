import {
  AlertTriangle,
  Bot,
  Database,
  FileText,
  Home,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  Search,
  Send,
  ShieldCheck,
  UploadCloud,
  UserCircle
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import {
  buildUploadFallbackPacket,
  fetchInsightPacket,
  sendChatMessage,
  uploadContract,
  validateUploadFile
} from "./apiClient";
import { CitationSourcePanel } from "./components/CitationSourcePanel";
import { SourcePdfViewerPanel } from "./components/SourcePdfViewerPanel";
import type { AnalysisSession, ChatMessage, Citation, Finding, InsightPacket, UiError, UploadStatus } from "./types";

function citationMap(packet: InsightPacket | null) {
  return new Map((packet?.citations ?? []).map((citation) => [citation.citation_id, citation]));
}

function ErrorBanner({ error }: { error: UiError | null }) {
  if (!error) return null;
  return (
    <div className="notice notice-error" role="alert">
      <AlertTriangle size={18} aria-hidden="true" />
      <div>
        <strong>{error.title}</strong>
        <span>{error.detail}</span>
      </div>
    </div>
  );
}

function UploadPanel({
  status,
  session,
  error,
  onUpload
}: {
  status: UploadStatus;
  session: AnalysisSession | null;
  error: UiError | null;
  onUpload: (file: File) => void;
}) {
  const [dragActive, setDragActive] = useState(false);
  const loading = status === "validating" || status === "uploading" || status === "analyzing";

  return (
    <section className="panel upload-panel" aria-label="Contract upload">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Contract Analyzer</p>
          <h1>Evidence-first contract workbench</h1>
        </div>
        <span className={`status-chip status-${status}`}>{status.replace("_", " ")}</span>
      </div>

      <label
        className={`drop-zone ${dragActive ? "drop-zone-active" : ""}`}
        onDragEnter={() => setDragActive(true)}
        onDragLeave={() => setDragActive(false)}
        onDrop={() => setDragActive(false)}
      >
        <input
          aria-label="Upload contract"
          type="file"
          accept=".txt,.pdf,.docx"
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            if (file) onUpload(file);
            event.currentTarget.value = "";
          }}
        />
        <UploadCloud size={28} aria-hidden="true" />
        <span>Upload TXT, PDF, or DOCX</span>
      </label>

      <ErrorBanner error={error} />

      <div className="session-strip">
        <div>
          <span>Session</span>
          <strong>{session?.analysisId ?? "No analysis yet"}</strong>
        </div>
        <div>
          <span>Document</span>
          <strong>{session?.filename ?? "Waiting for upload"}</strong>
        </div>
      </div>

      {loading && (
        <div className="notice">
          <Loader2 className="spin" size={18} aria-hidden="true" />
          <span>{status === "uploading" ? "Uploading contract..." : "Building analysis state..."}</span>
        </div>
      )}
    </section>
  );
}

function FindingPanel({ packet }: { packet: InsightPacket | null }) {
  const citations = useMemo(() => citationMap(packet), [packet]);
  const findings = packet?.findings ?? [];

  if (!packet) {
    return (
      <section className="panel state-panel">
        <FileText size={22} aria-hidden="true" />
        <h2>No analysis loaded</h2>
        <p>Upload a contract to open the evidence dashboard.</p>
      </section>
    );
  }

  if (packet.grounding === "not_grounded" || findings.length === 0) {
    return (
      <section className="panel state-panel">
        <AlertTriangle size={22} aria-hidden="true" />
        <h2>Low evidence</h2>
        <p>{packet.abstention_reason ?? "No cited findings are available for this session."}</p>
        {packet.warnings.length > 0 && <span className="warning-line">{packet.warnings.join(", ")}</span>}
      </section>
    );
  }

  return (
    <section className="panel findings-panel" aria-label="Findings">
      <div className="section-heading tight">
        <div>
          <p className="eyebrow">Findings</p>
          <h2>Risk, obligation, and comparison signals</h2>
        </div>
        <span className="status-chip status-complete">{packet.confidence}</span>
      </div>

      {packet.answer_text && <p className="answer-summary">{packet.answer_text}</p>}
      {packet.warnings.length > 0 && <span className="warning-line">{packet.warnings.join(", ")}</span>}

      <div className="finding-list">
        {findings.map((finding: Finding) => (
          <article className="finding-row" key={finding.finding_id}>
            <div className="finding-main">
              <span className={`severity severity-${finding.severity}`}>{finding.severity}</span>
              <strong>{finding.summary}</strong>
              <span>{finding.finding_type}</span>
            </div>
            <div className="citation-pills">
              {finding.citation_ids.map((citationId) => {
                const citation = citations.get(citationId);
                return (
                  <a href={`#citation-${citationId}`} key={citationId}>
                    {citation?.document_role ?? "source"} · {citation?.chunk_id ?? citationId}
                  </a>
                );
              })}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function EvidencePanel({
  packet,
  onSelectCitation
}: {
  packet: InsightPacket | null;
  onSelectCitation: (c: Citation) => void;
}) {
  return (
    <section className="panel evidence-panel" aria-label="Evidence citations">
      <div className="section-heading tight">
        <div>
          <p className="eyebrow">Evidence</p>
          <h2>Citations and source spans</h2>
        </div>
        <Search size={20} aria-hidden="true" />
      </div>

      {packet?.citations?.length ? (
        <div className="evidence-list">
          {packet.citations.map((citation) => (
            <article
              id={`citation-${citation.citation_id}`}
              className="evidence-row evidence-row-clickable"
              key={citation.citation_id}
              role="button"
              tabIndex={0}
              data-testid={`citation-row-${citation.chunk_id}`}
              aria-label={`View citation ${citation.chunk_id}`}
              onClick={() => onSelectCitation(citation)}
              onKeyDown={(e) => e.key === "Enter" && onSelectCitation(citation)}
            >
              <div className="evidence-meta">
                <strong>{citation.document_role}</strong>
                <span>{citation.chunk_id}</span>
                <span>
                  {citation.span_start}–{citation.span_end}
                </span>
                {citation.page_start != null && (
                  <span className="evidence-page-badge" data-testid="page-badge">
                    p.{citation.page_start}
                  </span>
                )}
              </div>
              <p>{citation.excerpt}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted">No citations have been returned by the current analysis state.</p>
      )}
    </section>
  );
}

function ChatPanel({
  session,
  messages,
  onSend
}: {
  session: AnalysisSession | null;
  messages: ChatMessage[];
  onSend: (message: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setDraft("");
  };

  return (
    <section className="panel chat-panel" aria-label="Persistent chat">
      <div className="section-heading tight">
        <div>
          <p className="eyebrow">Persistent chat</p>
          <h2>Ask against this session</h2>
        </div>
        <MessageSquare size={20} aria-hidden="true" />
      </div>

      <div className="chat-log" aria-live="polite">
        {messages.length === 0 ? (
          <p className="muted">Questions stay attached to the active analysis session.</p>
        ) : (
          messages.map((message) => (
            <article className={`chat-message chat-${message.role}`} key={message.id}>
              <strong>{message.role === "user" ? "You" : "Analyzer"}</strong>
              <p>{message.text}</p>
              {message.citations.length > 0 && <span className="chat-citations">{message.citations.join(", ")}</span>}
            </article>
          ))
        )}
      </div>

      <form className="chat-form" onSubmit={submit}>
        <input
          aria-label="Ask a contract question"
          value={draft}
          disabled={!session}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={session ? "Ask for a cited clause, risk, or obligation" : "Upload a contract first"}
        />
        <button type="submit" disabled={!session || !draft.trim()} aria-label="Send question">
          <Send size={18} aria-hidden="true" />
          <span>Send</span>
        </button>
      </form>
    </section>
  );
}

function MetricsRail({ packet, session }: { packet: InsightPacket | null; session: AnalysisSession | null }) {
  return (
    <aside className="metrics-rail" aria-label="Analysis summary">
      <div className="ctx-section-title">
        <span>Context</span>
        <strong>Live session</strong>
      </div>
      <div>
        <span>Analysis</span>
        <strong>{session?.analysisId ?? "pending"}</strong>
      </div>
      <div>
        <span>Grounding</span>
        <strong>{packet?.grounding ?? "idle"}</strong>
      </div>
      <div>
        <span>Findings</span>
        <strong>{packet?.findings.length ?? 0}</strong>
      </div>
      <div>
        <span>Citations</span>
        <strong>{packet?.citations.length ?? 0}</strong>
      </div>
      <div>
        <span>Data boundary</span>
        <strong>BYO upload</strong>
      </div>
    </aside>
  );
}

function ShellSidebar() {
  const navItems = [
    { icon: Home, label: "Home" },
    { icon: Bot, label: "Ask AiDa" },
    { icon: Database, label: "Data" },
    { icon: LayoutDashboard, label: "Agents", active: true },
    { icon: ShieldCheck, label: "Governance" }
  ];

  return (
    <aside className="shell-sidebar" aria-label="AiDa navigation">
      <div className="shell-brand">
        <div className="shell-mark">A</div>
        <div className="shell-brand-text">
          <strong>AIDA</strong>
          <span>Insight Marketplace</span>
        </div>
      </div>

      <nav className="shell-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <a className={`shell-nav-item ${item.active ? "active" : ""}`} href="#" key={item.label}>
              <Icon size={16} aria-hidden="true" />
              <span>{item.label}</span>
            </a>
          );
        })}
      </nav>

      <div className="shell-sidebar-card">
        <span>Agent</span>
        <strong>Contract Analyzer</strong>
      </div>

      <div className="shell-profile">
        <div className="shell-avatar">
          <UserCircle size={18} aria-hidden="true" />
        </div>
        <div>
          <strong>John Doe</strong>
          <span>john.doe@mufg.com</span>
        </div>
      </div>
    </aside>
  );
}

export default function App() {
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [session, setSession] = useState<AnalysisSession | null>(null);
  const [packet, setPacket] = useState<InsightPacket | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [viewerCitation, setViewerCitation] = useState<Citation | null>(null);

  const handleUpload = async (file: File) => {
    setStatus("validating");
    setError(null);
    const validationError = validateUploadFile(file);
    if (validationError) {
      setStatus("error");
      setError(validationError);
      return;
    }

    setStatus("uploading");
    try {
      const upload = await uploadContract(file);
      const nextSession = {
        analysisId: upload.analysis_id,
        sessionId: upload.session_id,
        filename: upload.filename,
        upload
      };
      setSession(nextSession);
      setMessages([]);
      setSelectedCitation(null);
      setViewerCitation(null);
      setStatus("analyzing");

      try {
        const insightPacket = await fetchInsightPacket(upload.analysis_id);
        // Insights is blocked for single-doc (requires a baseline comparison).
        // Fall back to the upload excerpt so the EvidencePanel shows content.
        setPacket(insightPacket.citations?.length ? insightPacket : buildUploadFallbackPacket(upload));
      } catch (analysisError) {
        setPacket(buildUploadFallbackPacket(upload));
        setError(analysisError as UiError);
      }
      setStatus("complete");
    } catch (uploadError) {
      setStatus("error");
      setError(uploadError as UiError);
    }
  };

  const handleChat = async (text: string) => {
    if (!session) return;
    const userMessage: ChatMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      text,
      citations: [],
      state: "sent"
    };
    setMessages((current) => [...current, userMessage]);
    try {
      const response = await sendChatMessage(session.analysisId, text);
      const citations = response.citations ?? response.citation_ids ?? [];
      // If chat returned full citation objects, merge them into the packet so
      // EvidencePanel shows them (single-doc path: /insights returns empty).
      if (response.citation_objects?.length) {
        setPacket((prev) => ({
          ...(prev ?? {
            schema_version: "contract_analyzer_insight_answer_packet_v1" as const,
            query: text,
            findings: [],
            chunks: [],
            source_documents: [],
            confidence: "medium",
            grounding: "grounded",
            answer_text: "",
            warnings: [],
            abstention_reason: null
          }),
          citations: response.citation_objects!,
          grounding: "grounded",
        }));
      }
      setMessages((current) => [
        ...current,
        {
          id: `assistant_${Date.now()}`,
          role: "assistant",
          text: response.answer_text || response.abstention_reason || "No supported answer was returned.",
          citations,
          state: response.answer_text ? "grounded" : "abstained"
        }
      ]);
    } catch (chatError) {
      const nextError = chatError as UiError;
      setMessages((current) => [
        ...current,
        {
          id: `assistant_error_${Date.now()}`,
          role: "assistant",
          text: `${nextError.title}: ${nextError.detail}`,
          citations: [],
          state: "error"
        }
      ]);
    }
  };

  return (
    <div className="app-shell dark">
      <header className="shell-topbar">
        <div className="mufg-wordmark">MUFG</div>
        <span className="shell-topbar-sep" aria-hidden="true" />
        <strong>Data & Agentic Insight Marketplace</strong>
        <span className="topbar-badge">Contract Analyzer</span>
      </header>

      <div className="shell-layout">
        <ShellSidebar />
        <main className="shell-main">
            <UploadPanel status={status} session={session} error={error} onUpload={handleUpload} />
            <div className="workspace-grid">
              <FindingPanel packet={packet} />
              <EvidencePanel
                packet={packet}
                onSelectCitation={(c) => {
                  setSelectedCitation(c);
                  // Only open viewer if PDF is available
                  if (c.pdf_url) setViewerCitation(c);
                }}
              />
              <ChatPanel session={session} messages={messages} onSend={handleChat} />
            </div>
            {selectedCitation && (
              <div className="provenance-panels" data-testid="provenance-panels">
                <CitationSourcePanel
                  citation={selectedCitation}
                  onOpenInViewer={(c) => setViewerCitation(c)}
                />
                <SourcePdfViewerPanel citation={viewerCitation} />
              </div>
            )}
          </main>
        <MetricsRail packet={packet} session={session} />
      </div>
    </div>
  );
}
