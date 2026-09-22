"""Study/quiz routes — docs/IMPLEMENTATION_PLAN.md M4, extended for the Quiz redesign that
`design/synapse`'s `QuizCard` required.

Two ways to answer an item, sharing the same grading pipeline:
- Standalone (`POST /api/study/session` + `POST /api/study/answer` with no
  `quiz_attempt_id`) — the original M4 flow, an unscoped queue.
- As part of a `QuizAttempt` (`POST /api/study/quiz` to start one, then `POST
  /api/study/answer` with that `quiz_attempt_id` for each item) — a week-scoped, resumable,
  repeatable attempt. Design decision from that conversation: a week's quiz is "available"
  once the week has any *studyable* Item (M6: `status` in `STUDYABLE_STATUSES`, below), and a
  week can have any number of attempts, not one slot that locks after use. A `draft` item
  never appears here — that's the whole point of the M6 review queue
  (`GET /api/items/review`, `apps/api/routers/items.py`): it's the only door into
  `approved`/`edited`.

Locked section per `design/synapse`'s `SiteNav`: `require_owner` gates the whole router.

No `Deck` table exists yet (that's not an M2/M3/M4 deliverable), so both the standalone
queue and the quiz's item selection filter `Item` directly by week/topics rather than
through a deck.
"""

import json
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.config import settings
from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, get_llm_client, require_owner
from apps.api.schemas.study import (
    ItemSourceResponse,
    QuizAttemptOut,
    QuizReviewItem,
    QuizReviewResponse,
    RubricHit,
    SourceExcerpt,
    StartQuizRequest,
    StartQuizResponse,
    StudyAnswerRequest,
    StudyAnswerResponse,
    StudyQueueItem,
    StudySessionRequest,
    WeekQuizzes,
)
from apps.api.services.budget import (
    BudgetExceededError,
    enforce_daily_budget,
    estimate_call_tokens,
)
from apps.api.services.grading import (
    GradingFailedError,
    compute_score,
    grade_response,
    response_hash_for,
)
from packages.core.llm import LLMClient
from packages.db.models import (
    Attempt,
    Chunk,
    Item,
    ItemStatus,
    QuizAttempt,
    QuizAttemptStatus,
    Source,
)

router = APIRouter(prefix="/api/study", tags=["study"], dependencies=[Depends(require_owner)])

# M6: an item must clear the review queue before a student can be quizzed on it. `edited`
# counts as reviewed too — saving an edit in the review UI is itself a review decision, not
# a reason to make the reviewer click Approve again right after.
STUDYABLE_STATUSES = (ItemStatus.approved, ItemStatus.edited)


def _queue_item(item: Item) -> StudyQueueItem:
    return StudyQueueItem(
        id=item.id, type=item.type, prompt=item.prompt, difficulty=item.difficulty,
        bloom=item.bloom, topics=item.topics,
    )


@router.post("/session", response_model=list[StudyQueueItem])
async def start_session(
    body: StudySessionRequest,
    session: AsyncSession = Depends(get_session),
) -> list[StudyQueueItem]:
    stmt = select(Item).where(Item.status.in_(STUDYABLE_STATUSES))
    if body.week is not None:
        stmt = stmt.join(Source, Source.id == Item.source_id).where(Source.week == body.week)
    if body.topics:
        stmt = stmt.where(Item.topics.op("&&")(body.topics))
    stmt = stmt.order_by(Item.created_at).limit(body.limit)

    items = (await session.scalars(stmt)).all()
    return [_queue_item(item) for item in items]


