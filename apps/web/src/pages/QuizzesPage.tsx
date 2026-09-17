import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { listQuizWeeks, startQuiz } from '../api/client'
import { useSession } from '../auth/useAuth'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import { QuizCard } from '../components/QuizCard'
import './QuizzesPage.css'

export function QuizzesPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const weeksQuery = useQuery({
    queryKey: ['quiz-weeks'],
    queryFn: listQuizWeeks,
    enabled: signedIn,
  })

  const startMutation = useMutation({
    mutationFn: startQuiz,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['quiz-weeks'] })
      navigate(`/quizzes/${data.quiz_attempt_id}`)
    },
  })

  if (!signedIn) return <LockedPlaceholder section="Quizzes" />
  if (weeksQuery.isLoading) return <p className="body">Loading…</p>
  if (weeksQuery.isError) return <p className="body">{(weeksQuery.error as Error).message}</p>

  const weeks = weeksQuery.data ?? []

  return (
    <div>
      <h1 className="h1">Quizzes</h1>
      {weeks.length === 0 && (
        <p className="body">No quizzes available yet — upload and generate sources first.</p>
      )}
      <div className="quiz-grid">
        {weeks.map((week) => (
          <QuizCard
            key={week.week}
            week={week.week}
            itemCount={week.item_count}
            attempts={week.attempts}
            onStart={() => startMutation.mutate({ week: week.week, limit: 10 })}
            onReview={(attemptId) => navigate(`/quizzes/${attemptId}`)}
          />
        ))}
      </div>
      {startMutation.isError && <p className="caption">{(startMutation.error as Error).message}</p>}
    </div>
  )
}
