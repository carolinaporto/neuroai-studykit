import { describe, expect, it } from 'vitest'

import { findHighlightRanges } from './highlightQuotes'

describe('findHighlightRanges', () => {
  it('finds a literal quote inside the text', () => {
    const text = 'Hebbian plasticity is often summarized as cells that fire together.'
    const quote = 'cells that fire together'
    const ranges = findHighlightRanges(text, [quote])
    expect(ranges).toEqual([
      { start: text.indexOf(quote), end: text.indexOf(quote) + quote.length },
    ])
    expect(text.slice(ranges[0].start, ranges[0].end)).toBe(quote)
  })

  it('matches across a whitespace run that differs from the quote (mid-sentence PDF wrap)', () => {
    const text = 'cells that fire\ntogether wire together'
    const ranges = findHighlightRanges(text, ['cells that fire together'])
    expect(ranges).toHaveLength(1)
  })

  it('merges overlapping ranges from multiple quotes into one', () => {
    const text = 'the quick brown fox jumps over the lazy dog'
    const ranges = findHighlightRanges(text, ['quick brown', 'brown fox jumps'])
    expect(ranges).toHaveLength(1)
    expect(ranges[0].start).toBe(text.indexOf('quick brown'))
    expect(ranges[0].end).toBe(text.indexOf('brown fox jumps') + 'brown fox jumps'.length)
  })

  it('keeps non-overlapping ranges separate, sorted by position', () => {
    const text = 'alpha beta gamma delta'
    const ranges = findHighlightRanges(text, ['delta', 'alpha'])
    expect(ranges).toEqual([
      { start: text.indexOf('alpha'), end: text.indexOf('alpha') + 'alpha'.length },
      { start: text.indexOf('delta'), end: text.indexOf('delta') + 'delta'.length },
    ])
  })

  it('ignores a quote that is not found in the text', () => {
    const text = 'something entirely different'
    expect(findHighlightRanges(text, ['not present here'])).toEqual([])
  })

  it('ignores empty/whitespace-only quotes', () => {
    expect(findHighlightRanges('some text', ['', '   '])).toEqual([])
  })
})
