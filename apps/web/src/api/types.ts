// Mirrors apps/api/schemas/*.py — keep in sync by hand, there is no codegen yet.

export interface SessionStatus {
  signed_in: boolean
}

export interface StudySessionRequest {
  week?: number
  topics?: string[]
  limit?: number
}

// Deliberately has no `rubric`, `reference_answer` or source quote: the gabarito must not
// reach the client before an answer is submitted (see docs/IMPLEMENTATION_PLAN.md M5).
export interface StudyQueueItem {
  id: string
  type: string
  prompt: string
  difficulty: number
  bloom: string
  topics: string[]
}

export interface StudyAnswerRequest {
  item_id: string
  response_text: string
  quiz_attempt_id?: string
}

export interface RubricHit {
  point_id: string
  point: string
  weight: number
  covered: boolean
  evidence: string
}

export interface Locator {
  page?: number
  slide?: number
  has_notes?: boolean
  t0?: number
  t1?: number
}

export interface SourceExcerpt {
  locator: Locator
  quote: string
}

export interface StudyAnswerResponse {
  score: number
  rubric_hits: RubricHit[]
  misconceptions: string[]
  feedback_md: string
  reference_answer: string
  source: SourceExcerpt[]
  cached: boolean
}

export interface SourceOut {
  id: string
  kind: string
  title: string
  page_count: number | null
  duration_seconds: number | null
  ingested_at: string | null
}

export interface WeekSources {
  week: number
  title: string | null
  sources: SourceOut[]
}

export type Discipline = 'Neuroscience' | 'Computer Science' | 'Psychology'

export interface HomeworkOut {
  id: string
  week: number
  title: string
  description: string
  disciplines: string[]
  code_url: string | null
  live_url: string | null
  status: 'draft' | 'published'
  created_at: string
}

export interface NoteOut {
  id: string
  title: string
  body: string
  disciplines: string[]
  week: number | null
  source_id: string | null
  is_public: boolean
  created_at: string
}

export interface NoteCreateRequest {
  title: string
  body: string
  disciplines: Discipline[]
  week?: number | null
  source_id?: string | null
  is_public?: boolean
}

export interface StartQuizRequest {
  week: number
  limit?: number
}

export interface StartQuizResponse {
  quiz_attempt_id: string
  week: number
  items: StudyQueueItem[]
}

export interface QuizAttemptOut {
  id: string
  week: number
  status: 'in_progress' | 'completed'
  score: number | null
  item_count: number
  started_at: string
  completed_at: string | null
}

export interface WeekQuizzes {
  week: number
  item_count: number
  attempts: QuizAttemptOut[]
}

export interface QuizReviewItem {
  item_id: string
  prompt: string
  response_text: string
  score: number
  rubric_hits: RubricHit[]
  misconceptions: string[]
  feedback_md: string
  reference_answer: string
  source: SourceExcerpt[]
}

export interface QuizReviewResponse {
  quiz_attempt: QuizAttemptOut
  items: StudyQueueItem[]
  results: QuizReviewItem[]
}
