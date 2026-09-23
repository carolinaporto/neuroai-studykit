"""`GET/POST /api/notes`, `PATCH /api/notes/{id}` — design/synapse's `InsightNote`.

Locked section per `SiteNav` ("Notes & Insights... locked until signed in"): every route
here requires `require_owner`, even reading. `is_public` on a `Note` is a stored intent
("this one could be shown outside the locked section") rather than a second, unauthenticated
read path — nothing in the current design calls for one, so building it now would be
speculative (CLAUDE.md: no code for a future phase "já que estamos aqui").
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.schemas.notes import NoteCreateRequest, NoteOut, NotePatchRequest
from packages.db.models import Note, Source

router = APIRouter(
    prefix="/api/notes", tags=["notes"], dependencies=[Depends(require_owner)]
)


@router.get("", response_model=list[NoteOut])
async def list_notes(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[Note]:
    return list(
        (
            await session.scalars(
                select(Note)
                .where(Note.owner_id == user_id)
                .order_by(Note.created_at.desc())
            )
        ).all()
    )


@router.post("", response_model=NoteOut)
async def create_note(
    body: NoteCreateRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Note:
    if body.source_id is not None and await session.get(Source, body.source_id) is None:
        raise HTTPException(status_code=422, detail="source_id does not exist")

    note = Note(owner_id=user_id, **body.model_dump())
    session.add(note)
    await session.commit()
    return note


@router.patch("/{note_id}", response_model=NoteOut)
async def patch_note(
    note_id: uuid.UUID,
    body: NotePatchRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> Note:
    note = await session.get(Note, note_id)
    if note is None or note.owner_id != user_id:
        # 404, not 403: same as sources.py's _get_owned_source — don't confirm to the
        # caller that a note_id they don't own even exists.
        raise HTTPException(status_code=404, detail="note not found")

    updates = body.model_dump(exclude_unset=True)
    if "source_id" in updates and updates["source_id"] is not None:
        if await session.get(Source, updates["source_id"]) is None:
            raise HTTPException(status_code=422, detail="source_id does not exist")

    new_body = updates.get("body", note.body)
    new_url = updates.get("url", note.url)
    if not new_body and not new_url:
        raise HTTPException(status_code=422, detail="a note needs at least one of body or url")

    for field, value in updates.items():
        setattr(note, field, value)

    await session.commit()
    return note
