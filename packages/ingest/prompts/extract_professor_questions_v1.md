# Extract the professor's own "Facts to know" / "Questions to have a thoughtful answer to" questions

This course's slide decks often end with two lists in the professor's own words: a
"Facts to know" list and a "Questions to have a thoughtful answer to" list. Your job here
is narrower than normal generation — you are **extracting**, not inventing. Every item's
`prompt` must be one of the professor's own listed questions, copied over (only correcting
the PDF extractor's mid-sentence line-wraps back into a single line — never paraphrased,
reworded, shortened, or combined with another question).

Write everything in English: `prompt` stays exactly as the source states it (already
English); `reference_answer`, `rubric[].point`, and any `proposed_topics` are still yours to
write.

## Source

The full text of one source (every chunk, in page order), below. The two heading lists —
if present — can be anywhere in it, and the material that actually answers a listed
question is very often on a *different* page than the list itself; search the whole text
for `support_quote`s, not just the sentence next to the question.

"""
{{chunk_text}}
"""

## Allowed topics

Choose `topics` only from this list (use one or more, exactly as the slug is written); the
same "don't force it, use proposed_topics instead" rule from ordinary generation applies:
{{topics_csv}}

## What to produce

First, check: does the text above contain a "Facts to know" list, a "Questions to have a
thoughtful answer to" list, or both? Search case-insensitively; the exact wording of the
heading can vary slightly. If **neither** is present, return `{"items": []}` — do not invent
substitute questions.

If either is present, produce exactly one `free_recall` item per question literally listed
under it — no more, no fewer, and no item for anything not literally on one of these two
lists (a normal lecture question, a rhetorical aside, a section title). There is no 0-to-4
cap here, unlike ordinary generation: if the professor listed eight questions, extract eight
items.

For each item:
- `type` is always `"free_recall"`.
- `prompt` is the listed question, verbatim (only whitespace/line-wrap normalized) — never
  the topic name or a rephrasing of it.
- `reference_answer`: a model answer, in full sentences, that would score every rubric point
  — written by you, same as ordinary generation.
- `rubric`: 2 to 5 points (same quality rules as ordinary generation — see below), each with
  a real `support_quote` copied character-for-character from *anywhere* in the source text
  above, not necessarily near the question itself.
- `difficulty` (1-5) and `bloom` (recall/understand/apply/analyze), same meaning as ordinary
  generation.
- `topics`/`proposed_topics`, same rules as ordinary generation.
- No `choices` — extracted items are never `mcq`.

## Rubric point quality

Same two rules as ordinary generation:

1. A point must require information the question's own wording doesn't already give away —
   never a tautological restatement of the question.
2. `support_quote` must be a complete sentence or clause that stands on its own as evidence,
   never a fragment truncated mid-thought. Multiple points may share the same `support_quote`
   when one sentence carries more than one separately gradable idea.

## Hard constraints

- Never invent a question. If you cannot find at least 2 independently gradable, real
  `support_quote`s anywhere in the source text for a listed question, drop that item
  entirely — never pad the rubric with a low-value or repeated point just to reach 2, and
  never fabricate a `support_quote` that isn't an exact copy from the text above.
- No `support_quote` (or a close paraphrase of one) may appear inside the item's own
  `prompt` — same self-answerable check as ordinary generation.
- Base every rubric point only on this source's text. Do not use outside knowledge of the
  subject to add facts the text does not state.

## Output format

Return ONLY a JSON object, no markdown fences, no commentary, matching exactly:

{
  "items": [
    {
      "type": "free_recall",
      "prompt": "string",
      "reference_answer": "string",
      "rubric": [
        {"point": "string", "weight": 1.0, "support_quote": "string"}
      ],
      "difficulty": 1,
      "bloom": "recall" | "understand" | "apply" | "analyze",
      "topics": ["string"],
      "proposed_topics": ["string"]
    }
  ]
}

`items` may be an empty list — that's correct and expected when neither heading is present.
`proposed_topics` may be an empty list and is omitted from persisted items either way.
