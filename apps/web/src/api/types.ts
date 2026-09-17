// Mirrors apps/api/schemas/study.py — keep in sync by hand, there is no codegen yet.

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
