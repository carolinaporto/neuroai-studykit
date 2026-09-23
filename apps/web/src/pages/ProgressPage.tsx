import { useQuery } from '@tanstack/react-query'

import { getProgress } from '../api/client'
import type { TopicMastery } from '../api/types'
import { useSession } from '../auth/useAuth'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import './ProgressPage.css'

// Same three-way split as apps/api/services/scheduling.py's score_to_grade — reusing the
// app's own existing thresholds for "how well do you know this" instead of inventing a new
// color scale for the same idea.
function scoreBand(score: number): 'good' | 'hard' | 'again' {
  if (score > 0.85) return 'good'
  if (score >= 0.6) return 'hard'
  return 'again'
}

function StatTile({
  label,
  value,
  emphasize,
}: {
  label: string
  value: number
  emphasize?: boolean
}) {
  return (
    <div className="progress-tile">
      <p className={`progress-tile-value${emphasize ? ' progress-tile-value-danger' : ''}`}>
        {value}
      </p>
      <p className="caption progress-tile-label">{label}</p>
    </div>
  )
}

function TopicRow({ topic }: { topic: TopicMastery }) {
  const hasScore = topic.avg_score !== null
  const pct = hasScore ? Math.round((topic.avg_score as number) * 100) : null
  const band = hasScore ? scoreBand(topic.avg_score as number) : null
  const title = hasScore
    ? `${topic.attempted_count} of ${topic.item_count} items answered — ${pct}% average`
    : `${topic.item_count} item${topic.item_count === 1 ? '' : 's'}, none answered yet`

  return (
    <li className="progress-topic-row">
      <div className="progress-topic-head">
        <span className="body-sm progress-topic-label">{topic.label ?? topic.slug}</span>
        <span className="caption progress-topic-meta">
          {hasScore ? `${pct}%` : 'Not studied yet'} · {topic.attempted_count}/{topic.item_count}{' '}
          answered
        </span>
      </div>
      <div className="progress-meter-track" title={title}>
        {hasScore && (
          <div
            className={`progress-meter-fill progress-meter-${band}`}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </li>
  )
}

export function ProgressPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false
  const query = useQuery({ queryKey: ['progress'], queryFn: getProgress, enabled: signedIn })

  if (!signedIn) return <LockedPlaceholder section="Progress" />
  if (query.isLoading) return <p className="body">Loading…</p>
  if (query.isError) return <p className="body">{(query.error as Error).message}</p>
  if (!query.data) return null

  const { topics, due } = query.data

  return (
    <div className="page">
      <h1 className="h1">Progress</h1>

      <div className="progress-tiles">
        <StatTile label="Never reviewed" value={due.never_reviewed} />
        <StatTile label="Overdue" value={due.overdue} emphasize={due.overdue > 0} />
        <StatTile label="Due today" value={due.due_today} />
        <StatTile label="Upcoming" value={due.upcoming} />
      </div>

      <h2 className="h2 progress-section-title">By topic</h2>
      {topics.length === 0 ? (
        <p className="body">No topics yet — generate and answer some questions first.</p>
      ) : (
        <ul className="progress-topic-list">
          {topics.map((topic) => (
            <TopicRow key={topic.slug} topic={topic} />
          ))}
        </ul>
      )}
    </div>
  )
}
