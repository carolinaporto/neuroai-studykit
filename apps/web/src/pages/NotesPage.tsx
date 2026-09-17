import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { createNote, listNotes } from '../api/client'
import type { Discipline } from '../api/types'
import { useSession } from '../auth/useAuth'
import { Button } from '../components/Button'
import { InsightNote } from '../components/InsightNote'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import './NotesPage.css'

const DISCIPLINES: Discipline[] = ['Neuroscience', 'Computer Science', 'Psychology']

export function NotesPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false
  const queryClient = useQueryClient()
  const notesQuery = useQuery({ queryKey: ['notes'], queryFn: listNotes, enabled: signedIn })

  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [selected, setSelected] = useState<Discipline[]>([])
  const [isPublic, setIsPublic] = useState(false)

  const createMutation = useMutation({
    mutationFn: createNote,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
      setTitle('')
      setBody('')
      setSelected([])
      setIsPublic(false)
    },
  })

  if (!signedIn) return <LockedPlaceholder section="Notes & Insights" />

  function toggleDiscipline(discipline: Discipline) {
    setSelected((prev) =>
      prev.includes(discipline) ? prev.filter((d) => d !== discipline) : [...prev, discipline],
    )
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (title.trim() === '' || body.trim() === '' || selected.length === 0) return
    createMutation.mutate({ title, body, disciplines: selected, is_public: isPublic })
  }

  const notes = notesQuery.data ?? []

  return (
    <div>
      <h1 className="h1">Notes & Insights</h1>

      <form className="note-form" onSubmit={handleSubmit}>
        <input
          className="note-input"
          placeholder="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className="note-textarea"
          placeholder="What did you notice?"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="note-disciplines">
          {DISCIPLINES.map((discipline) => (
            <button
              type="button"
              key={discipline}
              className={`note-chip tag${selected.includes(discipline) ? ' note-chip-selected' : ''}`}
              onClick={() => toggleDiscipline(discipline)}
            >
              {discipline}
            </button>
          ))}
        </div>
        <label className="note-public-toggle body-sm">
          <input
            type="checkbox"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          Make this note public
        </label>
        <Button
          type="submit"
          disabled={
            createMutation.isPending ||
            title.trim() === '' ||
            body.trim() === '' ||
            selected.length === 0
          }
        >
          {createMutation.isPending ? 'Saving…' : 'Add note'}
        </Button>
      </form>

      {notes.length === 0 && <p className="body">No notes yet.</p>}
      <div className="notes-list">
        {notes.map((note) => (
          <InsightNote
            key={note.id}
            disciplines={note.disciplines}
            isPublic={note.is_public}
            title={note.title}
            body={note.body}
            week={note.week}
            createdAt={note.created_at}
          />
        ))}
      </div>
    </div>
  )
}
