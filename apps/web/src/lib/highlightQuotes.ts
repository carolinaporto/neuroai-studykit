// Finds where each literal quote sits inside a chunk's full text, so the UI can highlight
// the exact supporting passage instead of just listing short quotes separately. Whitespace
// in `quotes` is matched loosely (any run of whitespace matches any run in the text) for the
// same reason apps/api's collapse_whitespace exists: PDF extraction wraps lines mid-sentence,
// so a literal match needs to tolerate that without pretending to tolerate anything else.

export interface HighlightRange {
  start: number
  end: number
}

function buildQuotePattern(quote: string): RegExp | null {
  const trimmed = quote.trim()
  if (!trimmed) return null
  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const flexible = escaped.replace(/\s+/g, '\\s+')
  return new RegExp(flexible)
}

export function findHighlightRanges(text: string, quotes: string[]): HighlightRange[] {
  const ranges: HighlightRange[] = []
  for (const quote of quotes) {
    const pattern = buildQuotePattern(quote)
    if (!pattern) continue
    const match = pattern.exec(text)
    if (match) {
      ranges.push({ start: match.index, end: match.index + match[0].length })
    }
  }

  ranges.sort((a, b) => a.start - b.start)
  const merged: HighlightRange[] = []
  for (const range of ranges) {
    const last = merged[merged.length - 1]
    if (last && range.start <= last.end) {
      last.end = Math.max(last.end, range.end)
    } else {
      merged.push({ ...range })
    }
  }
  return merged
}
