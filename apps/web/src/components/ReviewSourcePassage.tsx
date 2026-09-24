import { Fragment, useMemo, useState } from 'react'

import type { ReviewChunkOut } from '../api/types'
import { findHighlightRanges } from '../lib/highlightQuotes'
import { formatLocator } from '../lib/locator'
import { EMBEDDABLE_KINDS } from '../lib/sourceKinds'
import { SourcePageViewer } from './SourcePageViewer'
import './SourcePassage.css'

// Same rendering as `SourcePassage`, but the chunk arrives as a prop instead of being
// fetched by item id: the review queue's `GET /api/items/review` already embeds each item's
// anchor chunk (apps/api/schemas/items.py's `ReviewItemOut`), so re-fetching it per card
// here would be a needless request for every item in the queue.
function HighlightedText({ text, quotes }: { text: string; quotes: string[] }) {
  const ranges = useMemo(() => findHighlightRanges(text, quotes), [text, quotes])
  if (ranges.length === 0) return <>{text}</>

  const parts: React.ReactNode[] = []
  let cursor = 0
  ranges.forEach((range, i) => {
    if (range.start > cursor)
      parts.push(<Fragment key={`t${i}`}>{text.slice(cursor, range.start)}</Fragment>)
    parts.push(
      <mark key={`h${i}`} className="source-highlight">
        {text.slice(range.start, range.end)}
      </mark>,
    )
    cursor = range.end
  })
  if (cursor < text.length) parts.push(<Fragment key="tail">{text.slice(cursor)}</Fragment>)
  return <>{parts}</>
}

export function ReviewSourcePassage({
  chunk,
  quotes,
}: {
  chunk: ReviewChunkOut
  quotes: string[]
}) {
  const [viewingOriginal, setViewingOriginal] = useState(false)

  return (
    <div className="source-passage">
      <div className="source-passage-header">
        <p className="label source-passage-label">
          From the source — {formatLocator(chunk.locator)}
        </p>
        {EMBEDDABLE_KINDS.has(chunk.source_kind) && (
          <button
            type="button"
            className="source-passage-view-original"
            onClick={() => setViewingOriginal(true)}
          >
            View original page ↗
          </button>
        )}
      </div>
      <p className="body-sm source-passage-text">
        <HighlightedText text={chunk.text} quotes={quotes} />
      </p>
      {viewingOriginal && (
        <SourcePageViewer
          sourceId={chunk.source_id}
          page={chunk.locator.page}
          onClose={() => setViewingOriginal(false)}
        />
      )}
    </div>
  )
}
