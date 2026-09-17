import type { QuizAttemptOut } from '../api/types'
import { CheckTargetIcon, LockIcon } from './icons'
import './QuizCard.css'

interface QuizCardProps {
  week: number
  itemCount: number
  attempts: QuizAttemptOut[]
  onStart: () => void
  onReview: (attemptId: string) => void
}

// Design's QuizCard was drawn as one slot per week (locked/available/completed,
// mutually exclusive). Adapted here for multiple attempts per week, per this project's
// discussion: "available" once itemCount > 0, always start-able, with attempt history
// (in-progress/completed) listed underneath rather than replacing the card.
export function QuizCard({ week, itemCount, attempts, onStart, onReview }: QuizCardProps) {
  const locked = itemCount === 0

  return (
    <div className="qc-card">
      <div className="qc-top">
        <span className="qc-wk tag">WK {String(week).padStart(2, '0')}</span>
        <span className="caption qc-eyebrow">Recall check</span>
      </div>
      <div className="h3 qc-title">Week {week} Quiz</div>

      {locked ? (
        <>
          <div className="qc-body">
            <div className="qc-icon qc-icon-locked">
              <LockIcon />
            </div>
            <div className="caption qc-meta">Sources not uploaded yet</div>
          </div>
          <button className="qc-btn qc-btn-disabled button" disabled>
            <LockIcon />
            Locked
          </button>
        </>
      ) : (
        <>
          <div className="qc-body">
            <div className="qc-icon qc-icon-ready">
              <CheckTargetIcon />
            </div>
            <div className="caption qc-meta">{itemCount} questions</div>
          </div>
          <button className="qc-btn qc-btn-primary button" onClick={onStart}>
            Start quiz
          </button>
        </>
      )}

      {attempts.length > 0 && (
        <ul className="qc-history">
          {attempts.map((attempt) => (
            <li key={attempt.id} className="qc-history-row">
              <span className="caption qc-history-label">
                {attempt.status === 'completed'
                  ? `${Math.round((attempt.score ?? 0) * attempt.item_count)}/${attempt.item_count}`
                  : 'In progress'}
              </span>
              <button className="qc-history-link" onClick={() => onReview(attempt.id)}>
                {attempt.status === 'completed' ? 'Review answers' : 'Continue'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
