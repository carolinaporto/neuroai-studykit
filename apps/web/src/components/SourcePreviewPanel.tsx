import { useQuery } from '@tanstack/react-query'

import { getSource, sourceFileUrl } from '../api/client'
import { formatLocator } from '../lib/locator'
import './SourcePreviewPanel.css'

// Only a PDF can be embedded natively in the browser — .pptx and transcripts fall back to
// the extracted chunk text below, plus a download link for the real file.
const EMBEDDABLE_KINDS = new Set(['lecture_pdf', 'paper'])

export function SourcePreviewPanel({
  sourceId,
  onClose,
}: {
  sourceId: string
  onClose: () => void
}) {
  const query = useQuery({
    queryKey: ['source', sourceId],
    queryFn: () => getSource(sourceId),
  })

  return (
    <aside className="source-preview">
      <div className="source-preview-header">
        <h2 className="h3 source-preview-title">{query.data?.title ?? 'Loading…'}</h2>
        <button
          type="button"
          className="source-preview-close"
          onClick={onClose}
          aria-label="Close preview"
        >
          ×
        </button>
      </div>

      {query.isLoading && <p className="body">Loading…</p>}
      {query.isError && <p className="body">{(query.error as Error).message}</p>}

      {query.data && (
        <>
          <a
            className="source-preview-download caption"
            href={sourceFileUrl(sourceId)}
            target="_blank"
            rel="noreferrer"
          >
            Open original file
          </a>

          {EMBEDDABLE_KINDS.has(query.data.kind) ? (
            <iframe
              className="source-preview-frame"
              src={sourceFileUrl(sourceId)}
              title={query.data.title}
            />
          ) : (
            <div className="source-preview-text">
              {query.data.chunks.map((chunk) => (
                <div key={chunk.ordinal} className="source-preview-chunk">
                  <p className="caption source-preview-locator">
                    {chunk.locators.map((loc) => formatLocator(loc)).join(' · ')}
                  </p>
                  <p className="body-sm">{chunk.text}</p>
                </div>
              ))}
              {query.data.chunks.length === 0 && (
                <p className="body-sm">No extracted text for this source.</p>
              )}
            </div>
          )}
        </>
      )}
    </aside>
  )
}
