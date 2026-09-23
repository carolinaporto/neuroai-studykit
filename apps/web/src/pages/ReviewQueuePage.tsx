import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { listReviewQueue, patchItem } from '../api/client'
import type { ItemPatchRequest, ReviewItemOut, RubricPoint } from '../api/types'
import { useSession } from '../auth/useAuth'
import { Button } from '../components/Button'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import { ReviewSourcePassage } from '../components/ReviewSourcePassage'
import { useToast } from '../components/toastContext'
import './ReviewQueuePage.css'

const STATUS_TOAST_LABEL: Record<string, string> = {
  approved: 'Item approved',
  edited: 'Item saved as edited',
  retired: 'Item retired',
}

const BLOOM_LEVELS = ['recall', 'understand', 'apply', 'analyze']
const MIN_RUBRIC_POINTS = 2

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return el?.tagName === 'TEXTAREA' || el?.tagName === 'INPUT' || el?.tagName === 'SELECT'
}

interface EditState {
  prompt: string
  reference_answer: string
  difficulty: number
  bloom: string
  rubric: RubricPoint[]
}

function toEditState(item: ReviewItemOut): EditState {
  return {
    prompt: item.prompt,
    reference_answer: item.reference_answer,
    difficulty: item.difficulty,
    bloom: item.bloom,
    rubric: item.rubric,
  }
}

