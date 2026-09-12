"""Manual calibration runner for the grader. NOT part of pytest/CI — see CLAUDE.md.

Run via `make calibrate` (or `uv run python -m tests.calibration.run_calibration`) after
touching the grading prompt (`apps/api/prompts/grade_v1.md`) or `compute_score`, or when a
new item type starts going through the grader. Requires `make api` running against a real
Postgres with a real ANTHROPIC_API_KEY — this deliberately calls the live API and a real
LLM so a human can look at the result; CLAUDE.md invariant 5 ("nenhum teste chama a API do
Anthropic") is about pytest, and this script is never collected by pytest.

Creates its own Source/Chunk/Item rows for the frozen item in `cases.py`, submits each of
the four CASES to POST /api/study/answer, compares the returned score and per-point
coverage against what's frozen there, and deletes everything it created — including the
Attempt rows the API wrote — before exiting, so the dev DB is unchanged either way.
"""

import asyncio
import math
import os
import sys
import uuid

import httpx

from packages.db.models import (
    Chunk,
    Item,
    ItemBloom,
    ItemType,
    Source,
    SourceKind,
    SourceStatus,
    User,
)
from packages.db.session import DbSettings, make_session_factory

from .cases import CASES, CHUNK_LOCATORS, CHUNK_TEXT, ITEM_PROMPT, REFERENCE_ANSWER, RUBRIC

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


async def _create_golden_item(session_factory) -> tuple[uuid.UUID, uuid.UUID]:
    settings = DbSettings()
    async with session_factory() as session:
        if await session.get(User, settings.dev_owner_id) is None:
            session.add(User(id=settings.dev_owner_id, email="owner@studykit.local"))
            await session.flush()

        source = Source(
            owner_id=settings.dev_owner_id,
            week=None,
            title="calibration-fixture",
            kind=SourceKind.slides,
            storage_uri="calibration://grader",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,  # unique per run, never reused
            status=SourceStatus.ingested,
        )
        session.add(source)
        await session.flush()

        chunk = Chunk(
            source_id=source.id,
            ordinal=0,
            text=CHUNK_TEXT,
            locators=CHUNK_LOCATORS,
            token_count=len(CHUNK_TEXT.split()),
        )
        session.add(chunk)
        await session.flush()

        item = Item(
            source_id=source.id,
            chunk_ids=[chunk.id],
            type=ItemType.free_recall,
            prompt=ITEM_PROMPT,
            reference_answer=REFERENCE_ANSWER,
            rubric=RUBRIC,
            difficulty=3,
            bloom=ItemBloom.understand,
            topics=["gradient-descent", "loss-functions"],
            gen_model="calibration",
            gen_prompt_version="calibration",
        )
        session.add(item)
        await session.commit()
        return item.id, source.id


async def _cleanup(session_factory, source_id: uuid.UUID) -> None:
    async with session_factory() as session:
        source = await session.get(Source, source_id)
        if source is not None:
            await session.delete(source)  # cascades to Chunk/Item/Attempt
            await session.commit()


def _covered_map(rubric_hits: list[dict]) -> dict[str, bool]:
    return {h["point_id"]: h["covered"] for h in rubric_hits}


async def main() -> int:
    session_factory = make_session_factory(DbSettings().database_url)
    item_id, source_id = await _create_golden_item(session_factory)

    all_passed = True
    try:
        async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=60) as client:
            for case in CASES:
                try:
                    resp = await client.post(
                        "/api/study/answer",
                        json={"item_id": str(item_id), "response_text": case.response_text},
                    )
                except httpx.ConnectError:
                    print(
                        f"não foi possível conectar em {API_BASE_URL} — suba a API primeiro "
                        f"(`make api`)."
                    )
                    return 2

                if resp.status_code != 200:
                    print(f"[FALHOU] Resposta {case.label}: HTTP {resp.status_code} — {resp.text}")
                    all_passed = False
                    continue

                body = resp.json()
                actual_score = body["score"]
                actual_covered = _covered_map(body["rubric_hits"])

                score_ok = math.isclose(actual_score, case.expected_score, abs_tol=1e-9)
                covered_ok = actual_covered == case.expected_covered

                if score_ok and covered_ok:
                    print(f"[passou] Resposta {case.label}: score={actual_score:.4f}")
                else:
                    all_passed = False
                    print(f"[FALHOU] Resposta {case.label}")
                    print(
                        f"  score esperado={case.expected_score:.4f} obtido={actual_score:.4f}"
                    )
                    print(f"  covered esperado={case.expected_covered}")
                    print(f"  covered obtido  ={actual_covered}")
    finally:
        await _cleanup(session_factory, source_id)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
