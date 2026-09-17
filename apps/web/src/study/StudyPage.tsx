import { useMutation } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { startStudySession, submitStudyAnswer } from '../api/client'
import type { StudyAnswerResponse, StudyQueueItem } from '../api/types'
import { formatLocator } from '../lib/locator'

type Phase = 'start' | 'answering' | 'result' | 'done'

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return el?.tagName === 'TEXTAREA' || el?.tagName === 'INPUT'
}

export function StudyPage() {
  const [phase, setPhase] = useState<Phase>('start')
  const [week, setWeek] = useState('')
  const [limit, setLimit] = useState('10')
  const [queue, setQueue] = useState<StudyQueueItem[]>([])
  const [index, setIndex] = useState(0)
  const [responseText, setResponseText] = useState('')
  const [results, setResults] = useState<StudyAnswerResponse[]>([])
  const [emptyQueue, setEmptyQueue] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const sessionMutation = useMutation({
    mutationFn: startStudySession,
    onSuccess: (items) => {
      if (items.length === 0) {
        setEmptyQueue(true)
        return
      }
      setEmptyQueue(false)
      setQueue(items)
      setIndex(0)
      setResults([])
      setResponseText('')
      setPhase('answering')
    },
  })

  const answerMutation = useMutation({
    mutationFn: submitStudyAnswer,
    onSuccess: (result) => {
      setResults((prev) => [...prev, result])
      setPhase('result')
    },
  })

  const currentItem = queue[index]

  function handleStart() {
    setEmptyQueue(false)
    sessionMutation.mutate({
      week: week.trim() === '' ? undefined : Number(week),
      limit: Number(limit) || 10,
    })
  }

  function handleSubmit() {
    if (!currentItem || responseText.trim() === '' || answerMutation.isPending) return
    answerMutation.mutate({ item_id: currentItem.id, response_text: responseText })
  }

  function handleAdvance() {
    if (phase !== 'result') return
    const next = index + 1
    if (next < queue.length) {
      setIndex(next)
      setResponseText('')
      setPhase('answering')
      textareaRef.current?.focus()
    } else {
      setPhase('done')
    }
  }

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && phase === 'answering') {
        e.preventDefault()
        handleSubmit()
        return
      }
      if (e.key === ' ' && phase === 'result' && !isEditableTarget(e.target)) {
        e.preventDefault()
        handleAdvance()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  if (phase === 'start') {
    return (
      <main className="mx-auto flex min-h-svh max-w-xl flex-col justify-center gap-4 p-6">
        <h1 className="text-2xl font-semibold text-gray-900">NeuroAI Study Kit</h1>
        <label className="flex flex-col gap-1 text-sm text-gray-700">
          Semana (opcional)
          <input
            type="number"
            className="rounded border border-gray-300 px-3 py-2"
            value={week}
            onChange={(e) => setWeek(e.target.value)}
            placeholder="ex.: 1"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-gray-700">
          Nº de questões
          <input
            type="number"
            className="rounded border border-gray-300 px-3 py-2"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-50"
          onClick={handleStart}
          disabled={sessionMutation.isPending}
        >
          {sessionMutation.isPending ? 'Carregando…' : 'Começar'}
        </button>
        {sessionMutation.isError && (
          <p className="text-sm text-red-600">{(sessionMutation.error as Error).message}</p>
        )}
        {emptyQueue && (
          <p className="text-sm text-amber-700">
            Nenhuma questão encontrada para esse filtro. Tente outra semana ou deixe o campo em
            branco.
          </p>
        )}
      </main>
    )
  }

  if (phase === 'done') {
    const avg = results.length ? results.reduce((sum, r) => sum + r.score, 0) / results.length : 0
    return (
      <main className="mx-auto flex min-h-svh max-w-xl flex-col justify-center gap-4 p-6">
        <h1 className="text-2xl font-semibold text-gray-900">Sessão concluída</h1>
        <p className="text-gray-700">
          {results.length} questões respondidas — média {(avg * 100).toFixed(0)}%.
        </p>
        <button
          type="button"
          className="rounded bg-gray-900 px-4 py-2 font-medium text-white"
          onClick={() => setPhase('start')}
        >
          Nova sessão
        </button>
      </main>
    )
  }

  if (!currentItem) return null

  const currentResult = phase === 'result' ? results[results.length - 1] : undefined

  return (
    <main className="mx-auto flex min-h-svh max-w-2xl flex-col gap-4 p-6">
      <p className="text-sm text-gray-500">
        Questão {index + 1} de {queue.length} · {currentItem.type} · dificuldade{' '}
        {currentItem.difficulty} · {currentItem.bloom}
        {currentItem.topics.length > 0 && ` · ${currentItem.topics.join(', ')}`}
      </p>

      <p className="text-lg text-gray-900">{currentItem.prompt}</p>

      <textarea
        ref={textareaRef}
        className="min-h-40 rounded border border-gray-300 p-3"
        placeholder="Digite sua resposta de memória…"
        value={responseText}
        onChange={(e) => setResponseText(e.target.value)}
        disabled={phase === 'result'}
        autoFocus
      />

      {phase === 'answering' && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-50"
            onClick={handleSubmit}
            disabled={responseText.trim() === '' || answerMutation.isPending}
          >
            {answerMutation.isPending ? 'Corrigindo…' : 'Enviar (Ctrl+Enter)'}
          </button>
          {answerMutation.isError && (
            <p className="text-sm text-red-600">{(answerMutation.error as Error).message}</p>
          )}
        </div>
      )}

      {phase === 'result' && currentResult && (
        <div className="flex flex-col gap-4 rounded border border-gray-200 p-4">
          <p className="text-lg font-semibold text-gray-900">
            Nota: {(currentResult.score * 100).toFixed(0)}%
            {currentResult.cached && (
              <span className="ml-2 text-sm font-normal text-gray-500">(cache)</span>
            )}
          </p>

          <ul className="flex flex-col gap-2">
            {currentResult.rubric_hits.map((hit) => (
              <li
                key={hit.point_id}
                className={
                  hit.covered
                    ? 'rounded border-l-4 border-green-600 bg-green-50 p-2 text-green-900'
                    : 'rounded border-l-4 border-red-600 bg-red-50 p-2 text-red-900'
                }
              >
                <p className="font-medium">
                  {hit.covered ? '✓' : '✗'} {hit.point}
                </p>
                {hit.evidence && <p className="text-sm italic">{hit.evidence}</p>}
              </li>
            ))}
          </ul>

          {currentResult.misconceptions.length > 0 && (
            <div>
              <p className="font-medium text-gray-900">Possíveis equívocos</p>
              <ul className="list-inside list-disc text-gray-700">
                {currentResult.misconceptions.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <p className="font-medium text-gray-900">Feedback</p>
            <p className="whitespace-pre-wrap text-gray-700">{currentResult.feedback_md}</p>
          </div>

          <div>
            <p className="font-medium text-gray-900">Gabarito</p>
            <p className="whitespace-pre-wrap text-gray-700">{currentResult.reference_answer}</p>
          </div>

          <div>
            <p className="font-medium text-gray-900">Fonte</p>
            <ul className="flex flex-col gap-2">
              {currentResult.source.map((excerpt, i) => (
                <li key={i} className="rounded bg-gray-50 p-2">
                  <p className="text-xs font-medium text-gray-500">
                    {formatLocator(excerpt.locator)}
                  </p>
                  <p className="text-gray-700">"{excerpt.quote}"</p>
                </li>
              ))}
            </ul>
          </div>

          <button
            type="button"
            className="self-start rounded bg-gray-900 px-4 py-2 font-medium text-white"
            onClick={handleAdvance}
          >
            {index + 1 < queue.length ? 'Próxima (Espaço)' : 'Finalizar (Espaço)'}
          </button>
        </div>
      )}
    </main>
  )
}
