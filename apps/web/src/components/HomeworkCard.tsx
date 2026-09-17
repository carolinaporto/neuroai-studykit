import type { HomeworkOut } from '../api/types'
import { AccessBadge } from './AccessBadge'
import { ExternalLinkIcon, GithubIcon } from './icons'
import './HomeworkCard.css'

export function HomeworkCard({
  week,
  title,
  disciplines,
  description,
  code_url,
  live_url,
}: HomeworkOut) {
  return (
    <div className="hc-card">
      <div className="hc-top">
        <span className="hc-wk tag">WK {String(week).padStart(2, '0')}</span>
        <AccessBadge isPublic />
      </div>
      <div className="h3 hc-title">{title}</div>
      <div className="hc-tags">
        {disciplines.map((d) => (
          <span key={d} className="hc-tag tag">
            {d}
          </span>
        ))}
      </div>
      <p className="body-sm hc-excerpt">{description}</p>
      {(code_url || live_url) && (
        <div className="caption hc-foot">
          {code_url && (
            <a className="hc-link" href={code_url} target="_blank" rel="noreferrer">
              <GithubIcon />
              View code
            </a>
          )}
          {live_url && (
            <a className="hc-link" href={live_url} target="_blank" rel="noreferrer">
              <ExternalLinkIcon />
              Live site
            </a>
          )}
        </div>
      )}
    </div>
  )
}
