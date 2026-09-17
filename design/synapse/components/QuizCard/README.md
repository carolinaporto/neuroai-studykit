The recall check the professor asks for at the start of every class — a short quiz on last week's content, so the material sticks as native knowledge rather than something you'd have to look up again. Consumer provides the week, the quiz's state and, once completed, the score.

Three states, never combined on one card:
- **Locked** — `surface-200` icon tile with the lock glyph in `ink-soft`, a `disabled` button repeating the lock glyph and the word "Locked." Meta line says what unlocks it (this week's homework, not "later").
- **Available** — `accent-neuro-soft` icon tile with a check-target glyph in `accent-neuro`, question count and time estimate in `caption`, a primary `Start quiz` button.
- **Completed** — a `success`-ringed score circle (`8/10`, set in `code` inside the ring) replaces the icon tile, the completion date in `caption`, and a secondary `Review answers` button — never a primary button once the quiz is done.

Keep the card's top row (week tag + "Recall check" eyebrow + title) identical across all three states; only the body and the button change. Never use `danger` on this card, even for a low score — a completed quiz is a `success` state regardless of the number; a genuinely failed attempt gets a retry affordance in a future component, not a red score ring here.
