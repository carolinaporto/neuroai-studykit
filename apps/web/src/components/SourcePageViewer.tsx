import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'

import { fetchSourceFile } from '../api/client'
import './SourcePageViewer.css'

// A lightweight overlay for "view the real page this quote is anchored to" — separate from
// SourcePreviewPanel (which browses a source's whole document as a side panel from the
// Sources page) because this is triggered from an anchor-quote box on a completely
// different page layout (Review, Quiz, Notes), not from a source list.
export function SourcePageViewer({
  sourceId,
  page,
  onClose,
}: {
  sourceId: string
  page?: number
  onClose: () => void
}) {
  const fileQuery = useQuery({
    queryKey: ['source-file', sourceId],
    queryFn: () => fetchSourceFile(sourceId),
  })

  // Same pattern as SourcePreviewPanel.tsx: useMemo computes the object URL during render
  // (no setState-in-effect), a paired effect only revokes it — an un-revoked object URL
  // leaks the blob for the page's lifetime.
  const fileUrl = useMemo(
    () => (fileQuery.data ? URL.createObjectURL(fileQuery.data) : null),
    [fileQuery.data],
  )
  useEffect(() => {
    return () => {
      if (fileUrl) URL.revokeObjectURL(fileUrl)
    }
  }, [fileUrl])

  // #page=N is a PDF-viewer URL fragment browsers honor natively (Chrome, Firefox, Safari's
  // built-in viewers all support it) — no PDF.js or other new dependency needed to jump
  // straight to the anchored page instead of opening at page 1.
  const viewerUrl = fileUrl && page ? `${fileUrl}#page=${page}` : fileUrl

  return (
    <div className="page-viewer-overlay" onClick={onClose}>
      <div className="page-viewer-panel" onClick={(e) => e.stopPropagation()}>
        <div className="page-viewer-header">
          <p className="label page-viewer-title">
            {page ? `Original — page ${page}` : 'Original document'}
          </p>
          <button type="button" className="page-viewer-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {fileQuery.isLoading && <p className="body">Loading…</p>}
        {fileQuery.isError && <p className="body">{(fileQuery.error as Error).message}</p>}
        {viewerUrl && (
          <iframe className="page-viewer-frame" src={viewerUrl} title="Original source page" />
        )}
      </div>
    </div>
  )
}
