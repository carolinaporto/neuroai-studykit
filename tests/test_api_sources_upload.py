"""Tests for `POST /api/sources/upload` and `POST /api/sources/generate` — the web-upload
equivalents of `ingest sync`/`ingest generate`. Runs against the real dev Postgres, same
assumption as the other `test_api_*` files.
"""

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.core.db import get_session, get_session_factory
from apps.api.core.deps import (
    get_current_user_id,
    get_embedding_client,
    get_llm_client,
    require_owner,
)
from apps.api.main import app
from packages.core.embeddings import EmbeddingClient, FakeEmbeddingClient
from packages.core.llm import FakeLLM, LLMClient
from packages.db.models import (
    Chunk,
    IngestJob,
    IngestJobStatus,
    Item,
    Source,
    SourceKind,
    SourceStatus,
    User,
)
from packages.db.session import DbSettings, make_session_factory
from tests.pdf_builders import build_pdf, scanned_page, text_page

FIXTURES = Path(__file__).parent / "fixtures"


@asynccontextmanager
async def _test_client(
    session_factory: async_sessionmaker,
    llm: LLMClient | None = None,
    embeddings: EmbeddingClient | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    # generate_for_week (packages/ingest/cli.py) takes a whole session_factory, not one
    # AsyncSession — see get_session_factory's docstring in apps/api/core/db.py for why this
    # override matters: without it, /api/sources/generate binds to the module-level
    # session_factory's original event loop instead of this test's.
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[require_owner] = lambda: None
    app.dependency_overrides[get_current_user_id] = lambda: DbSettings().dev_owner_id
    # Always overridden: upload can call the LLM now (scanned PDF pages), and no test may
    # reach the real API (invariant 5) — a test that forgets to pass one gets an empty fake
    # that raises if it is ever called.
    fake_llm = llm if llm is not None else FakeLLM([])
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    # Same reasoning, extended to M7 part 2's embedding provider: generate now embeds every
    # accepted item for dedup, so this must always be overridden too.
    fake_embeddings = embeddings if embeddings is not None else FakeEmbeddingClient([])
    app.dependency_overrides[get_embedding_client] = lambda: fake_embeddings
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_session_factory, None)
        app.dependency_overrides.pop(require_owner, None)
        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(get_llm_client, None)
        app.dependency_overrides.pop(get_embedding_client, None)


async def _ensure_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    if await session.get(User, owner_id) is None:
        session.add(User(id=owner_id, email="owner@studykit.local"))
        await session.flush()


async def _cleanup_week(session_factory: async_sessionmaker, week: int) -> None:
    async with session_factory() as session:
        sources = (await session.scalars(select(Source).where(Source.week == week))).all()
        for source in sources:
            await session.delete(source)  # cascades to Chunk/Item/Attempt
        await session.commit()


async def _cleanup_by_sha256(session_factory: async_sessionmaker, data: bytes) -> None:
    """Fixture isolation, not week-based cleanup: `tests/fixtures/synthetic.pdf`'s exact
    bytes may already be a Source from unrelated earlier dev-DB activity (M2/M3 fixture
    syncs, calibration runs), which would make a fresh upload of the same file dedupe
    against that leftover row instead of actually ingesting. Clears it first so the test
    doesn't depend on what else has touched this dev database."""
    sha256 = hashlib.sha256(data).hexdigest()
    async with session_factory() as session:
        existing = await session.scalar(select(Source).where(Source.sha256 == sha256))
        if existing is not None:
            await session.delete(existing)
            await session.commit()


@pytest.mark.asyncio
async def test_upload_ingests_a_supported_file_and_dedupes_on_replay() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    week = 8001

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    pdf_bytes = (FIXTURES / "synthetic.pdf").read_bytes()
    await _cleanup_by_sha256(session_factory, pdf_bytes)

    try:
        async with _test_client(session_factory) as client:
            first = await client.post(
                "/api/sources/upload",
                data={"week": str(week)},
                files=[("files", ("lecture.pdf", pdf_bytes, "application/pdf"))],
            )
            assert first.status_code == 200
            first_results = first.json()["results"]
            assert len(first_results) == 1
            assert first_results[0]["status"] == "ingested"
            assert first_results[0]["chunk_count"] > 0

            async with session_factory() as session:
                sources = (
                    await session.scalars(select(Source).where(Source.week == week))
                ).all()
                assert len(sources) == 1
                chunks = (
                    await session.scalars(
                        select(Chunk).where(Chunk.source_id == sources[0].id)
                    )
                ).all()
                assert len(chunks) == first_results[0]["chunk_count"]
                assert sources[0].file_data == pdf_bytes
                assert sources[0].file_media_type == "application/pdf"

            # Same bytes again — must dedupe by sha256, not create a second Source.
            second = await client.post(
                "/api/sources/upload",
                data={"week": str(week)},
                files=[("files", ("lecture-copy.pdf", pdf_bytes, "application/pdf"))],
            )
            assert second.json()["results"][0]["status"] == "duplicate"

            async with session_factory() as session:
                sources = (
                    await session.scalars(select(Source).where(Source.week == week))
                ).all()
                assert len(sources) == 1
    finally:
        await _cleanup_week(session_factory, week)


