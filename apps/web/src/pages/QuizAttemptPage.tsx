import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { reviewQuiz, submitStudyAnswer } from '../api/client'
import type { QuizReviewItem, RubricHit, StudyAnswerResponse } from '../api/types'
import { Button } from '../components/Button'
import { formatLocator } from '../lib/locator'
import './QuizAttemptPage.css'

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return el?.tagName === 'TEXTAREA' || el?.tagName === 'INPUT'
}

function RubricList({ hits }: { hits: RubricHit[] }) {
  return (
    <ul className="rubric-list">
      {hits.map((hit) => (
        <li
          key={hit.point_id}
          className={`rubric-hit ${hit.covered ? 'rubric-hit-covered' : 'rubric-hit-missed'}`}
        >
          <p className="body-sm">
            {hit.covered ? '✓' : '✗'} {hit.point}
          </p>
        </li>
      ))}
    </ul>
  )
}

function AnswerResult({ result }: { result: StudyAnswerResponse }) {
  return (
    <div className="quiz-result">
      <p className="body">
        <strong>Score: {Math.round(result.score * 100)}%</strong>
        {result.cached && <span className="caption"> (cache)</span>}
      </p>
      <RubricList hits={result.rubric_hits} />
      {result.misconceptions.length > 0 && (
        <p className="body-sm">Misconceptions: {result.misconceptions.join('; ')}</p>
      )}
      <p className="body-sm">{result.feedback_md}</p>
      <p className="body-sm">
        <strong>Reference answer:</strong> {result.reference_answer}
      </p>
      {result.source.map((excerpt, i) => (
        <p key={i} className="caption quiz-source">
          {formatLocator(excerpt.locator)} — "{excerpt.quote}"
        </p>
      ))}
    </div>
  )
}

function ReviewItemCard({ item }: { item: QuizReviewItem }) {
  return (
    <div className="quiz-result">
      <p className="body">
        <strong>{item.prompt}</strong>
      </p>
      <p className="body-sm">Your answer: {item.response_text}</p>
      <RubricList hits={item.rubric_hits} />
      <p className="body-sm">
        <strong>Reference answer:</strong> {item.reference_answer}
      </p>
      {item.source.map((excerpt, i) => (
        <p key={i} className="caption quiz-source">
          {formatLocator(excerpt.locator)} — "{excerpt.quote}"
        </p>
      ))}
    </div>
  )
}

export function QuizAttemptPage() {
  const { attemptId } = useParams<{ attemptId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [responseText, setResponseText] = useState('')
  const [lastResult, setLastResult] = useState<StudyAnswerResponse | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const query = useQuery({
    queryKey: ['quiz-attempt', attemptId],
    queryFn: () => reviewQuiz(attemptId as string),
    enabled: attemptId !== undefined,
  })

  const answerMutation = useMutation({
    mutationFn: submitStudyAnswer,
    onSuccess: (result) => {
      setLastResult(result)
      setResponseText('')
      queryClient.invalidateQueries({ queryKey: ['quiz-attempt', attemptId] })
      queryClient.invalidateQueries({ queryKey: ['quiz-weeks'] })
    },
  })

  const remaining = useMemo(() => {
    if (!query.data) return []
    const answeredIds = new Set(query.data.results.map((r) => r.item_id))
    return query.data.items.filter((item) => !answeredIds.has(item.id))
  }, [query.data])

  const currentItem = remaining[0]

  function handleSubmit() {
    if (!currentItem || !attemptId || responseText.trim() === '' || answerMutation.isPending) return
    answerMutation.mutate({
      item_id: currentItem.id,
      response_text: responseText,
      quiz_attempt_id: attemptId,
    })
  }

  function handleContinue() {
    setLastResult(null)
    textareaRef.current?.focus()
  }

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !lastResult) {
        e.preventDefault()
        handleSubmit()
        return
      }
      if (e.key === ' ' && lastResult && !isEditableTarget(e.target)) {
        e.preventDefault()
        handleContinue()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  if (query.isLoading) return <p className="body">Loading…</p>
  if (query.isError) return <p className="body">{(query.error as Error).message}</p>
  if (!query.data) return null

  const { quiz_attempt, results } = query.data

  if (quiz_attempt.status === 'completed') {
    return (
      <div>
        <p className="caption">Week {quiz_attempt.week} Quiz — Review</p>
        <h1 className="h1">
          {Math.round((quiz_attempt.score ?? 0) * quiz_attempt.item_count)}/
          {quiz_attempt.item_count}
        </h1>
        <div className="quiz-results-list">
          {results.map((item) => (
            <ReviewItemCard key={item.item_id} item={item} />
          ))}
        </div>
        <Button variant="secondary" onClick={() => navigate('/quizzes')}>
          Back to Quizzes
        </Button>
      </div>
    )
  }

  return (
    <div className="quiz-take">
      <p className="caption">
        Week {quiz_attempt.week} · question {results.length + 1} of {quiz_attempt.item_count}
      </p>

      {lastResult ? (
        <>
          <AnswerResult result={lastResult} />
          <Button onClick={handleContinue}>
            {remaining.length > 1 ? 'Next question (Space)' : 'Finish (Space)'}
          </Button>
        </>
      ) : currentItem ? (
        <>
          <p className="body quiz-prompt">{currentItem.prompt}</p>
          <textarea
            ref={textareaRef}
            className="quiz-textarea"
            placeholder="Type your answer from memory…"
            value={responseText}
            onChange={(e) => setResponseText(e.target.value)}
            autoFocus
          />
          <Button
            onClick={handleSubmit}
            disabled={responseText.trim() === '' || answerMutation.isPending}
          >
            {answerMutation.isPending ? 'Grading…' : 'Submit (Ctrl+Enter)'}
          </Button>
          {answerMutation.isError && (
            <p className="caption quiz-error">{(answerMutation.error as Error).message}</p>
          )}
        </>
      ) : (
        <p className="body">Finishing up…</p>
      )}
    </div>
  )
}
