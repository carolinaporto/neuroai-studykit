import { ReviewIcon } from './icons'
import './ReviewCard.css'

// Landing card for one week's review queue — same tokens as QuizCard, simpler state:
// there's no "locked" or "completed", just a draft count and a way in.
export function ReviewCard({
  week,
  title,
  draftCount,
  onReview,
}: {
  week: number
  title: string | null
  draftCount: number
  onReview: () => void
}) {
  return (
    <div className="rc-card">
      <div className="rc-top">
        <span className="rc-wk tag">WK {String(week).padStart(2, '0')}</span>
        <span className="caption rc-eyebrow">Needs review</span>
      </div>
      <div className="h3 rc-title">{title ?? `Week ${week}`}</div>

      <div className="rc-body">
        <div className="rc-icon">
          <ReviewIcon />
        </div>
        <div className="caption rc-meta">
          {draftCount} draft{draftCount === 1 ? '' : 's'}
        </div>
      </div>

      <button className="rc-btn button" onClick={onReview}>
        Review
      </button>
    </div>
  )
}
