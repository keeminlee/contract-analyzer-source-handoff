import type { Citation } from "../types";

interface Props {
  citation: Citation | null;
}

function buildViewerUrl(citation: Citation): string {
  if (!citation.pdf_url) return "";
  const page = citation.page_start ?? 1;
  const searchText = (citation.excerpt ?? "").trim().slice(0, 140);
  const searchParam = searchText ? `&search=${encodeURIComponent(searchText)}` : "";
  // Use Vite proxy path (/api) so browser doesn't need CORS for blob URL.
  // The backend route is /api/v1/analyses/{id}/pdf.
  return `${citation.pdf_url}#page=${page}${searchParam}`;
}

export function SourcePdfViewerPanel({ citation }: Props) {
  const hasSource = Boolean(citation?.pdf_url);

  return (
    <section className="panel source-viewer-panel" aria-label="Source viewer" data-testid="source-viewer-panel">
      <div className="section-heading tight" style={{ padding: "14px 16px 0" }}>
        <div>
          <p className="eyebrow">Source viewer</p>
          <h2>{citation ? citation.chunk_id : "No source selected"}</h2>
        </div>
      </div>

      {!hasSource ? (
        <div className="viewer-placeholder" data-testid="viewer-placeholder">
          {citation
            ? "This citation has no PDF source available."
            : "Select a citation to view the source document."}
        </div>
      ) : (
        <div className="viewer-wrap">
          <div className="viewer-toolbar">
            <span data-testid="viewer-page-label">
              Page {citation!.page_start ?? 1}
            </span>
            <span className="viewer-hint">Jump + search highlighting</span>
          </div>
          <div className="pdf-canvas-wrap" data-testid="pdf-canvas-wrap">
            <iframe
              key={`${citation!.chunk_id}_${citation!.page_start ?? 1}`}
              src={buildViewerUrl(citation!)}
              title={`Source: ${citation!.chunk_id}`}
              className="pdf-iframe"
              data-testid="pdf-iframe"
            />
          </div>
        </div>
      )}
    </section>
  );
}
