import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { listReviewQueue } from '../api/client'
import { useSession } from '../auth/useAuth'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import { ReviewCard } from '../components/ReviewCard'
import './ReviewPage.css'

export function ReviewPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false
  const navigate = useNavigate()
  const query = useQuery({
    queryKey: ['review-queue'],
    queryFn: listReviewQueue,
    enabled: signedIn,
  })

  if (!signedIn) return <LockedPlaceholder section="Review" />
  if (query.isLoading) return <p className="body">Loading…</p>
  if (query.isError) return <p className="body">{(query.error as Error).message}</p>

  const weeks = query.data ?? []

  return (
    <div className="page">
      <h1 className="h1">Review</h1>
      <p className="body-sm review-lede">
        A question only reaches a quiz once it's approved or edited here — nothing generated skips
        this.
      </p>
      {weeks.length === 0 && (
        <p className="body">
          Nothing to review right now — every generated question has been decided.
        </p>
      )}
      <div className="review-grid">
        {weeks.map((week) => (
          <ReviewCard
            key={week.week}
            week={week.week}
            title={week.title}
            draftCount={week.items.length}
            onReview={() => navigate(`/review/${week.week}`)}
          />
        ))}
      </div>
    </div>
  )
}