@router.get("/items/{item_id}/source", response_model=ItemSourceResponse)
async def get_item_source(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ItemSourceResponse:
    """"I don't know this one" — the passage an item is anchored to, with no LLM call and
    no rubric/reference_answer attached. See `ItemSourceResponse`'s docstring for why this
    is not the same thing as a reveal-the-answer button."""
    item = await session.get(Item, item_id)
    if item is None or not item.chunk_ids:
        raise HTTPException(status_code=404, detail="item not found")
    chunk = await session.get(Chunk, item.chunk_ids[0])
    if chunk is None:
        raise HTTPException(status_code=404, detail="source chunk not found")
    locator = chunk.locators[0] if chunk.locators else {}
    return ItemSourceResponse(locator=locator, text=chunk.text)


def _source_excerpts(item: Item, chunks: list[Chunk]) -> list[SourceExcerpt]:
    """One excerpt per rubric point, using that point's own `support_quote`. Every rubric
    point is anchored in `item.chunk_ids[0]` — the M3 generator never produces an item
    spanning more than one chunk — so all points share that chunk's locator."""
    chunk_by_id = {c.id: c for c in chunks}
    chunk = chunk_by_id.get(item.chunk_ids[0]) if item.chunk_ids else None
    locator = chunk.locators[0] if chunk and chunk.locators else {}
    return [SourceExcerpt(locator=locator, quote=p["support_quote"]) for p in item.rubric]


def _rubric_hits(item: Item, attempt: Attempt) -> list[RubricHit]:
    rubric_by_id = {p["id"]: p for p in item.rubric}
    covered_by_id = {h["point_id"]: h["covered"] for h in attempt.rubric_hits}
    evidence_by_id = {h["point_id"]: h["evidence"] for h in attempt.rubric_hits}
    return [
        RubricHit(
            point_id=pid,
            point=p["point"],
            weight=p["weight"],
            covered=covered_by_id.get(pid, False),
            evidence=evidence_by_id.get(pid, ""),
        )
        for pid, p in rubric_by_id.items()
    ]


def _attempt_to_response(
    attempt: Attempt, item: Item, chunks: list[Chunk], *, cached: bool
) -> StudyAnswerResponse:
    return StudyAnswerResponse(
        score=attempt.score,
        rubric_hits=_rubric_hits(item, attempt),
        misconceptions=attempt.misconceptions,
        feedback_md=attempt.feedback_md,
        reference_answer=item.reference_answer,
        source=_source_excerpts(item, chunks),
        cached=cached,
    )


async def _maybe_complete_quiz(session: AsyncSession, quiz_attempt: QuizAttempt) -> None:
    """Marks the attempt completed once every one of its frozen `item_ids` has a graded
    `Attempt` row. Uses each item's *latest* row (ordered by `created_at`) so a rare
    re-answer of the same item within one attempt doesn't double-count — see the module
    docstring's note that re-answering isn't blocked, just not double-weighted."""
    if quiz_attempt.status == QuizAttemptStatus.completed:
        return

    rows = (
        await session.execute(
            select(Attempt.item_id, Attempt.score)
            .where(Attempt.quiz_attempt_id == quiz_attempt.id)
            .order_by(Attempt.created_at)
        )
    ).all()
    latest_score_by_item: dict[uuid.UUID, float] = dict(rows)

    if not set(quiz_attempt.item_ids) <= set(latest_score_by_item):
        return

    scores = [latest_score_by_item[item_id] for item_id in quiz_attempt.item_ids]
    quiz_attempt.score = sum(scores) / len(scores)
    quiz_attempt.status = QuizAttemptStatus.completed
    quiz_attempt.completed_at = datetime.now(UTC)


@router.post("/quiz", response_model=StartQuizResponse)
async def start_quiz(
    body: StartQuizRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> StartQuizResponse:
    stmt = (
        select(Item)
        .join(Source, Source.id == Item.source_id)
        .where(Source.week == body.week, Item.status.in_(STUDYABLE_STATUSES))
        .order_by(Item.created_at)
        .limit(body.limit)
    )
    items = (await session.scalars(stmt)).all()
    if not items:
        raise HTTPException(
            status_code=404, detail=f"no items available for week {body.week} yet"
        )

    quiz_attempt = QuizAttempt(user_id=user_id, week=body.week, item_ids=[i.id for i in items])
    session.add(quiz_attempt)
    await session.commit()

    return StartQuizResponse(
        quiz_attempt_id=quiz_attempt.id,
        week=body.week,
        items=[_queue_item(item) for item in items],
    )


def _quiz_attempt_out(attempt: QuizAttempt) -> QuizAttemptOut:
    return QuizAttemptOut(
        id=attempt.id,
        week=attempt.week,
        status=attempt.status,
        score=attempt.score,
        item_count=len(attempt.item_ids),
        started_at=attempt.created_at,
        completed_at=attempt.completed_at,
    )


@router.get("/weeks", response_model=list[WeekQuizzes])
async def list_quiz_weeks(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[WeekQuizzes]:
    item_counts = (
        await session.execute(
            select(Source.week, func.count(Item.id))
            .join(Item, Item.source_id == Source.id)
            .where(Item.status.in_(STUDYABLE_STATUSES), Source.week.is_not(None))
            .group_by(Source.week)
        )
    ).all()

    attempts = (
        await session.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user_id)
            .order_by(QuizAttempt.created_at.desc())
        )
    ).all()
    attempts_by_week: dict[int, list[QuizAttempt]] = {}
    for attempt in attempts:
        attempts_by_week.setdefault(attempt.week, []).append(attempt)

    return [
        WeekQuizzes(
            week=week,
            item_count=count,
            attempts=[_quiz_attempt_out(a) for a in attempts_by_week.get(week, [])],
        )
        for week, count in sorted(item_counts)
    ]


@router.get("/quiz/{quiz_attempt_id}", response_model=QuizReviewResponse)
async def review_quiz(
    quiz_attempt_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> QuizReviewResponse:
    quiz_attempt = await session.get(QuizAttempt, quiz_attempt_id)
    if quiz_attempt is None or quiz_attempt.user_id != user_id:
        raise HTTPException(status_code=404, detail="quiz attempt not found")

    items = (
        await session.scalars(select(Item).where(Item.id.in_(quiz_attempt.item_ids)))
    ).all()
    items_by_id = {item.id: item for item in items}

    chunk_ids = {cid for item in items for cid in item.chunk_ids}
    chunks = (await session.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids)))).all()

    graded = (
        await session.scalars(
            select(Attempt)
            .where(Attempt.quiz_attempt_id == quiz_attempt_id)
            .order_by(Attempt.created_at)
        )
    ).all()
    latest_attempt_by_item: dict[uuid.UUID, Attempt] = {a.item_id: a for a in graded}

    results = []
    for item_id in quiz_attempt.item_ids:
        item = items_by_id.get(item_id)
        attempt = latest_attempt_by_item.get(item_id)
        if item is None or attempt is None:
            continue  # not answered yet — attempt still in_progress
        results.append(
            QuizReviewItem(
                item_id=item.id,
                prompt=item.prompt,
                response_text=attempt.response_text,
                score=attempt.score,
                rubric_hits=_rubric_hits(item, attempt),
                misconceptions=attempt.misconceptions,
                feedback_md=attempt.feedback_md,
                reference_answer=item.reference_answer,
                source=_source_excerpts(item, chunks),
            )
        )

    ordered_items = [
        items_by_id[item_id] for item_id in quiz_attempt.item_ids if item_id in items_by_id
    ]
    return QuizReviewResponse(
        quiz_attempt=_quiz_attempt_out(quiz_attempt),
        items=[_queue_item(item) for item in ordered_items],
        results=results,
    )


