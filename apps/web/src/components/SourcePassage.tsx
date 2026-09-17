import { useQuery } from '@tanstack/react-query'
import { Fragment, useMemo } from 'react'

import { getItemSource } from '../api/client'
import { findHighlightRanges } from '../lib/highlightQuotes'
import { formatLocator } from '../lib/locator'
import './SourcePassage.css'

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

// The real class material an item is anchored to — full chunk text, not a paraphrase, with
// the rubric's supporting quotes highlighted in place. Reuses GET /api/study/items/{id}/source
// (no LLM call, already built for the quiz "skip" flow) rather than the short disconnected
// quotes StudyAnswerResponse.source carries — those stay literal too, but out of context
// they read like fragments; seeing them inside the real passage is what the user asked for.
export function SourcePassage({ itemId, quotes }: { itemId: string; quotes: string[] }) {
  const query = useQuery({
    queryKey: ['item-source', itemId],
    queryFn: () => getItemSource(itemId),
  })

  if (query.isLoading) return <p className="caption">Loading source…</p>
  if (query.isError || !query.data) return null

  return (
    <div className="source-passage">
      <p className="label source-passage-label">
        From the source — {formatLocator(query.data.locator)}
      </p>
      <p className="body-sm source-passage-text">
        <HighlightedText text={query.data.text} quotes={quotes} />
      </p>
    </div>
  )
}
