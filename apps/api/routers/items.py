"""`PATCH /api/items/{id}` — docs/IMPLEMENTATION_PLAN.md M4. Covers approve/edit/retire;
the review UI itself is M6."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.schemas.items import ItemOut, ItemPatchRequest
from packages.db.models import Item, ItemBloom, ItemStatus

router = APIRouter(prefix="/api/items", tags=["items"])


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
    if "status" in updates:
        item.status = ItemStatus(updates.pop("status"))
    if "bloom" in updates:
        item.bloom = ItemBloom(updates.pop("bloom"))
    for field, value in updates.items():
        setattr(item, field, value)

    await session.commit()
    return item
