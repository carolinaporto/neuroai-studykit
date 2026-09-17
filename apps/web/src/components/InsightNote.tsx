import { AccessBadge } from './AccessBadge'
import './InsightNote.css'

interface InsightNoteProps {
  disciplines: string[]
  isPublic: boolean
  title: string
  body: string
  week: number | null
  createdAt: string
}

export function InsightNote({
  disciplines,
  isPublic,
  title,
  body,
  week,
  createdAt,
}: InsightNoteProps) {
  return (
    <div className="in-card">
      <div className="in-top">
        <span className="in-disc tag">{disciplines.join(' · ')}</span>
        <AccessBadge isPublic={isPublic} />
      </div>
      <div className="h3 in-title">{title}</div>
      <p className="body-sm in-excerpt">{body}</p>
      {week != null && (
        <div className="caption in-foot">
          Linked to Week {week} · {new Date(createdAt).toLocaleDateString()}
        </div>
      )}
    </div>
  )
}
