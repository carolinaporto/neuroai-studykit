import type {
  StudyAnswerRequest,
  StudyAnswerResponse,
  StudySessionRequest,
  StudyQueueItem,
} from './types'

// Never a secret — just the backend's own address. VITE_* would leak into the client
// bundle, but that's fine here (CLAUDE.md invariant 3 is about API keys, not this).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`${path} failed (${res.status}): ${detail}`)
  }
  return res.json() as Promise<T>
}

export function startStudySession(body: StudySessionRequest): Promise<StudyQueueItem[]> {
  return postJson('/api/study/session', body)
}

export function submitStudyAnswer(body: StudyAnswerRequest): Promise<StudyAnswerResponse> {
  return postJson('/api/study/answer', body)
}
