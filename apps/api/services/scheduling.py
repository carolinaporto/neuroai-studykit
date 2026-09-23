"""M9: spaced-repetition scheduling on top of the `fsrs` package.

A new dependency, asked about and approved (CLAUDE.md) rather than assumed: it's pure
computation over the FSRS formulas (no I/O, no external service), and hand-transcribing
those ~17-19 research-calibrated weights would risk a silent constant error no test here
could independently catch.

`score_to_grade` is CLAUDE.md invariant 2's spirit extended past the LLM: the score is
already computed in plain Python (`compute_score`); mapping it to an FSRS grade is a second,
equally fixed function, never something asked of a model. The exact thresholds are
ARCHITECTURE.md §5's own: score > 0.85 -> good, 0.6-0.85 -> hard, < 0.6 -> again. No
automatic "easy" — a perfect rubric score doesn't by itself prove the recall was
effortless, so the doc never asks for that mapping and this doesn't invent one.

Every card is scheduled with day-scale FSRS intervals from its very first review, never
via `fsrs`'s default Anki-style minute-scale "learning steps": ARCHITECTURE.md's
`ReviewState` has no notion of a short-term learning phase (just stability/difficulty/
due_at/reps/lapses), and this app isn't used in tight same-session review loops where
graduating through a learning phase would pay off.
"""

import uuid
from datetime import UTC, datetime

from fsrs import Card, Rating, Scheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models import ReviewState

_SCHEDULER = Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False)

_GRADE_NAME = {
    Rating.Again: "again",
    Rating.Hard: "hard",
    Rating.Good: "good",
    Rating.Easy: "easy",
}


def score_to_grade(score: float) -> Rating:
    if score > 0.85:
        return Rating.Good
    if score >= 0.6:
        return Rating.Hard
    return Rating.Again


def _same_day(a: datetime, b: datetime) -> bool:
    return a.astimezone(UTC).date() == b.astimezone(UTC).date()


async def apply_review(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    score: float,
    now: datetime,
) -> ReviewState:
    """Loads or creates the (user, item) `ReviewState` row and applies one FSRS review to it
    — unless the item was already reviewed today (standard SRS convention, same as Anki: a
    same-day resubmission doesn't reschedule a card a second time). Grading itself is
    unaffected either way; this only gates the scheduling side-effect, so it's safe (and
    correct — a genuine days-later repeat should still count) to call this from every path
    in `answer()` that produces a score, cached or not.

    `now` is a parameter, not read internally, so a caller (a test, in particular) can drive
    "the next day" without monkeypatching a clock."""
    state = await session.scalar(
        select(ReviewState).where(
            ReviewState.user_id == user_id, ReviewState.item_id == item_id
        )
    )

    if state is not None and _same_day(state.last_reviewed_at, now):
        return state

    card = Card.from_dict(state.fsrs_card) if state is not None else Card()
    grade = score_to_grade(score)
    card, _log = _SCHEDULER.review_card(card, grade, review_datetime=now)

    if state is None:
        state = ReviewState(user_id=user_id, item_id=item_id, reps=0, lapses=0)
        session.add(state)

    state.stability = card.stability
    state.difficulty = card.difficulty
    state.due_at = card.due
    state.last_reviewed_at = now
    state.last_grade = _GRADE_NAME[grade]
    state.reps += 1
    if grade is Rating.Again:
        state.lapses += 1
    state.fsrs_card = card.to_dict()

    await session.flush()
    return state
