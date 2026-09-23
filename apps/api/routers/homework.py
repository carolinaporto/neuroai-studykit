"""`GET /api/homework` (public), `POST /api/homework` and `PATCH /api/homework/{id}`
(owner-only) — the semester portfolio Synapse's `HomeworkCard` renders.

Unlike Sources/Quizzes/Notes, this section is never locked (design/synapse's `SiteNav`: "the
Homework item... takes a Public tag instead"), so `GET` carries no `require_owner` dependency
— it's the one router in this app a signed-out visitor can call.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.schemas.homework import HomeworkCreateRequest, HomeworkOut, HomeworkPatchRequest
from packages.db.models import Homework, HomeworkStatus

router = APIRouter(prefix="/api/homework", tags=["homework"])


@router.get("", response_model=list[HomeworkOut])
async def list_homework(session: AsyncSession = Depends(get_session)) -> list[Homework]:
    """Only `published` entries are ever exposed here. `draft` is how a not-yet-finished
    portfolio entry stays invisible without needing a private state — this card type has no
    private variant (see `Homework.status`'s docstring in packages/db/models.py)."""
    return list(
        (
            await session.scalars(
                select(Homework)
                .where(Homework.status == HomeworkStatus.published)
                .order_by(Homework.week, Homework.created_at)
            )
        ).all()
    )


@router.post("", response_model=HomeworkOut, dependencies=[Depends(require_owner)])
async def create_homework(
    body: HomeworkCreateRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Homework:
    """Creates in `draft` — publishing is a separate, explicit `PATCH ... {"status":
    "published"}` so a half-written entry never appears on the public list by accident."""
    homework = Homework(owner_id=user_id, **body.model_dump())
    session.add(homework)
    await session.commit()
    return homework


@router.patch("/{homework_id}", response_model=HomeworkOut, dependencies=[Depends(require_owner)])
async def patch_homework(
    homework_id: uuid.UUID,
    body: HomeworkPatchRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Homework:
    homework = await session.get(Homework, homework_id)
    if homework is None or homework.owner_id != user_id:
        raise HTTPException(status_code=404, detail="homework not found")

    updates = body.model_dump(exclude_unset=True)
    if "status" in updates:
        homework.status = HomeworkStatus(updates.pop("status"))
    for field, value in updates.items():
        setattr(homework, field, value)

    await session.commit()
    return homework
