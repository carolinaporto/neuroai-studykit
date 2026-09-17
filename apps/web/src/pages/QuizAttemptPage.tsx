import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { reviewQuiz, submitStudyAnswer } from '../api/client'
import type { QuizReviewItem, RubricHit, StudyAnswerResponse, StudyQueueItem } from '../api/types'
import { Button } from '../components/Button'
import { SourcePassage } from '../components/SourcePassage'
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

// Original passage first (the actual class material, highlighted where the rubric points
// to it), the model's own writing — feedback, reference answer — clearly labeled and last.
// Was the other way around before: reference_answer/feedback_md are LLM-composed text, not
// anything from the document, and showing them first read as "the app summarizing my
// upload," which is exactly backwards from what a recall check should show.
function AnswerResult({ itemId, result }: { itemId: string; result: StudyAnswerResponse }) {
  const quotes = result.source.map((excerpt) => excerpt.quote)
  return (
    <div className="quiz-result">
      <p className="body">
        <strong>Score: {Math.round(result.score * 100)}%</strong>
        {result.cached && <span className="caption"> (cache)</span>}
      </p>
      <RubricList hits={result.rubric_hits} />
      <SourcePassage itemId={itemId} quotes={quotes} />
      <div className="quiz-summary">
        <p className="label quiz-summary-label">Summary</p>
        {result.misconceptions.length > 0 && (
          <p className="body-sm">Misconceptions: {result.misconceptions.join('; ')}</p>
        )}
        <p className="body-sm">{result.feedback_md}</p>
        <p className="body-sm">
          <strong>Reference answer:</strong> {result.reference_answer}
        </p>
      </div>
    </div>
  )
}

function ReviewItemCard({ item }: { item: QuizReviewItem }) {
  const quotes = item.source.map((excerpt) => excerpt.quote)
  return (
    <div className="quiz-result">
      <p className="body">
        <strong>{item.prompt}</strong>
      </p>
      <p className="body-sm">Your answer: {item.response_text}</p>
      <RubricList hits={item.rubric_hits} />
      <SourcePassage itemId={item.item_id} quotes={quotes} />
      <div className="quiz-summary">
        <p className="label quiz-summary-label">Summary</p>
        <p className="body-sm">
          <strong>Reference answer:</strong> {item.reference_answer}
        </p>
      </div>
    </div>
  )
}

// "I don't know this one" — shows the passage the skipped item is anchored to, not the
// gabarito (no rubric, no reference_answer: see ItemSourceResponse's docstring on the
// backend). The item itself moves to the end of the queue in the parent's ordering, so
// this is a detour, not a way out — it still has to be answered for real before the quiz
// counts it graded.
function ReadingPanel({
  itemId,
  prompt,
  onContinue,
}: {
  itemId: string
  prompt: string | undefined
  onContinue: () => void
}) {
  return (
    <div className="quiz-reading">
      {prompt && <p className="caption quiz-reading-prompt">Skipped: {prompt}</p>}
      <SourcePassage itemId={itemId} quotes={[]} />
      <Button onClick={onContinue}>Continue (Space)</Button>
    </div>
  )
}

export function QuizAttemptPage() {
  const { attemptId } = useParams<{ attemptId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [responseText, setResponseText] = useState('')
  const [lastResult, setLastResult] = useState<StudyAnswerResponse | null>(null)
  const [lastAnsweredItemId, setLastAnsweredItemId] = useState<string | null>(null)
  const [skippedIds, setSkippedIds] = useState<string[]>([])
  const [readingItemId, setReadingItemId] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const query = useQuery({
    queryKey: ['quiz-attempt', attemptId],
    queryFn: () => reviewQuiz(attemptId as string),
    enabled: attemptId !== undefined,
  })

  const answerMutation = useMutation({
    mutationFn: submitStudyAnswer,
    onSuccess: (result, variables) => {
      setLastResult(result)
      setLastAnsweredItemId(variables.item_id)
      setResponseText('')
      queryClient.invalidateQueries({ queryKey: ['quiz-attempt', attemptId] })
      queryClient.invalidateQueries({ queryKey: ['quiz-weeks'] })
    },
  })

  // Skipped items sink to the end of the queue instead of disappearing — "pull the item
  // I'm stuck on to the back of the line" rather than "let me skip it for good".
  const orderedRemaining = useMemo(() => {
    if (!query.data) return []
    const answeredIds = new Set(query.data.results.map((r) => r.item_id))
    const notAnswered = query.data.items.filter((item) => !answeredIds.has(item.id))
    const notAnsweredIds = new Set(notAnswered.map((item) => item.id))
    const stillSkippedIds = skippedIds.filter((id) => notAnsweredIds.has(id))
    const stillSkippedSet = new Set(stillSkippedIds)
    const notSkipped = notAnswered.filter((item) => !stillSkippedSet.has(item.id))
    const byId = new Map(notAnswered.map((item) => [item.id, item]))
    const stillSkipped = stillSkippedIds
      .map((id) => byId.get(id))
      .filter((item): item is StudyQueueItem => item !== undefined)
    return [...notSkipped, ...stillSkipped]
  }, [query.data, skippedIds])

  const currentItem = orderedRemaining[0]
  const currentItemWasSkipped = currentItem !== undefined && skippedIds.includes(currentItem.id)

  function handleSubmit() {
    if (!currentItem || !attemptId || responseText.trim() === '' || answerMutation.isPending) return
    answerMutation.mutate({
      item_id: currentItem.id,
      response_text: responseText,
      quiz_attempt_id: attemptId,
    })
  }

  function handleSkip() {
    if (!currentItem) return
    setSkippedIds((prev) => (prev.includes(currentItem.id) ? prev : [...prev, currentItem.id]))
    setReadingItemId(currentItem.id)
  }

  function handleContinueReading() {
    setReadingItemId(null)
    textareaRef.current?.focus()
  }

  function handleContinue() {
    setLastResult(null)
    textareaRef.current?.focus()
  }

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (readingItemId !== null) {
        if (e.key === ' ' && !isEditableTarget(e.target)) {
          e.preventDefault()
          handleContinueReading()
        }
        return
      }
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
        {currentItemWasSkipped && readingItemId === null && ' · revisiting a skipped question'}
      </p>

      {readingItemId ? (
        <ReadingPanel
          itemId={readingItemId}
          prompt={query.data.items.find((item) => item.id === readingItemId)?.prompt}
          onContinue={handleContinueReading}
        />
      ) : lastResult ? (
        <>
          <AnswerResult itemId={lastAnsweredItemId as string} result={lastResult} />
          <Button onClick={handleContinue}>
            {orderedRemaining.length > 1 ? 'Next question (Space)' : 'Finish (Space)'}
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
          <div className="quiz-actions">
            <Button
              onClick={handleSubmit}
              disabled={responseText.trim() === '' || answerMutation.isPending}
            >
              {answerMutation.isPending ? 'Grading…' : 'Submit (Ctrl+Enter)'}
            </Button>
            {!currentItemWasSkipped && (
              <Button variant="secondary" onClick={handleSkip} disabled={answerMutation.isPending}>
                I don't know this — show me the material
              </Button>
            )}
          </div>
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
