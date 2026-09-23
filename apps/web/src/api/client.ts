import type {
  GenerateResponse,
  HomeworkOut,
  ItemOut,
  ItemPatchRequest,
  ItemSourceResponse,
  NoteCreateRequest,
  NoteOut,
  ProgressResponse,
  QuizReviewResponse,
  SessionStatus,
  SourceDetail,
  StartQuizRequest,
  StartQuizResponse,
  StudyAnswerRequest,
  StudyAnswerResponse,
  StudySessionRequest,
  StudyQueueItem,
  UploadSourcesResponse,
  WeekQuizzes,
  WeekReviewQueue,
  WeekSources,
} from './types'

// Never a secret — just the backend's own address. VITE_* would leak into the client
// bundle, but that's fine here (CLAUDE.md invariant 3 is about API keys, not this).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include', // sends/accepts the owner session cookie
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`${path} failed (${res.status}): ${detail}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

function get<T>(path: string): Promise<T> {
  return request(path)
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request(path, { method: 'PATCH', body: JSON.stringify(body) })
}

function del<T>(path: string): Promise<T> {
  return request(path, { method: 'DELETE' })
}

// --- auth ---

export function login(password: string): Promise<SessionStatus> {
  return post('/api/auth/login', { password })
}

export function logout(): Promise<SessionStatus> {
  return post('/api/auth/logout')
}

export function getSession(): Promise<SessionStatus> {
  return get('/api/auth/session')
}

// --- sources ---

export function listSources(): Promise<WeekSources[]> {
  return get('/api/sources')
}

export function getSource(id: string): Promise<SourceDetail> {
  return get(`/api/sources/${id}`)
}

export function deleteSource(id: string): Promise<void> {
  return del(`/api/sources/${id}`)
}

// Not a fetch wrapper — used directly as an <iframe>/<a> src so the browser (not our JS)
// streams the bytes. Cookies still ride along automatically for a same-context request.
export function sourceFileUrl(id: string): string {
  return `${API_BASE_URL}/api/sources/${id}/file`
}

export async function uploadSources(week: number, files: File[]): Promise<UploadSourcesResponse> {
  const formData = new FormData()
  formData.append('week', String(week))
  for (const file of files) formData.append('files', file)

  // Not the shared `request()` helper: it always sets Content-Type: application/json,
  // which would break multipart/form-data — the browser must set that header itself, with
  // the boundary it picked, or the server can't parse the body at all.
  const res = await fetch(`${API_BASE_URL}/api/sources/upload`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })
  if (!res.ok) {
    throw new Error(`upload failed (${res.status}): ${await res.text()}`)
  }
  return res.json() as Promise<UploadSourcesResponse>
}

export function generateQuestions(week: number, force = false): Promise<GenerateResponse> {
  return post('/api/sources/generate', { week, force })
}

// --- items / review (M6) ---

export function listReviewQueue(): Promise<WeekReviewQueue[]> {
  return get('/api/items/review')
}

export function patchItem(id: string, body: ItemPatchRequest): Promise<ItemOut> {
  return patch(`/api/items/${id}`, body)
}

// --- homework (public) ---

export function listHomework(): Promise<HomeworkOut[]> {
  return get('/api/homework')
}

// --- notes ---

export function listNotes(): Promise<NoteOut[]> {
  return get('/api/notes')
}

export function createNote(body: NoteCreateRequest): Promise<NoteOut> {
  return post('/api/notes', body)
}

export function patchNote(id: string, body: Partial<NoteCreateRequest>): Promise<NoteOut> {
  return patch(`/api/notes/${id}`, body)
}

// --- study: standalone practice ---

export function startStudySession(body: StudySessionRequest): Promise<StudyQueueItem[]> {
  return post('/api/study/session', body)
}

export function submitStudyAnswer(body: StudyAnswerRequest): Promise<StudyAnswerResponse> {
  return post('/api/study/answer', body)
}

// --- study: per-week quiz ---

export function listQuizWeeks(): Promise<WeekQuizzes[]> {
  return get('/api/study/weeks')
}

export function startQuiz(body: StartQuizRequest): Promise<StartQuizResponse> {
  return post('/api/study/quiz', body)
}

export function reviewQuiz(quizAttemptId: string): Promise<QuizReviewResponse> {
  return get(`/api/study/quiz/${quizAttemptId}`)
}

// "I don't know this one" — the passage the item is anchored to, no rubric/reference
// answer attached. See ItemSourceResponse's docstring on the backend for why this is
// different from a reveal-the-answer button.
export function getItemSource(itemId: string): Promise<ItemSourceResponse> {
  return get(`/api/study/items/${itemId}/source`)
}

// --- progress (M10) ---

export function getProgress(): Promise<ProgressResponse> {
  return get('/api/progress')
}
