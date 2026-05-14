import type { Citation } from "../types";

interface Props {
  citation: Citation | null;
  onOpenInViewer?: (citation: Citation) => void;
}

function splitExcerpt(excerpt: string): { lead: string; context: string[] } {
  const normalized = excerpt.trim();
  if (!normalized) return { lead: "", context: [] };
  const match = normalized.match(/^(.+?[.!?])(?:\s|$)/);
  const lead = match ? match[1].trim() : normalized;
  const context = normalized
    .slice(lead.length)
    .trim()
    .split(/\n{1,2}/)
    .map((p) => p.trim())
    .filter(Boolean);
  return { lead, context };
}

export function CitationSourcePanel({ citation, onOpenInViewer }: Props) {
  const parts = splitExcerpt(citation?.excerpt ?? "");
  const hasPage = citation?.page_start != null;
  const pageLabel = hasPage
    ? citation!.page_start === citation!.page_end || citation!.page_end == null
      ? `p. ${citation!.page_start}`
      : `pp. ${citation!.page_start}–${citation!.page_end}`
    : "text span";

  return (
    <section className="panel citation-source-panel" aria-label="Citation source">
      <div className="section-heading tight" style={{ padding: "14px 16px 0" }}>
        <div>
          <p className="eyebrow">Evidence</p>
          <h2>Source citation</h2>
        </div>
      </div>

      <div className="citation-body">
        {!citation ? (
          <p className="muted" data-testid="citation-empty">
            Click a citation in the findings or evidence panel to inspect the source.
          </p>
        ) : (
          <>
            <div className="citation-meta-card" data-testid="citation-meta">
              <p className="citation-source-title">{citation.chunk_id}</p>
              <div className="citation-chips">
                <span className="citation-chip">{citation.document_role}</span>
                <span className="citation-chip" data-testid="citation-page-label">
                  {pageLabel}
                </span>
              </div>

              <div className="citation-detail-grid">
                <div>
                  <span className="detail-label">Role</span>
                  <span>{citation.document_role}</span>
                </div>
                <div>
                  <span className="detail-label">Page</span>
                  <span>{pageLabel}</span>
                </div>
                <div>
                  <span className="detail-label">Span</span>
                  <span>
                    {citation.span_start}–{citation.span_end}
                  </span>
                </div>
                {citation.pdf_url && (
                  <div>
                    <span className="detail-label">Source</span>
                    <span>PDF available</span>
                  </div>
                )}
              </div>

              {citation.pdf_url && (
                <button
                  className="open-viewer-btn"
                  data-testid="open-viewer-btn"
                  onClick={() => onOpenInViewer?.(citation)}
                >
                  Open in source viewer
                </button>
              )}
            </div>

            <div className="citation-excerpt-card">
              <p className="eyebrow" style={{ marginBottom: 6 }}>
                Highlighted excerpt
              </p>
              <blockquote className="citation-lead-quote" data-testid="citation-excerpt">
                {parts.lead || citation.excerpt}
              </blockquote>
              {parts.context.length > 0 && (
                <div className="citation-context">
                  <p className="eyebrow" style={{ marginTop: 10, marginBottom: 6 }}>
                    Supporting context
                  </p>
                  {parts.context.map((p, i) => (
                    <p key={i} className="citation-context-para">
                      {p}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
