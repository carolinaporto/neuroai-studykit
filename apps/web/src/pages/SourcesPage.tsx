import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { listSources } from '../api/client'
import { useSession } from '../auth/useAuth'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import { SourceItem, SourceList } from '../components/SourceItem'
import { SourcePreviewPanel } from '../components/SourcePreviewPanel'
import { SourceUploadPanel } from '../components/SourceUploadPanel'
import { WeekHeader } from '../components/WeekHeader'
import './SourcesPage.css'

const KIND_LABEL: Record<string, string> = {
  slides: 'Slides',
  transcript: 'Video',
  paper: 'Reading',
  lecture_pdf: 'Lecture',
  notes: 'Notes',
}

function formatMeta(
  kind: string,
  pageCount: number | null,
  durationSeconds: number | null,
): string {
  const label = KIND_LABEL[kind] ?? kind
  if (durationSeconds != null) return `${label} · ${Math.round(durationSeconds / 60)} min`
  if (pageCount != null) return `${label} · ${pageCount} pages`
  return label
}

const DEFAULT_PREVIEW_WIDTH = 560
const MIN_PREVIEW_WIDTH = 340
const MIN_MAIN_WIDTH = 360

export function SourcesPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false
  const query = useQuery({ queryKey: ['sources'], queryFn: listSources, enabled: signedIn })
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null)
  const [previewWidth, setPreviewWidth] = useState(DEFAULT_PREVIEW_WIDTH)
  const isDraggingRef = useRef(false)

  // Drag-to-resize the preview panel — width tracked as plain px, clamped between a
  // minimum for the panel and a minimum left for the source list. Global listeners while
  // dragging so the drag keeps tracking the mouse even if it leaves the handle itself.
  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!isDraggingRef.current) return
      const next = window.innerWidth - e.clientX
      const max = window.innerWidth - MIN_MAIN_WIDTH
      setPreviewWidth(Math.min(Math.max(next, MIN_PREVIEW_WIDTH), Math.max(max, MIN_PREVIEW_WIDTH)))
    }
    function onMouseUp() {
      if (isDraggingRef.current) {
        isDraggingRef.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  function startResize(e: React.MouseEvent) {
    e.preventDefault()
    isDraggingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  if (!signedIn) return <LockedPlaceholder section="Sources" />

  const weeks = query.data ?? []

  return (
    <div className="sources-layout">
      <div className="sources-main">
        <h1 className="h1">Sources</h1>
        <SourceUploadPanel />
        {query.isLoading && <p className="body">Loading…</p>}
        {query.isError && <p className="body">{(query.error as Error).message}</p>}
        {!query.isLoading && !query.isError && weeks.length === 0 && (
          <p className="body">No sources uploaded yet.</p>
        )}
        {weeks.map((week) => (
          <section key={week.week}>
            <WeekHeader
              week={week.week}
              title={week.title ?? `Week ${week.week}`}
              meta={`${week.sources.length} source${week.sources.length === 1 ? '' : 's'}`}
            />
            <SourceList>
              {week.sources.map((source) => (
                <SourceItem
                  key={source.id}
                  kind={source.kind}
                  title={source.title}
                  meta={formatMeta(source.kind, source.page_count, source.duration_seconds)}
                  isActive={selectedSourceId === source.id}
                  onClick={() => setSelectedSourceId(source.id)}
                />
              ))}
            </SourceList>
          </section>
        ))}
      </div>

      {selectedSourceId && (
        <>
          <div
            className="sources-resize-handle"
            onMouseDown={startResize}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize preview panel"
          />
          <SourcePreviewPanel
            sourceId={selectedSourceId}
            widthPx={previewWidth}
            onClose={() => setSelectedSourceId(null)}
          />
        </>
      )}
    </div>
  )
}
