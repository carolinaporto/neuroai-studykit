"""`PATCH /api/items/{id}` — docs/IMPLEMENTATION_PLAN.md M4. Covers approve/edit/retire;
the review UI itself is M6. Owner-only: this is a review action, never public."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import require_owner
from apps.api.schemas.items import ItemOut, ItemPatchRequest
from packages.db.models import Chunk, Item, ItemBloom, ItemStatus
from packages.ingest.validators import collapse_whitespace

router = APIRouter(prefix="/api/items", tags=["items"], dependencies=[Depends(require_owner)])

MIN_RUBRIC_POINTS = 2
MAX_RUBRIC_POINTS = 5


def _validate_rubric_edit(rubric: list[dict], chunk_text: str) -> None:
    """Re-runs invariant 1's checks on a rubric coming through the edit endpoint. A rubric
    saved by the M3 generator already passed these at generation time; this endpoint is the
    other door into the same column, and CLAUDE.md invariant 1 doesn't carve out an
    exception for edits — a citation that isn't literally in the chunk is just as wrong
    typed by a human as invented by the model."""
    if not (MIN_RUBRIC_POINTS <= len(rubric) <= MAX_RUBRIC_POINTS):
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
) -> Item:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")

    updates = body.model_dump(exclude_unset=True)

    if "rubric" in updates:
        chunk = await session.get(Chunk, item.chunk_ids[0]) if item.chunk_ids else None
        if chunk is None:
            raise HTTPException(
                status_code=422, detail="item has no anchor chunk to validate rubric against"
            )
        try:
            _validate_rubric_edit(updates["rubric"], chunk.text)
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
