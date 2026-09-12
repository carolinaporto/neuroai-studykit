"""`POST /api/study/session` and `POST /api/study/answer` — docs/IMPLEMENTATION_PLAN.md M4.

No `Deck` table exists yet (that's not an M2/M3/M4 deliverable), so the session queue
filters `Item` directly by week/topics rather than through a deck.
"""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, get_llm_client
from apps.api.schemas.study import (
    RubricHit,
    SourceExcerpt,
    StudyAnswerRequest,
    StudyAnswerResponse,
    StudyQueueItem,
    StudySessionRequest,
)
from apps.api.services.grading import (
    GradingFailedError,
    compute_score,
    grade_response,
    response_hash_for,
)
from packages.core.llm import LLMClient
from packages.db.models import Attempt, Chunk, Item, ItemStatus, Source

router = APIRouter(prefix="/api/study", tags=["study"])


@router.post("/session", response_model=list[StudyQueueItem])
async def start_session(
    body: StudySessionRequest,
    session: AsyncSession = Depends(get_session),
) -> list[StudyQueueItem]:
    stmt = select(Item).where(Item.status != ItemStatus.retired)
    if body.week is not None:
        stmt = stmt.join(Source, Source.id == Item.source_id).where(Source.week == body.week)
    if body.topics:
        stmt = stmt.where(Item.topics.op("&&")(body.topics))
    stmt = stmt.order_by(Item.created_at).limit(body.limit)

    items = (await session.scalars(stmt)).all()
    return [
        StudyQueueItem(
            id=item.id,
            type=item.type,
            prompt=item.prompt,
            difficulty=item.difficulty,
            bloom=item.bloom,
            topics=item.topics,
        )
        for item in items
    ]


def _source_excerpts(item: Item, chunks: list[Chunk]) -> list[SourceExcerpt]:
    """One excerpt per rubric point, using that point's own `support_quote`. Every rubric
    point is anchored in `item.chunk_ids[0]` — the M3 generator never produces an item
    spanning more than one chunk — so all points share that chunk's locator."""
    chunk_by_id = {c.id: c for c in chunks}
    chunk = chunk_by_id.get(item.chunk_ids[0]) if item.chunk_ids else None
    locator = chunk.locators[0] if chunk and chunk.locators else {}
    return [SourceExcerpt(locator=locator, quote=p["support_quote"]) for p in item.rubric]


def _attempt_to_response(
    attempt: Attempt, item: Item, chunks: list[Chunk], *, cached: bool
) -> StudyAnswerResponse:
    rubric_by_id = {p["id"]: p for p in item.rubric}
    covered_by_id = {h["point_id"]: h["covered"] for h in attempt.rubric_hits}
    evidence_by_id = {h["point_id"]: h["evidence"] for h in attempt.rubric_hits}
    rubric_hits = [
        RubricHit(
            point_id=pid,
            point=p["point"],
            weight=p["weight"],
            covered=covered_by_id.get(pid, False),
            evidence=evidence_by_id.get(pid, ""),
        )
        for pid, p in rubric_by_id.items()
    ]
    return StudyAnswerResponse(
        score=attempt.score,
        rubric_hits=rubric_hits,
        misconceptions=attempt.misconceptions,
        feedback_md=attempt.feedback_md,
        reference_answer=item.reference_answer,
        source=_source_excerpts(item, chunks),
        cached=cached,
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
    if cached is not None:
        return _attempt_to_response(cached, item, chunks, cached=True)

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
        response_text=body.response_text,
        response_hash=response_hash,
        score=score,
        rubric_hits=[p.model_dump() for p in graded.points],
        misconceptions=graded.misconceptions,
        feedback_md=graded.feedback_md,
        grader_model=llm.model_name,
        latency_ms=latency_ms,
    )
    session.add(attempt)
    await session.commit()

    return _attempt_to_response(attempt, item, chunks, cached=False)
