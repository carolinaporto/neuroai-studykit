"""`GET /api/sources` — Sources grouped by week, for Synapse's `WeekHeader` + `SourceItem`.

Read-only: uploading a source is still CLI-only (`python -m ingest.cli sync`) in Fase 1, per
ARCHITECTURE.md. Only `ingested` sources are listed — a `pending`/`failed` row isn't
something to show on the Sources page, it's ingestion housekeeping.

Locked section per `design/synapse`'s `SiteNav`: `require_owner` gates the whole router.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.db import get_session
from apps.api.core.deps import get_current_user_id, require_owner
from apps.api.schemas.sources import SourceOut, WeekSources
from packages.db.models import Source, SourceStatus
from packages.ingest.topics import load_topics

router = APIRouter(prefix="/api/sources", tags=["sources"], dependencies=[Depends(require_owner)])


@router.get("", response_model=list[WeekSources])
async def list_sources(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[WeekSources]:
    # `week` is nullable on Source (see packages/db/models.py), but every real source's week
    # is inferred from its `contentWeekNN/` folder at sync time — a NULL week only happens
    # for hand-built rows like the grading calibration fixture, which don't belong here.
    sources = (
        await session.scalars(
            select(Source)
            .where(
                Source.owner_id == user_id,
                Source.status == SourceStatus.ingested,
                Source.week.is_not(None),
            )
            .order_by(Source.week, Source.created_at)
        )
    ).all()

    grouped: dict[int, list[Source]] = {}
    for source in sources:
        grouped.setdefault(source.week, []).append(source)

    vocabulary = load_topics()
    return [
        WeekSources(
            week=week,
            title=vocabulary.title_for_week(week),
            sources=[SourceOut.model_validate(s) for s in grouped[week]],
        )
        for week in sorted(grouped)
    ]
