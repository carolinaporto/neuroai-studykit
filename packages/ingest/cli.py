"""CLI for the ingestion pipeline.

`parse` is pure: no db, no app config (invariant 4). `sync` does write to Postgres, but only
through `packages/db` — never through `apps/api` — so invariant 4 (packages/ingest never
imports apps/api) still holds; see docs/IMPLEMENTATION_PLAN.md M2 and CLAUDE.md invariant 4.
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.core.llm import AnthropicLLMClient, LLMClient, LLMSettings
from packages.db.models import (
    Chunk as ChunkRow,
)
from packages.db.models import (
    IngestJob,
    IngestJobKind,
    IngestJobStatus,
    Item,
    ItemBloom,
    ItemType,
    Source,
    SourceKind,
    SourceStatus,
    User,
)
from packages.db.session import DbSettings, make_session_factory

from .chunker import chunk_blocks
from .generator import GenerationFailedError, generate_items_for_chunk, prompt_version_hash
from .models import Chunk, Locator, ParsedBlock
from .parsers.pdf import parse_pdf
from .parsers.pptx import parse_pptx
from .parsers.transcript import parse_transcript
from .topics import load_topics

PARSERS = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
    ".vtt": parse_transcript,
    ".srt": parse_transcript,
}

SOURCE_KIND_BY_EXTENSION = {
    ".pdf": SourceKind.lecture_pdf,
    ".pptx": SourceKind.slides,
    ".vtt": SourceKind.transcript,
    ".srt": SourceKind.transcript,
}

_WEEK_RE = re.compile(r"week0*(\d+)", re.IGNORECASE)


def parse_file(path: Path) -> list[ParsedBlock]:
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ValueError(f"no parser registered for extension {path.suffix!r}")
    return parser(path.read_bytes())


def _format_locator(locator: Locator) -> str:
    return ", ".join(f"{key}={value}" for key, value in locator.as_dict().items())


def _print_chunks(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        locators = " | ".join(_format_locator(loc) for loc in chunk.locators)
        print(f"--- chunk {chunk.ordinal} ({chunk.token_count} tokens) [{locators}] ---")
        print(chunk.text)
        print()


def _infer_week(folder: Path) -> int | None:
    match = _WEEK_RE.search(str(folder))
    return int(match.group(1)) if match else None


def page_count_for(kind: SourceKind, blocks: list[ParsedBlock]) -> int | None:
    if kind is not SourceKind.lecture_pdf:
        return None
    pages = [b.locator.page for b in blocks if b.locator.page is not None]
    return max(pages) if pages else None


def duration_seconds_for(kind: SourceKind, blocks: list[ParsedBlock]) -> float | None:
    if kind is not SourceKind.transcript:
        return None
    ends = [b.locator.t1 for b in blocks if b.locator.t1 is not None]
    return max(ends) if ends else None


def _find_syncable_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in PARSERS)


async def _ensure_owner(session: AsyncSession, owner_id: uuid.UUID) -> None:
    if await session.get(User, owner_id) is None:
        session.add(User(id=owner_id, email="owner@studykit.local"))
        await session.flush()


async def sync_folder(
    folder: Path,
    session_factory: async_sessionmaker[AsyncSession],
    owner_id: uuid.UUID,
) -> dict[str, int]:
    """Sync every supported file under `folder` into Source/Chunk/IngestJob rows.

    Dedup is by sha256 of the file bytes: a file already backing a Source is skipped
    entirely (no reparse, no new rows), which is what makes running this twice idempotent.
    """
    counts = {"new": 0, "duplicate": 0, "failed": 0, "chunks": 0}
    week = _infer_week(folder)

    async with session_factory() as session:
        await _ensure_owner(session, owner_id)

        for path in _find_syncable_files(folder):
            data = path.read_bytes()
            sha256 = hashlib.sha256(data).hexdigest()

            existing = await session.scalar(select(Source).where(Source.sha256 == sha256))
            if existing is not None:
                counts["duplicate"] += 1
                continue

            kind = SOURCE_KIND_BY_EXTENSION[path.suffix.lower()]
            source = Source(
                owner_id=owner_id,
                week=week,
                title=path.stem,
                kind=kind,
                storage_uri=str(path.resolve()),
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
            # Commit durably now: source+job must survive below even if parsing fails,
            # so the failure path below has real committed rows to roll back to and update.
            await session.commit()

            try:
                blocks = parse_file(path)
                chunks = chunk_blocks(blocks)
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
                job.payload = {"path": str(path), "chunk_count": len(chunks)}
                await session.commit()
                counts["new"] += 1
                counts["chunks"] += len(chunks)
            except Exception as exc:
                await session.rollback()
                source.status = SourceStatus.failed
                job.status = IngestJobStatus.failed
                job.error = str(exc)
                await session.commit()
                counts["failed"] += 1

    return counts


async def generate_for_week(
    week: int,
    session_factory: async_sessionmaker[AsyncSession],
    llm: LLMClient,
    *,
    force: bool = False,
) -> dict[str, object]:
    """Generates draft items for every chunk of every Source with `week=week`.

    By default, skips chunks already covered by an existing Item, so reruns don't re-spend
    tokens on chunks already generated. `force=True` (CLI `--force`) turns that off and
    regenerates every chunk regardless — for when you've edited the prompt and want to see
    what the new version produces. It does not delete or retire the old items: each new one
    is tagged with the current `gen_prompt_version` (see `generator.prompt_version_hash`),
    so old and new items sit side by side and you can compare them by that field until you
    triage them in the M6 review UI.
    """
    vocabulary = load_topics()
    prompt_version = prompt_version_hash()
    counts = {"chunks_processed": 0, "items_saved": 0, "items_rejected": 0, "chunks_failed": 0}
    proposed_topics: list[str] = []

    async with session_factory() as session:
        sources = (await session.scalars(select(Source).where(Source.week == week))).all()
        if not sources:
            return {**counts, "proposed_topics": proposed_topics}
        source_ids = [s.id for s in sources]

        covered_chunk_ids: set[uuid.UUID] = set()
        if not force:
            existing_items = (
                await session.scalars(select(Item).where(Item.source_id.in_(source_ids)))
            ).all()
            covered_chunk_ids = {cid for item in existing_items for cid in item.chunk_ids}

        chunks = (
            await session.scalars(
                select(ChunkRow)
                .where(ChunkRow.source_id.in_(source_ids))
                .order_by(ChunkRow.ordinal)
            )
        ).all()

        for chunk in chunks:
            if chunk.id in covered_chunk_ids:
                continue
            counts["chunks_processed"] += 1

            job = IngestJob(
                source_id=chunk.source_id,
                kind=IngestJobKind.generate,
                status=IngestJobStatus.running,
                attempts=1,
                payload={"chunk_id": str(chunk.id)},
            )
            session.add(job)
            await session.commit()

            try:
                result = await generate_items_for_chunk(
                    chunk_text=chunk.text, week=week, vocabulary=vocabulary, llm=llm
                )
            except GenerationFailedError as exc:
                job.status = IngestJobStatus.failed
                job.error = str(exc)
                await session.commit()
                counts["chunks_failed"] += 1
                continue

            for validated in result.items:
                session.add(
                    Item(
                        source_id=chunk.source_id,
                        chunk_ids=[chunk.id],
                        type=ItemType(validated.type),
                        prompt=validated.prompt,
                        reference_answer=validated.reference_answer,
                        rubric=[p.model_dump() for p in validated.rubric],
                        difficulty=validated.difficulty,
                        bloom=ItemBloom(validated.bloom),
                        topics=validated.topics,
                        gen_model=llm.model_name,
                        gen_prompt_version=prompt_version,
                    )
                )
            for topic in result.proposed_topics:
                if topic not in proposed_topics:
                    proposed_topics.append(topic)

            job.status = IngestJobStatus.done
            job.payload = {
                "chunk_id": str(chunk.id),
                "items_saved": len(result.items),
                "items_rejected": len(result.rejected),
                "rejected_reasons": [r.reason for r in result.rejected],
                "attempts": result.attempts,
            }
            await session.commit()
            counts["items_saved"] += len(result.items)
            counts["items_rejected"] += len(result.rejected)

    return {**counts, "proposed_topics": proposed_topics}


def _run_generate(week: int, force: bool) -> int:
    db_settings = DbSettings()
    llm_settings = LLMSettings()
    session_factory = make_session_factory(db_settings.database_url)
    llm = AnthropicLLMClient(
        api_key=llm_settings.anthropic_api_key, model=llm_settings.llm_model_generate
    )

    result = asyncio.run(generate_for_week(week, session_factory, llm, force=force))
    print(
        f"{result['chunks_processed']} chunks processados, {result['items_saved']} itens salvos, "
        f"{result['items_rejected']} itens rejeitados, {result['chunks_failed']} chunks falharam"
    )
    proposed = result["proposed_topics"]
    if proposed:
        print("tópicos propostos (não salvos — para revisão em M6):")
        for topic in proposed:
            print(f"  - {topic}")
    return 1 if result["chunks_failed"] else 0


def _run_sync(folder: Path) -> int:
    settings = DbSettings()
    session_factory = make_session_factory(settings.database_url)
    counts = asyncio.run(sync_folder(folder, session_factory, settings.dev_owner_id))
    print(
        f"{counts['new']} fontes novas, {counts['duplicate']} já existentes, "
        f"{counts['failed']} falharam, {counts['chunks']} chunks criados"
    )
    return 1 if counts["failed"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="parse a file into chunks and print them")
    parse_cmd.add_argument("path", type=Path)
    parse_cmd.add_argument("--json", action="store_true", help="print chunks as JSON instead")

    sync_cmd = subparsers.add_parser("sync", help="parse+chunk a folder and persist to Postgres")
    sync_cmd.add_argument("folder", type=Path)

    generate_cmd = subparsers.add_parser(
        "generate", help="generate draft items for a week's chunks via the LLM"
    )
    generate_cmd.add_argument("--week", type=int, required=True)
    generate_cmd.add_argument(
        "--force",
        action="store_true",
        help="regenerate every chunk even if it already has items (old items are kept, "
        "not deleted — compare by gen_prompt_version)",
    )

    args = parser.parse_args(argv)

    if args.command == "parse":
        blocks = parse_file(args.path)
        chunks = chunk_blocks(blocks)
        if args.json:
            print(json.dumps([c.model_dump() for c in chunks], indent=2))
        else:
            _print_chunks(chunks)
        return 0

    if args.command == "sync":
        return _run_sync(args.folder)

    if args.command == "generate":
        return _run_generate(args.week, args.force)

    return 1


if __name__ == "__main__":
    sys.exit(main())
