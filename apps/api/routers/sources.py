"""Sources: `GET /api/sources` (list, grouped by week), `POST /api/sources/upload` (drag a
folder of files in — parse+chunk, no LLM call), `POST /api/sources/generate` (the paid step:
call the LLM to turn a week's chunks into draft quiz items).

Locked section per `design/synapse`'s `SiteNav`: `require_owner` gates the whole router.
"""

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.core.config import settings
from apps.api.core.db import get_session, get_session_factory
from apps.api.core.deps import get_current_user_id, get_llm_client, require_owner
from apps.api.schemas.sources import (
    ChunkOut,
    GenerateRequest,
    GenerateResponse,
    SourceDetail,
    SourceOut,
    UploadResult,
    UploadSourcesResponse,
    WeekSources,
)
from packages.core.llm import LLMClient
from packages.db.models import Chunk as ChunkRow
from packages.db.models import IngestJob, IngestJobKind, IngestJobStatus, Source, SourceStatus, User
from packages.ingest.chunker import chunk_blocks
from packages.ingest.cli import (
    PARSERS,
    SOURCE_KIND_BY_EXTENSION,
    duration_seconds_for,
    generate_for_week,
    page_count_for,
)
from packages.ingest.topics import load_topics

router = APIRouter(prefix="/api/sources", tags=["sources"], dependencies=[Depends(require_owner)])

# Same as ARCHITECTURE.md §7's upload rules: only these extensions, a size cap, and the
# stored file is named by UUID — never the original filename.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

MEDIA_TYPE_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".vtt": "text/vtt",
    ".srt": "text/plain",
}


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


async def _get_owned_source(
    session: AsyncSession, source_id: uuid.UUID, user_id: uuid.UUID
) -> Source:
    source = await session.get(Source, source_id)
    if source is None or source.owner_id != user_id:
        raise HTTPException(status_code=404, detail="source not found")
    return source


@router.get("/{source_id}", response_model=SourceDetail)
async def get_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> SourceDetail:
    """The click-to-preview panel's data: the source's own fields plus every chunk, in
    order — what the app actually extracted from it, gabarito concerns don't apply here
    (this is raw source material, not a quiz item's rubric)."""
    source = await _get_owned_source(session, source_id, user_id)
    chunks = (
        await session.scalars(
            select(ChunkRow).where(ChunkRow.source_id == source_id).order_by(ChunkRow.ordinal)
        )
    ).all()
    return SourceDetail(
        **SourceOut.model_validate(source).model_dump(),
        chunks=[ChunkOut.model_validate(c) for c in chunks],
    )


@router.get("/{source_id}/file")
async def get_source_file(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> FileResponse:
    """The actual uploaded bytes, for the one type a browser can render natively (`.pdf`) —
    an `<iframe>` pointed at this URL is the preview panel's real document view. `.pptx` and
    transcripts fall back to `SourceDetail`'s chunk text; this endpoint still serves them
    (as a download), just not embeddable."""
    source = await _get_owned_source(session, source_id, user_id)
    path = Path(source.storage_uri)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="stored file is missing on disk")
    media_type = MEDIA_TYPE_BY_EXTENSION.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


async def _ensure_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    if await session.get(User, owner_id) is None:
        session.add(User(id=owner_id, email="owner@studykit.local"))
        await session.flush()


@router.post("/upload", response_model=UploadSourcesResponse)
async def upload_sources(
    week: int = Form(...),
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> UploadSourcesResponse:
    """Drag-a-folder-in equivalent of `python -m ingest.cli sync` — parse + chunk only, no
    LLM call, so this endpoint costs nothing to hit. `week` comes from the form (there is no
    `weekNN/` folder name to infer it from, unlike the CLI), same file types the CLI
    supports (`packages/ingest/cli.py`'s `PARSERS`) — anything else comes back
    `unsupported`, not silently dropped."""
    await _ensure_owner(session, user_id)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    results: list[UploadResult] = []
    for upload in files:
        filename = upload.filename or "unnamed"
        ext = Path(filename).suffix.lower()

        if ext not in PARSERS:
            results.append(UploadResult(filename=filename, status="unsupported"))
            continue

        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            results.append(UploadResult(filename=filename, status="too_large"))
            continue

        sha256 = hashlib.sha256(data).hexdigest()
        existing = await session.scalar(select(Source).where(Source.sha256 == sha256))
        if existing is not None:
            results.append(UploadResult(filename=filename, status="duplicate"))
            continue

        kind = SOURCE_KIND_BY_EXTENSION[ext]
        stored_path = upload_dir / f"{uuid.uuid4()}{ext}"

        source = Source(
            owner_id=user_id,
            week=week,
            title=Path(filename).stem,
            kind=kind,
            storage_uri=str(stored_path.resolve()),
            sha256=sha256,
            status=SourceStatus.pending,
        )
        session.add(source)
        await session.flush()

        job = IngestJob(
            source_id=source.id,
            kind=IngestJobKind.parse_and_chunk,
            status=IngestJobStatus.running,
            attempts=1,
        )
        session.add(job)
        await session.commit()

        try:
            blocks = PARSERS[ext](data)
            chunks = chunk_blocks(blocks)
            stored_path.write_bytes(data)
            for chunk in chunks:
                session.add(
                    ChunkRow(
                        source_id=source.id,
                        ordinal=chunk.ordinal,
                        text=chunk.text,
                        locators=[loc.as_dict() for loc in chunk.locators],
                        token_count=chunk.token_count,
                    )
                )
            source.page_count = page_count_for(kind, blocks)
            source.duration_seconds = duration_seconds_for(kind, blocks)
            source.status = SourceStatus.ingested
            source.ingested_at = datetime.now(UTC)
            job.status = IngestJobStatus.done
            job.payload = {"filename": filename, "chunk_count": len(chunks)}
            await session.commit()
            results.append(
                UploadResult(filename=filename, status="ingested", chunk_count=len(chunks))
            )
        except Exception as exc:
            await session.rollback()
            source.status = SourceStatus.failed
            job.status = IngestJobStatus.failed
            job.error = str(exc)
            await session.commit()
            results.append(UploadResult(filename=filename, status="failed", error=str(exc)))

    return UploadSourcesResponse(results=results)


@router.post("/generate", response_model=GenerateResponse)
async def generate_questions(
    body: GenerateRequest,
    llm: LLMClient = Depends(get_llm_client),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> GenerateResponse:
    """The paid step: one real LLM call per not-yet-covered chunk in the week. Reuses
    `packages/ingest/cli.py`'s `generate_for_week` verbatim — same function the CLI's
    `ingest generate` runs — via a whole session factory rather than the request's own
    `AsyncSession`, since that function manages several of its own transactions across a
    week's chunks. A chunk whose generation call fails is counted in `chunks_failed`, not
    raised — the same behavior the CLI has always had, so one bad chunk doesn't lose the
    rest of the week's results."""
    result = await generate_for_week(body.week, session_factory, llm, force=body.force)
    return GenerateResponse(**result)