@router.post("/answer", response_model=StudyAnswerResponse)
async def answer(
    body: StudyAnswerRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
    llm: LLMClient = Depends(get_llm_client),
) -> StudyAnswerResponse:
    item = await session.get(Item, body.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    quiz_attempt: QuizAttempt | None = None
    if body.quiz_attempt_id is not None:
        quiz_attempt = await session.get(QuizAttempt, body.quiz_attempt_id)
        if quiz_attempt is None or quiz_attempt.user_id != user_id:
            raise HTTPException(status_code=404, detail="quiz attempt not found")
        if quiz_attempt.status == QuizAttemptStatus.completed:
            raise HTTPException(status_code=409, detail="quiz attempt already completed")
        if item.id not in quiz_attempt.item_ids:
            raise HTTPException(
                status_code=422, detail="item is not part of this quiz attempt"
            )

    chunks = (
        await session.scalars(select(Chunk).where(Chunk.id.in_(item.chunk_ids)))
    ).all()

    response_hash = response_hash_for(item.id, body.response_text)
    cached = await session.scalar(
        select(Attempt).where(
            Attempt.user_id == user_id,
            Attempt.item_id == item.id,
            Attempt.response_hash == response_hash,
        )
    )

    if cached is not None and quiz_attempt is None:
        return _attempt_to_response(cached, item, chunks, cached=True)

    if cached is not None:
        # Reuses the cached grading (no new LLM call, tokens_used=0) but still persists a
        # fresh row scoped to this quiz attempt, so "review answers" has one row per item
        # regardless of which attempt first produced the grading.
        attempt = Attempt(
            user_id=user_id,
            item_id=item.id,
            quiz_attempt_id=quiz_attempt.id,
            response_text=body.response_text,
            response_hash=response_hash,
            score=cached.score,
            rubric_hits=cached.rubric_hits,
            misconceptions=cached.misconceptions,
            feedback_md=cached.feedback_md,
            grader_model=cached.grader_model,
            latency_ms=0,
            tokens_used=0,
        )
        session.add(attempt)
        await _maybe_complete_quiz(session, quiz_attempt)
        await session.commit()
        return _attempt_to_response(attempt, item, chunks, cached=True)

    estimated_tokens = estimate_call_tokens(
        item.prompt, json.dumps(item.rubric), body.response_text
    )
    try:
        await enforce_daily_budget(
            session,
            user_id=user_id,
            estimated_tokens=estimated_tokens,
            daily_token_budget=settings.daily_token_budget,
            max_gradings_per_day=settings.max_gradings_per_day,
        )
    except BudgetExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    started = time.monotonic()
    try:
        graded = await grade_response(
            item_prompt=item.prompt, rubric=item.rubric, response_text=body.response_text, llm=llm
        )
    except GradingFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    latency_ms = int((time.monotonic() - started) * 1000)

    covered_by_id = {p.point_id: p.covered for p in graded.points}
    score = compute_score(item.rubric, covered_by_id)

    attempt = Attempt(
        user_id=user_id,
        item_id=item.id,
        quiz_attempt_id=quiz_attempt.id if quiz_attempt is not None else None,
        response_text=body.response_text,
        response_hash=response_hash,
        score=score,
        rubric_hits=[p.model_dump() for p in graded.points],
        misconceptions=graded.misconceptions,
        feedback_md=graded.feedback_md,
        grader_model=llm.model_name,
        latency_ms=latency_ms,
        tokens_used=estimated_tokens,
    )
    session.add(attempt)
    if quiz_attempt is not None:
        await _maybe_complete_quiz(session, quiz_attempt)
    await session.commit()

    return _attempt_to_response(attempt, item, chunks, cached=False)
