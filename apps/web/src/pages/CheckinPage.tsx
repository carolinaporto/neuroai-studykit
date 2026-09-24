import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import Markdown from 'react-markdown'

import { getCheckinDraft } from '../api/client'
import { useSession } from '../auth/useAuth'
import { Button } from '../components/Button'
import { LockedPlaceholder } from '../components/LockedPlaceholder'
import './CheckinPage.css'

export function CheckinPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false
  const [week, setWeek] = useState(1)
  const [copied, setCopied] = useState(false)

  const query = useQuery({
    queryKey: ['checkin-draft', week],
    queryFn: () => getCheckinDraft(week),
    enabled: signedIn,
  })

  if (!signedIn) return <LockedPlaceholder section="Check-in" />

  async function handleCopy() {
    if (!query.data) return
    try {
      await navigator.clipboard.writeText(query.data.draft_markdown)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be denied by the browser — the text is still on screen to
      // select by hand, so this isn't a dead end, just a missed shortcut.
    }
  }

  return (
    <div className="page">
      <h1 className="h1">Check-in draft</h1>
      <p className="body-sm checkin-lede">
        A starting point for the course's weekly check-in, built from your own real numbers — not
        written for you. Copy it out and write the reflection yourself.
      </p>

      <label className="checkin-week-field">
        <span className="label">Week</span>
        <input
          type="number"
          min={1}
          className="checkin-week-input"
          value={week}
          onChange={(e) => setWeek(Math.max(1, Number(e.target.value) || 1))}
        />
      </label>

      {query.isLoading && <p className="body">Loading…</p>}
      {query.isError && <p className="body">{(query.error as Error).message}</p>}

      {query.data && (
        <div className="checkin-draft">
          <div className="checkin-draft-actions">
            <Button variant="secondary" onClick={handleCopy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
          <div className="checkin-draft-text">
            <Markdown>{query.data.draft_markdown}</Markdown>
          </div>
        </div>
      )}
    </div>
  )
}