@pytest.mark.asyncio
async def test_upload_flags_unsupported_extension_without_failing_the_batch() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    week = 8002

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    pdf_bytes = (FIXTURES / "synthetic.pdf").read_bytes()
    await _cleanup_by_sha256(session_factory, pdf_bytes)

    try:
        async with _test_client(session_factory) as client:
            resp = await client.post(
                "/api/sources/upload",
                data={"week": str(week)},
                files=[
                    ("files", ("notes.docx", b"not a real docx", "application/octet-stream")),
                    ("files", ("lecture.pdf", pdf_bytes, "application/pdf")),
                ],
            )
            assert resp.status_code == 200
            results = {r["filename"]: r["status"] for r in resp.json()["results"]}
            assert results["notes.docx"] == "unsupported"
            assert results["lecture.pdf"] == "ingested"
    finally:
        await _cleanup_week(session_factory, week)


@pytest.mark.asyncio
async def test_upload_transcribes_scanned_pages_into_the_chunk_text() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    week = 8003

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    pdf_bytes = build_pdf(text_page, scanned_page)
    await _cleanup_by_sha256(session_factory, pdf_bytes)
    transcription = "Week 3 notes: intelligence is not one scale of nature"
    llm = FakeLLM([], vision_responses=[transcription])

    try:
        async with _test_client(session_factory, llm) as client:
            resp = await client.post(
                "/api/sources/upload",
                data={"week": str(week)},
                files=[("files", ("notes.pdf", pdf_bytes, "application/pdf"))],
            )
            assert resp.status_code == 200
            assert resp.json()["results"][0]["status"] == "ingested"

        assert len(llm.vision_calls) == 1
        async with session_factory() as session:
            source = await session.scalar(select(Source).where(Source.week == week))
            chunk_text = " ".join(
                (
                    await session.scalars(
                        select(Chunk.text)
                        .where(Chunk.source_id == source.id)
                        .order_by(Chunk.ordinal)
                    )
                ).all()
            )
            assert transcription in chunk_text
            job = await session.scalar(
                select(IngestJob).where(IngestJob.source_id == source.id)
            )
            assert job.payload["transcribed_pages"] == [2]
    finally:
        await _cleanup_week(session_factory, week)


@pytest.mark.asyncio
async def test_upload_of_a_scan_fails_cleanly_when_the_transcription_call_fails() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    week = 8004

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        await session.commit()

    pdf_bytes = build_pdf(scanned_page)
    await _cleanup_by_sha256(session_factory, pdf_bytes)
    llm = FakeLLM([], vision_responses=[RuntimeError("api down"), RuntimeError("api down")])

    try:
        async with _test_client(session_factory, llm) as client:
            resp = await client.post(
                "/api/sources/upload",
                data={"week": str(week)},
                files=[("files", ("scan.pdf", pdf_bytes, "application/pdf"))],
            )
            assert resp.status_code == 200
            result = resp.json()["results"][0]
            assert result["status"] == "failed"
            assert "api down" in result["error"]

        async with session_factory() as session:
            source = await session.scalar(select(Source).where(Source.week == week))
            assert source.status == SourceStatus.failed
            job = await session.scalar(
                select(IngestJob).where(IngestJob.source_id == source.id)
            )
            assert job.status == IngestJobStatus.failed
            assert "page 1" in job.error
    finally:
        await _cleanup_week(session_factory, week)


def _generated_batch_json() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "type": "term_def",
                    "prompt": "Define the term introduced in this passage.",
                    "reference_answer": "A short reference answer grounded in the chunk.",
                    "rubric": [
                        {
                            "point": "States the definition correctly.",
                            "weight": 1.0,
                            "support_quote": "Hebbian plasticity is often summarized as "
                            "cells that fire together wire together.",
                        },
                        {
                            "point": "Mentions the mechanism.",
                            "weight": 1.0,
                            "support_quote": "Long-term potentiation is a persistent "
                            "increase in synaptic strength.",
                        },
                    ],
                    "difficulty": 2,
                    "bloom": "recall",
                    "topics": ["hebbian-plasticity"],
                    "proposed_topics": [],
                }
            ]
        }
    )


@pytest.mark.asyncio
async def test_generate_uses_fake_llm_and_saves_items() -> None:
    session_factory = make_session_factory(DbSettings().database_url)
    owner_id = DbSettings().dev_owner_id
    week = 3  # a real syllabus week — topics.yaml needs a matching unit for generation

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)
        source = Source(
            owner_id=owner_id,
            week=week,
            title="generate-test-source",
            kind=SourceKind.lecture_pdf,
            storage_uri="test://generate",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()
        chunk = Chunk(
            source_id=source.id,
            ordinal=0,
            text=(
                "Hebbian plasticity is often summarized as cells that fire together wire "
                "together. Long-term potentiation is a persistent increase in synaptic "
                "strength."
            ),
            locators=[{"page": 1}],
            token_count=40,
        )
        session.add(chunk)
        await session.commit()
        source_id = source.id

    fake_llm = FakeLLM([_generated_batch_json()])
    # One item in that batch -> one embed() call for one vector. Nothing else in this
    # isolated source has an embedding, so it can't dedup against anything.
    fake_embeddings = FakeEmbeddingClient([[[1.0] + [0.0] * 1535]])

    try:
        async with _test_client(session_factory, fake_llm, fake_embeddings) as client:
            resp = await client.post("/api/sources/generate", json={"week": week})
            assert resp.status_code == 200
            body = resp.json()
            assert body["chunks_processed"] == 1
            assert body["items_saved"] == 1
            assert body["items_deduped"] == 0
            assert body["chunks_failed"] == 0

        async with session_factory() as session:
            items = (
                await session.scalars(select(Item).where(Item.source_id == source_id))
            ).all()
            assert len(items) == 1
    finally:
        async with session_factory() as session:
            source = await session.get(Source, source_id)
            if source is not None:
                await session.delete(source)
            await session.commit()
