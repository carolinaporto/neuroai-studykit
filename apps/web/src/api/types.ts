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
  // Present only for `type === 'mcq'` — just the option texts, never which one is correct.
  choices?: { options: string[] } | null
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

export interface ChunkOut {
  ordinal: number
  text: string
  locators: Locator[]
  token_count: number
}

export interface SourceDetail extends SourceOut {
  chunks: ChunkOut[]
}

export interface UploadResult {
  filename: string
  status: 'ingested' | 'duplicate' | 'unsupported' | 'too_large' | 'failed'
  chunk_count: number | null
  error: string | null
}

export interface UploadSourcesResponse {
  results: UploadResult[]
}

export interface GenerateResponse {
  chunks_processed: number
  items_saved: number
  items_rejected: number
  items_deduped: number
  chunks_failed: number
  proposed_topics: string[]
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
  body: string | null
  url: string | null
  disciplines: string[]
  week: number | null
  source_id: string | null
  is_public: boolean
  created_at: string
}

export interface NoteCreateRequest {
  title: string
  body?: string | null
  url?: string | null
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

export interface ItemSourceResponse {
  locator: Locator
  text: string
}

// --- items / review (M6) ---

export interface RubricPoint {
  id: string
  point: string
  weight: number
  support_quote: string
}

export type ItemStatus = 'draft' | 'approved' | 'edited' | 'retired'

export interface ItemOut {
  id: string
  source_id: string
  chunk_ids: string[]
  type: string
  prompt: string
  reference_answer: string
  rubric: RubricPoint[]
  choices: Record<string, unknown> | null
  difficulty: number
  bloom: string
  topics: string[]
  status: ItemStatus
}

export interface ReviewChunkOut {
  locator: Locator
  text: string
}

export interface ReviewItemOut extends ItemOut {
  chunk: ReviewChunkOut
  gen_model: string
}

export interface WeekReviewQueue {
  week: number
  title: string | null
  items: ReviewItemOut[]
}

// All optional: only what's set gets sent. Mirrors apps/api/schemas/items.py's
// ItemPatchRequest.
export interface ItemPatchRequest {
  status?: ItemStatus
  prompt?: string
  reference_answer?: string
  rubric?: RubricPoint[]
  difficulty?: number
  bloom?: string
  topics?: string[]
  choices?: Record<string, unknown> | null
}

// --- progress (M10) ---

export interface TopicMastery {
  slug: string
  label: string | null
  item_count: number
  attempted_count: number
  // null: items exist for this topic but none have been answered yet — not the same as weak.
  avg_score: number | null
}

export interface DueCounts {
  never_reviewed: number
  overdue: number
  due_today: number
  upcoming: number
}

export interface ProgressResponse {
  topics: TopicMastery[]
  due: DueCounts
}

// --- checkin (M11) ---

export interface CheckinDraft {
  week: number
  title: string | null
  items_total: number
  items_attempted: number
  avg_score: number | null
  topics: TopicMastery[]
  misconceptions: string[]
  draft_markdown: string
}
