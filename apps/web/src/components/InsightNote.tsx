import { AccessBadge } from './AccessBadge'
import { ExternalLinkIcon } from './icons'
import './InsightNote.css'

interface InsightNoteProps {
  disciplines: string[]
  isPublic: boolean
  title: string
  body: string | null
  url: string | null
  week: number | null
  createdAt: string
}

export function InsightNote({ disciplines, isPublic, title, body, url, week, createdAt }: InsightNoteProps) {
  return (
    <div className="in-card">
      <div className="in-top">
        <span className="in-disc tag">{disciplines.join(' · ')}</span>
        <AccessBadge isPublic={isPublic} />
      </div>
      <div className="h3 in-title">{title}</div>
      {body && <p className="body-sm in-excerpt">{body}</p>}
      {url && (
        <a className="in-link" href={url} target="_blank" rel="noreferrer">
          <ExternalLinkIcon />
          Open document
        </a>
      )}
      {week != null && (
        <div className="caption in-foot">
          Linked to Week {week} · {new Date(createdAt).toLocaleDateString()}
        </div>
      )}
    </div>
  )
}
