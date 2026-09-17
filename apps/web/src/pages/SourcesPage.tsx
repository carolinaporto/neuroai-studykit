import { useQuery } from '@tanstack/react-query'

import { listSources } from '../api/client'
import { useSession } from '../auth/useAuth'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import { SourceItem, SourceList } from '../components/SourceItem'
import { SourceUploadPanel } from '../components/SourceUploadPanel'
import { WeekHeader } from '../components/WeekHeader'

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

export function SourcesPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false
  const query = useQuery({ queryKey: ['sources'], queryFn: listSources, enabled: signedIn })

  if (!signedIn) return <LockedPlaceholder section="Sources" />

  const weeks = query.data ?? []

  return (
    <div>
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
              />
            ))}
          </SourceList>
        </section>
      ))}
    </div>
  )
}
