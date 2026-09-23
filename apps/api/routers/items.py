"""`PATCH /api/items/{id}` — docs/IMPLEMENTATION_PLAN.md M4, covers approve/edit/retire.
`GET /api/items/review` — M6, the review queue that drives that PATCH. Owner-only: this
whole router is a review surface, never public."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.schemas.items import ItemOut, ItemPatchRequest, ReviewItemOut, WeekReviewQueue
from packages.db.models import Chunk, Item, ItemBloom, ItemStatus, ItemType, Source
from packages.ingest.topics import load_topics
from packages.ingest.validators import collapse_whitespace

router = APIRouter(prefix="/api/items", tags=["items"], dependencies=[Depends(require_owner)])

MIN_RUBRIC_POINTS = 2
MAX_RUBRIC_POINTS = 5


@router.get("/review", response_model=list[WeekReviewQueue])
async def list_review_queue(
    session: AsyncSession = Depends(get_session),
) -> list[WeekReviewQueue]:
    """Every `draft` item, grouped by week, each with its anchor chunk embedded (invariant
    1's citation and locator are what the reviewer is actually judging, so they travel with
    the item rather than needing a second fetch). A week with zero drafts just isn't in the
    list — same convention as `list_sources` in `apps/api/routers/sources.py`."""
    rows = (
        await session.execute(
            select(Item, Source.week)
            .join(Source, Source.id == Item.source_id)
            .where(Item.status == ItemStatus.draft, Source.week.is_not(None))
            .order_by(Source.week, Item.created_at)
        )
    ).all()
    items = [row[0] for row in rows]
    weeks = [row[1] for row in rows]

    chunk_ids = {item.chunk_ids[0] for item in items if item.chunk_ids}
    chunks = (
        await session.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    ).all()
    chunk_by_id = {c.id: c for c in chunks}

    vocabulary = load_topics()
    grouped: dict[int, list[ReviewItemOut]] = {}
    for item, week in zip(items, weeks, strict=True):
        chunk = chunk_by_id.get(item.chunk_ids[0]) if item.chunk_ids else None
        if chunk is None:
            continue  # an item with no resolvable anchor chunk has nothing to review against
        review_item = ReviewItemOut(
            **ItemOut.model_validate(item).model_dump(),
            chunk={"locator": chunk.locators[0] if chunk.locators else {}, "text": chunk.text},
            gen_model=item.gen_model,
        )
        grouped.setdefault(week, []).append(review_item)

    return [
        WeekReviewQueue(week=week, title=vocabulary.title_for_week(week), items=grouped[week])
        for week in sorted(grouped)
    ]


_SINGLE_POINT_TYPES = {ItemType.cloze, ItemType.mcq}


def _validate_rubric_edit(rubric: list[dict], chunk_text: str, item_type: ItemType) -> None:
    """Re-runs invariant 1's checks on a rubric coming through the edit endpoint. A rubric
    saved by the M3 generator already passed these at generation time; this endpoint is the
    other door into the same column, and CLAUDE.md invariant 1 doesn't carve out an
    exception for edits — a citation that isn't literally in the chunk is just as wrong
    typed by a human as invented by the model.

    Bound depends on `item_type`, same split as `generated_item.py`'s
    `_rubric_length_by_type`: `cloze`/`mcq` are graded by exact-match against
    `reference_answer`, not rubric coverage, so they carry exactly 1 anchor point rather
    than 2-5."""
    if item_type in _SINGLE_POINT_TYPES:
        if len(rubric) != 1:
            raise ValueError(f"{item_type} items need exactly 1 rubric point, got {len(rubric)}")
    elif not (MIN_RUBRIC_POINTS <= len(rubric) <= MAX_RUBRIC_POINTS):
        raise ValueError(
            f"rubric must have between {MIN_RUBRIC_POINTS} and {MAX_RUBRIC_POINTS} points, "
            f"got {len(rubric)}"
        )
    normalized_chunk = collapse_whitespace(chunk_text)
    for point in rubric:
        weight = point.get("weight")
        if not isinstance(weight, int | float) or isinstance(weight, bool) or weight <= 0:
            raise ValueError(f"rubric point {point.get('id')!r} must have weight > 0")
        quote = point.get("support_quote")
        if not isinstance(quote, str) or collapse_whitespace(quote) not in normalized_chunk:
            raise ValueError(f"support_quote not found verbatim in source chunk: {quote!r}")


@router.patch("/{item_id}", response_model=ItemOut)
async def patch_item(
    item_id: uuid.UUID,
    body: ItemPatchRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Item:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    # Item has no owner_id of its own — ownership is via its Source, same indirection
    # sources.py's _get_owned_source resolves directly; there's no such helper to share
    # here without an apps.api-internal import cycle, so it's inlined.
    source = await session.get(Source, item.source_id)
    if source is None or source.owner_id != user_id:
        raise HTTPException(status_code=404, detail="item not found")

    updates = body.model_dump(exclude_unset=True)

    if "rubric" in updates:
        chunk = await session.get(Chunk, item.chunk_ids[0]) if item.chunk_ids else None
        if chunk is None:
            raise HTTPException(
                status_code=422, detail="item has no anchor chunk to validate rubric against"
            )
        try:
            _validate_rubric_edit(updates["rubric"], chunk.text, item.type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if "status" in updates:
        item.status = ItemStatus(updates.pop("status"))
    if "bloom" in updates:
        item.bloom = ItemBloom(updates.pop("bloom"))
    for field, value in updates.items():
        setattr(item, field, value)

    await session.commit()
    return item
