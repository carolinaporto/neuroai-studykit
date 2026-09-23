"""Item dedup by prompt embedding — M7 part 2, ARCHITECTURE.md step 7: "descarta se
cosseno > 0.92 contra item existente da mesma semana."

Lives in `packages/ingest`, not `apps/api`: `packages/ingest/cli.py` already does direct DB
work the same way (invariant 4 is about never importing `apps.api`, not about avoiding a
database), so a second piece of DB-touching ingestion logic belongs next to the first, not
split across layers.

Compares against *every* existing item in the week regardless of status (including
`draft`/`retired`) — a retired item was still a real question; regenerating its
near-duplicate is still wasted generation.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.models import Item, Source

DEDUP_COSINE_THRESHOLD = 0.92


async def find_duplicate_item(
    session: AsyncSession, *, week: int, embedding: list[float]
) -> uuid.UUID | None:
    """The id of an existing item in `week` whose prompt embedding is more than
    `DEDUP_COSINE_THRESHOLD` cosine-similar to `embedding`, or `None`. pgvector's
    `cosine_distance` is `1 - cosine_similarity`, so the comparison is inverted below."""
    row = (
        await session.execute(
            select(Item.id, Item.embedding.cosine_distance(embedding).label("distance"))
            .join(Source, Source.id == Item.source_id)
            .where(Source.week == week, Item.embedding.is_not(None))
            .order_by("distance")
            .limit(1)
        )
    ).first()

    if row is None:
        return None
    item_id, distance = row
    similarity = 1 - distance
    return item_id if similarity > DEDUP_COSINE_THRESHOLD else None
