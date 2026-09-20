import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { deleteSource, getSource, sourceFileUrl } from '../api/client'
import { formatLocator } from '../lib/locator'
import { Button } from './Button'
import './SourcePreviewPanel.css'

// Only a PDF can be embedded natively in the browser — .pptx and transcripts fall back to
// the extracted chunk text below, plus a download link for the real file.
const EMBEDDABLE_KINDS = new Set(['lecture_pdf', 'paper'])

export function SourcePreviewPanel({
  sourceId,
  widthPx,
  onClose,
}: {
  sourceId: string
  widthPx: number
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['source', sourceId],
    queryFn: () => getSource(sourceId),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteSource(sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      onClose()
    },
  })

  function handleDelete() {
    const title = query.data?.title ?? 'this source'
    if (
      window.confirm(
        `Delete "${title}"? This removes it and every question generated from it. This can't be undone.`,
      )
    ) {
      deleteMutation.mutate()
    }
  }

  return (
    <aside className="source-preview" style={{ width: widthPx }}>
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
          <div className="source-preview-actions">
            <a
              className="source-preview-download caption"
              href={sourceFileUrl(sourceId)}
              target="_blank"
              rel="noreferrer"
            >
              Open original file
            </a>
            <Button variant="danger" onClick={handleDelete} disabled={deleteMutation.isPending}>
              {deleteMutation.isPending ? 'Deleting…' : 'Delete source'}
            </Button>
          </div>
          {deleteMutation.isError && (
            <p className="caption source-preview-error">
              {(deleteMutation.error as Error).message}
            </p>
          )}

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
