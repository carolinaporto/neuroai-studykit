import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'

import { deleteSource, fetchSourceFile, getSource } from '../api/client'
import { formatLocator } from '../lib/locator'
import { EMBEDDABLE_KINDS } from '../lib/sourceKinds'
import { Button } from './Button'
import { useToast } from './toastContext'
import './SourcePreviewPanel.css'

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
  const toast = useToast()
  const query = useQuery({
    queryKey: ['source', sourceId],
    queryFn: () => getSource(sourceId),
  })

  // The file endpoint requires auth, so it can't be a plain <iframe>/<a> src (the browser's
  // own request for those can't carry an Authorization header) — fetched here instead, with
  // the token, then handed to the DOM as a local object URL.
  const fileQuery = useQuery({
    queryKey: ['source-file', sourceId],
    queryFn: () => fetchSourceFile(sourceId),
  })

  // useMemo computes the URL during render (no setState-in-effect); the effect below only
  // revokes it, never assigns anything — revoked whenever the blob changes (a new
  // sourceId) or the panel unmounts, since an un-revoked object URL leaks the blob for the
  // page's lifetime.
  const fileUrl = useMemo(
    () => (fileQuery.data ? URL.createObjectURL(fileQuery.data) : null),
    [fileQuery.data],
  )
  useEffect(() => {
    return () => {
      if (fileUrl) URL.revokeObjectURL(fileUrl)
    }
  }, [fileUrl])

  const deleteMutation = useMutation({
    mutationFn: () => deleteSource(sourceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      toast.success('Source deleted')
      onClose()
    },
    onError: (error) => toast.error((error as Error).message),
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
            {fileUrl && (
              <a className="source-preview-download caption" href={fileUrl} download>
                Open original file
              </a>
            )}
            <Button variant="danger" onClick={handleDelete} disabled={deleteMutation.isPending}>
              {deleteMutation.isPending ? 'Deleting…' : 'Delete source'}
            </Button>
          </div>

          {EMBEDDABLE_KINDS.has(query.data.kind) ? (
            fileUrl ? (
              <iframe className="source-preview-frame" src={fileUrl} title={query.data.title} />
            ) : (
              <p className="body-sm">Loading preview…</p>
            )
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
