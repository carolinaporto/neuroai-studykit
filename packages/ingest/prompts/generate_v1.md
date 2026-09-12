# Generate practice-testing items from a single course-material chunk

You are generating exam-style practice questions for a student studying from their own
course material. Every question must be answerable by someone who read and understood the
chunk below, from memory, without the chunk in front of them — and only from information
stated in the chunk.

Write everything in English: the `prompt`, `reference_answer`, `rubric[].point`, and any
`proposed_topics`.

## Source chunk

"""
{{chunk_text}}
"""

## Allowed topics

Choose `topics` only from this list (use one or more, exactly as the slug is written):
{{topics_csv}}

If a central concept in the chunk genuinely isn't covered by any slug or alias above, do
NOT force it onto the closest slug. Instead add a short free-text label for it to
`proposed_topics` and leave it out of `topics`.

## What to produce

Return 0 to 4 items. Zero is correct and expected for a chunk with no substantive content
(a title slide, a references page, a pure transition). Never invent an item just to have
something to return.

When there is real content, mix `free_recall` and `term_def`:
- `free_recall`: asks the student to explain a mechanism, process, or relationship from the
  chunk, in their own words, from memory. Do not name the key term being tested in the
  question stem.
- `term_def`: asks the student to define or identify a specific term named in the chunk.

For every item, write a rubric of 2 to 5 points that together capture what a complete
answer must contain. Each point needs:
- `point`: one fact or idea the answer must include, in your own words.
- `weight`: how important the point is to a correct answer, any positive number (points do
  not need to sum to 1; only relative weight matters).
- `support_quote`: the EXACT sentence or clause from the chunk above that justifies this
  point. Copy it character-for-character — no paraphrasing, no ellipsis, no fixing typos or
  punctuation. If you cannot find an exact quote for a point, drop the point instead of
  inventing one.

## Hard constraints

- Never let the wording of the question give away the answer: no `support_quote` text, and
  no close paraphrase of one, may appear inside the item's own `prompt`.
- Every item must stand on its own, as it would on a closed-book exam. Never refer to "the
  text", "the passage", "the excerpt above", "the lecture", or similar — the student will
  not have it in front of them when answering.
- `reference_answer` is a model answer, in full sentences, that would score every rubric
  point.
- `difficulty` is 1 (trivial recall) to 5 (requires connecting multiple ideas in the chunk).
- `bloom` is one of: recall, understand, apply, analyze.
- Base every item only on this chunk. Do not use outside knowledge of the subject to add
  facts the chunk does not state.

## Output format

Return ONLY a JSON object, no markdown fences, no commentary, matching exactly:

{
  "items": [
    {
      "type": "free_recall" | "term_def",
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

`items` may be an empty list. `proposed_topics` may be an empty list and is omitted from
persisted items either way — it only feeds the vocabulary review.
