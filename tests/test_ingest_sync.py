"""Integration test for `ingest.cli sync`: runs against the real dev Postgres (same
assumption as tests/test_health.py — `docker compose up` must be running), and proves the
sha256-dedup idempotency required by M2's acceptance check. Cleans up its own rows so it
stays repeatable across runs.
"""

from pathlib import Path

import pytest
from ingest.cli import sync_folder
from sqlalchemy import select

from packages.db.models import Chunk, Source
from packages.db.session import DbSettings, make_session_factory

_VTT = """WEBVTT

00:00:00.000 --> 00:00:05.000
Synaptic plasticity is the ability of synapses to strengthen or weaken over time.

00:00:05.000 --> 00:00:10.000
Long-term potentiation is a persistent increase in synaptic strength.
"""


@pytest.mark.asyncio
async def test_sync_is_idempotent(tmp_path: Path) -> None:
    folder = tmp_path / "week99"
    folder.mkdir()
    (folder / "lecture.vtt").write_text(_VTT)

    settings = DbSettings()
    session_factory = make_session_factory(settings.database_url)

    try:
        first = await sync_folder(folder, session_factory, settings.dev_owner_id)
        assert first["new"] == 1
        assert first["duplicate"] == 0
        assert first["failed"] == 0
        assert first["chunks"] >= 1

        async with session_factory() as session:
            source = await session.scalar(
                select(Source).where(Source.title == "lecture", Source.week == 99)
            )
            assert source is not None
            chunks_after_first = (
                await session.scalars(select(Chunk).where(Chunk.source_id == source.id))
            ).all()
            assert len(chunks_after_first) == first["chunks"]

        second = await sync_folder(folder, session_factory, settings.dev_owner_id)
        assert second["new"] == 0
        assert second["duplicate"] == 1
        assert second["chunks"] == 0

        async with session_factory() as session:
            chunks_after_second = (
                await session.scalars(select(Chunk).where(Chunk.source_id == source.id))
            ).all()
            assert len(chunks_after_second) == first["chunks"]
    finally:
        async with session_factory() as session:
            existing = await session.scalar(
                select(Source).where(Source.title == "lecture", Source.week == 99)
            )
            if existing is not None:
                await session.delete(existing)  # cascades to Chunk/IngestJob
                await session.commit()
