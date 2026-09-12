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

from packages.db.models import (
    Chunk as ChunkRow,
)
from packages.db.models import (
    IngestJob,
    IngestJobKind,
    IngestJobStatus,
    Source,
    SourceKind,
    SourceStatus,
    User,
)
from packages.db.session import DbSettings, make_session_factory

from .chunker import chunk_blocks
from .models import Chunk, Locator, ParsedBlock
from .parsers.pdf import parse_pdf
from .parsers.pptx import parse_pptx
from .parsers.transcript import parse_transcript

_PARSERS = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
    ".vtt": parse_transcript,
    ".srt": parse_transcript,
}

_SOURCE_KINDS = {
    ".pdf": SourceKind.lecture_pdf,
    ".pptx": SourceKind.slides,
    ".vtt": SourceKind.transcript,
    ".srt": SourceKind.transcript,
}

_WEEK_RE = re.compile(r"week0*(\d+)", re.IGNORECASE)


def parse_file(path: Path) -> list[ParsedBlock]:
    parser = _PARSERS.get(path.suffix.lower())
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


def _page_count(kind: SourceKind, blocks: list[ParsedBlock]) -> int | None:
    if kind is not SourceKind.lecture_pdf:
        return None
    pages = [b.locator.page for b in blocks if b.locator.page is not None]
    return max(pages) if pages else None


def _duration_seconds(kind: SourceKind, blocks: list[ParsedBlock]) -> float | None:
    if kind is not SourceKind.transcript:
        return None
    ends = [b.locator.t1 for b in blocks if b.locator.t1 is not None]
    return max(ends) if ends else None


def _find_syncable_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in _PARSERS)


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

            kind = _SOURCE_KINDS[path.suffix.lower()]
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
                source.page_count = _page_count(kind, blocks)
                source.duration_seconds = _duration_seconds(kind, blocks)
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

    return 1


if __name__ == "__main__":
    sys.exit(main())
