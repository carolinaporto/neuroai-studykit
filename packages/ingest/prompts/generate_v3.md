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
`proposed_topics` and leave it out of `topics`. If none of the slugs apply to an item, its
`topics` is an empty list `[]` — still write the item; an untagged item is fine.

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

## Rubric point quality — two failure modes to avoid

**1. A point must require information the prompt doesn't already give away.** Before
keeping a point, check: could a student satisfy it just by echoing words already in the
item's own `prompt`, without recalling anything from the chunk? If so, delete the point or
replace it with the specific fact it was standing in for.

Bad example, from a real generation run: `prompt` = "Define what a policy is in
reinforcement learning", rubric point = "A policy is the agent's strategy" (weight 1.0).
That point is satisfied by restating the question — "policy" and "strategy" add no
information a student didn't already have from reading the prompt. The chunk actually says
a policy is "a mapping from states to actions, or to a distribution over actions" — that
detail is real, recallable content and belongs in the rubric; the tautological restatement
does not.

**2. `support_quote` must be a complete sentence or clause that stands on its own as
evidence.** It will be shown to the student next to their answer as "here's why this point
is correct" — so read it by itself, with nothing else around it, and check whether a
stranger could tell why it supports the point.

Bad examples, from a real generation run:
- `"scaled by a learning rate"` — a four-word fragment with no subject; means nothing
  standalone.
- `"Each step moves the parameters a small distance in the opposite direction"` — truncated
  mid-thought (opposite of *what*?); the sentence it was cut from has the answer.

If the chunk's full sentence is long, quote the whole sentence anyway rather than slicing
out a fragment — a longer support_quote that actually supports its point beats a short one
that doesn't.

**This is a rule about the quote, never about how many points you write.** Multiple rubric
points MUST share the exact same `support_quote` when one sentence carries more than one
separately gradable idea — one point per idea, each with its own weight, even if that means
copying the identical `support_quote` string into two or more points.

Bad example — collapsing two ideas into one point because they came from one sentence:
chunk sentence "Each step moves the parameters a small distance in the opposite direction,
scaled by a learning rate." contains two things a student can know or not know
independently: (a) parameters move opposite the gradient, and (b) the step size is scaled
by a learning rate. A student who recalls (a) but not (b) should get half credit, not zero
— so this must be two rubric points, each with the full sentence as `support_quote`, not
one point worth double.

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