function EditForm({
  edit,
  onChange,
  onCancel,
  onSave,
  saving,
}: {
  edit: EditState
  onChange: (next: EditState) => void
  onCancel: () => void
  onSave: () => void
  saving: boolean
}) {
  function updatePoint(id: string, field: 'point' | 'weight', value: string) {
    onChange({
      ...edit,
      rubric: edit.rubric.map((p) =>
        p.id === id ? { ...p, [field]: field === 'weight' ? Number(value) || 0 : value } : p,
      ),
    })
  }

  function removePoint(id: string) {
    if (edit.rubric.length <= MIN_RUBRIC_POINTS) return
    onChange({ ...edit, rubric: edit.rubric.filter((p) => p.id !== id) })
  }

  return (
    <div className="review-edit-form">
      <label className="review-field">
        <span className="label">Prompt</span>
        <textarea
          className="review-textarea"
          value={edit.prompt}
          onChange={(e) => onChange({ ...edit, prompt: e.target.value })}
        />
      </label>

      <label className="review-field">
        <span className="label">Reference answer</span>
        <textarea
          className="review-textarea"
          value={edit.reference_answer}
          onChange={(e) => onChange({ ...edit, reference_answer: e.target.value })}
        />
      </label>

      <div className="review-field-row">
        <label className="review-field">
          <span className="label">Difficulty</span>
          <select
            className="review-select"
            value={edit.difficulty}
            onChange={(e) => onChange({ ...edit, difficulty: Number(e.target.value) })}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        <label className="review-field">
          <span className="label">Bloom level</span>
          <select
            className="review-select"
            value={edit.bloom}
            onChange={(e) => onChange({ ...edit, bloom: e.target.value })}
          >
            {BLOOM_LEVELS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="review-field">
        <span className="label">Rubric</span>
        <ul className="review-rubric-edit-list">
          {edit.rubric.map((point) => (
            <li key={point.id} className="review-rubric-edit-row">
              <textarea
                className="review-textarea review-rubric-point-input"
                value={point.point}
                onChange={(e) => updatePoint(point.id, 'point', e.target.value)}
              />
              <input
                className="review-rubric-weight-input"
                type="number"
                min={0.1}
                step={0.1}
                value={point.weight}
                onChange={(e) => updatePoint(point.id, 'weight', e.target.value)}
              />
              <p
                className="caption review-rubric-quote"
                title="The anchor quote — fixed, not editable"
              >
                “{point.support_quote}”
              </p>
              <button
                type="button"
                className="review-rubric-remove"
                onClick={() => removePoint(point.id)}
                disabled={edit.rubric.length <= MIN_RUBRIC_POINTS}
                aria-label="Remove this rubric point"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="review-actions">
        <Button onClick={onSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save (edited)'}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

function ReviewItemCard({
  item,
  onApprove,
  onRetire,
  onEdit,
  editing,
  edit,
  onEditChange,
  onEditCancel,
  onEditSave,
  saving,
}: {
  item: ReviewItemOut
  onApprove: () => void
  onRetire: () => void
  onEdit: () => void
  editing: boolean
  edit: EditState | null
  onEditChange: (next: EditState) => void
  onEditCancel: () => void
  onEditSave: () => void
  saving: boolean
}) {
  const quotes = item.rubric.map((p) => p.support_quote)

  return (
    <div className="review-card">
      <p className="caption review-card-meta">
        {item.type} · difficulty {item.difficulty} · {item.bloom}
        {item.topics.length > 0 && ` · ${item.topics.join(', ')}`}
      </p>
      <p className="body review-card-prompt">{item.prompt}</p>

      <ReviewSourcePassage chunk={item.chunk} quotes={quotes} />

      {editing && edit ? (
        <EditForm
          edit={edit}
          onChange={onEditChange}
          onCancel={onEditCancel}
          onSave={onEditSave}
          saving={saving}
        />
      ) : (
        <>
          <ul className="review-rubric-list">
            {item.rubric.map((point) => (
              <li key={point.id} className="review-rubric-point">
                <p className="body-sm">
                  {point.point} <span className="caption">(weight {point.weight})</span>
                </p>
              </li>
            ))}
          </ul>
          <p className="body-sm review-card-reference">
            <strong>Reference answer:</strong> {item.reference_answer}
          </p>
          <div className="review-actions">
            <Button onClick={onApprove} disabled={saving}>
              Approve (A)
            </Button>
            <Button variant="secondary" onClick={onEdit} disabled={saving}>
              Edit (E)
            </Button>
            <Button variant="danger" onClick={onRetire} disabled={saving}>
              Retire (R)
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

export function ReviewQueuePage() {
  const { week } = useParams<{ week: string }>()
  const weekNumber = Number(week)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false

  // enabled: signedIn — not just belt-and-suspenders. Reached directly (a bookmark, a
  // refresh, not always a client-side nav from ReviewPage), this query used to fire before
  // Layout's useSession() effect had set the Clerk token getter (clerkTokenStore.ts):
  // child effects run before a parent's on first mount, so the request went out with no
  // Authorization header and 401'd even while genuinely signed in. Every other locked page
  // already gates its query on its own useSession() call for the same reason — this one
  // didn't.
  const query = useQuery({
    queryKey: ['review-queue'],
    queryFn: listReviewQueue,
    enabled: signedIn,
  })

  const [doneIds, setDoneIds] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState(false)
  const [edit, setEdit] = useState<EditState | null>(null)
  const [tally, setTally] = useState({ approved: 0, edited: 0, retired: 0 })

  const weekQueue = query.data?.find((w) => w.week === weekNumber)
  const allItems = weekQueue?.items ?? []
  const remaining = allItems.filter((item) => !doneIds.has(item.id))
  const currentItem = remaining[0]

  const patchMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ItemPatchRequest }) => patchItem(id, body),
    onSuccess: (_, variables) => {
      setDoneIds((prev) => new Set(prev).add(variables.id))
      setEditing(false)
      setEdit(null)
      const status = variables.body.status
      if (status === 'approved') setTally((t) => ({ ...t, approved: t.approved + 1 }))
      else if (status === 'edited') setTally((t) => ({ ...t, edited: t.edited + 1 }))
      else if (status === 'retired') setTally((t) => ({ ...t, retired: t.retired + 1 }))
      queryClient.invalidateQueries({ queryKey: ['review-queue'] })
      queryClient.invalidateQueries({ queryKey: ['quiz-weeks'] })
      const label = variables.body.status && STATUS_TOAST_LABEL[variables.body.status]
      if (label) toast.success(label)
    },
    onError: (error) => toast.error((error as Error).message),
  })

  function handleApprove() {
    if (!currentItem || patchMutation.isPending) return
    patchMutation.mutate({ id: currentItem.id, body: { status: 'approved' } })
  }

  function handleRetire() {
    if (!currentItem || patchMutation.isPending) return
    if (!window.confirm('Retire this question? It will never reach a quiz.')) return
    patchMutation.mutate({ id: currentItem.id, body: { status: 'retired' } })
  }

  function handleEditToggle() {
    if (!currentItem) return
    if (editing) {
      setEditing(false)
      setEdit(null)
    } else {
      setEdit(toEditState(currentItem))
      setEditing(true)
    }
  }

  function handleSaveEdit() {
    if (!currentItem || !edit || patchMutation.isPending) return
    patchMutation.mutate({
      id: currentItem.id,
      body: {
        prompt: edit.prompt,
        reference_answer: edit.reference_answer,
        difficulty: edit.difficulty,
        bloom: edit.bloom,
        rubric: edit.rubric,
        status: 'edited',
      },
    })
  }

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (isEditableTarget(e.target) || !currentItem || patchMutation.isPending) return
      if (e.key === 'a' || e.key === 'A') {
        e.preventDefault()
        handleApprove()
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        handleRetire()
      } else if (e.key === 'e' || e.key === 'E') {
        e.preventDefault()
        handleEditToggle()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  if (!signedIn) return <LockedPlaceholder section="Review" />
  if (query.isLoading) return <p className="body">Loading…</p>
  if (query.isError) return <p className="body">{(query.error as Error).message}</p>

  return (
    <div className="page review-queue">
      <p className="caption">
        Week {weekNumber} · {remaining.length} left to review
      </p>

      {currentItem ? (
        <ReviewItemCard
          item={currentItem}
          onApprove={handleApprove}
          onRetire={handleRetire}
          onEdit={handleEditToggle}
          editing={editing}
          edit={edit}
          onEditChange={setEdit}
          onEditCancel={handleEditToggle}
          onEditSave={handleSaveEdit}
          saving={patchMutation.isPending}
        />
      ) : (
        <div className="review-summary">
          <p className="h2">All reviewed</p>
          <p className="body-sm">
            {tally.approved} approved · {tally.edited} edited · {tally.retired} retired
          </p>
          <Button variant="secondary" onClick={() => navigate('/review')}>
            Back to Review
          </Button>
        </div>
      )}
    </div>
  )
}
