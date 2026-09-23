The recall check the professor asks for at the start of every class — a short quiz on last week's content, so the material sticks as native knowledge rather than something you'd have to look up again. Consumer provides the week, the item count and the week's attempt history.

Two body states, not three — built (`apps/web/src/components/QuizCard.tsx`), a week allows more than one attempt (retries, later review), so "completed" isn't a slot that replaces "available"; attempt history lists underneath instead:
- **Locked** — `surface-200` icon tile with the lock glyph in `ink-soft`, a `disabled` button repeating the lock glyph and the word "Locked." Meta line says what's missing: "Sources not uploaded yet" (`itemCount === 0`), not a homework-completion gate.
- **Available** — `accent-neuro-soft` icon tile with a check-target glyph in `accent-neuro`, question count in `caption`, a primary `Start quiz` button. Stays available (re-startable) even after one or more completed attempts.
- Each past attempt renders as a row below the card body — `success`-ringed score (`8/10`, set in `code`) for a completed one, a plain in-progress marker otherwise — with a secondary `Review answers` action, never a primary button.

Keep the card's top row (week tag + "Recall check" eyebrow + title) identical across every state; only the body and the button change. Never use `danger` on a score ring, even for a low score — a completed attempt is a `success` state regardless of the number; a genuinely failed attempt gets a retry affordance (starting a new attempt), not a red score ring.
