"""Turns one chunk's text into validated, ready-to-persist items.

CLAUDE.md invariant 5: the only way this module talks to an LLM is through `LLMClient`
(`packages/core/llm.py`); tests inject `FakeLLM`. The prompt itself is the versioned file
`prompts/generate_v1.md`, never an inline string — its sha256 becomes `Item.gen_prompt_version`
so you can tell which questions came from which prompt version later.

Retry policy: "1 retentativa depois falha" applies only to the outer JSON shape (it doesn't
parse, or isn't `{"items": [...]}`) — that's the model failing to follow instructions at
all. Once that much parses, every item is validated on its own: a bad item is rejected and
recorded, the good ones in the same response are still saved. Re-asking the model for a
whole new batch because one of five items had an invalid quote would waste four good items
and another paid call.
"""

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from packages.core.llm import LLMClient

from .generated_item import GeneratedItem, RejectedItem, ValidatedItem
from .topics import TopicEntry, TopicsVocabulary
from .validators import ItemRejected, validate_generated_item

PROMPT_PATH = Path(__file__).parent / "prompts" / "generate_v1.md"
MAX_ATTEMPTS = 2  # 1 try + 1 retry, per CLAUDE.md

SYSTEM_PROMPT = (
    "You follow the user's instructions exactly and respond with nothing but the JSON "
    "object requested: no markdown fences, no prose before or after it."
)


class GenerationFailedError(Exception):
    """The model never returned a parseable `{"items": [...]}` shape, even after one retry."""


class GenerationResult:
    def __init__(
        self,
        items: list[ValidatedItem],
        rejected: list[RejectedItem],
        proposed_topics: list[str],
        attempts: int,
    ) -> None:
        self.items = items
        self.rejected = rejected
        self.proposed_topics = proposed_topics
        self.attempts = attempts


def load_prompt_template(path: Path = PROMPT_PATH) -> str:
    return path.read_text()


def prompt_version_hash(path: Path = PROMPT_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def format_topics_csv(topics: list[TopicEntry]) -> str:
    return "\n".join(f"- {t.slug}: {t.label}" for t in topics)


def render_prompt(template: str, *, chunk_text: str, topics: list[TopicEntry]) -> str:
    """Substitutes `{{topics_csv}}` before `{{chunk_text}}`. Order matters: if a chunk of
    course text happened to contain the literal string `{{chunk_text}}`, replacing that
    placeholder first would corrupt the topics section, since the chunk's own copy of the
    placeholder would get overwritten by the *second* substitution instead of the real one."""
    rendered = template.replace("{{topics_csv}}", format_topics_csv(topics))
    rendered = rendered.replace("{{chunk_text}}", chunk_text)
    return rendered


def _parse_batch_shape(raw: str) -> list[dict] | None:
    """Returns the raw `items` list if `raw` is `{"items": [...]}`, else None — the caller
    treats None as "malformed", worth a retry."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    return items


def _validate_items(
    raw_items: list[dict], *, chunk_text: str, allowed_topics: dict[str, str]
) -> tuple[list[ValidatedItem], list[RejectedItem], list[str]]:
    accepted: list[ValidatedItem] = []
    rejected: list[RejectedItem] = []
    proposed_topics: list[str] = []

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            rejected.append(
                RejectedItem(reason="item is not a JSON object", raw={"value": raw_item})
            )
            continue
        try:
            item = GeneratedItem.model_validate(raw_item)
        except ValidationError as exc:
            rejected.append(RejectedItem(reason=f"schema validation failed: {exc}", raw=raw_item))
            continue

        for topic in item.proposed_topics:
            if topic not in proposed_topics:
                proposed_topics.append(topic)

        try:
            validated = validate_generated_item(
                item, chunk_text=chunk_text, allowed_topics=allowed_topics
            )
        except ItemRejected as exc:
            rejected.append(RejectedItem(reason=str(exc), raw=raw_item))
            continue

        accepted.append(validated)

    return accepted, rejected, proposed_topics


async def generate_items_for_chunk(
    *,
    chunk_text: str,
    week: int,
    vocabulary: TopicsVocabulary,
    llm: LLMClient,
    prompt_template: str | None = None,
) -> GenerationResult:
    template = prompt_template if prompt_template is not None else load_prompt_template()
    topics = vocabulary.topics_for_week(week)
    allowed_topics = TopicsVocabulary.alias_map(topics)
    rendered = render_prompt(template, chunk_text=chunk_text, topics=topics)

    last_error = "no attempts made"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = await llm.complete_json(system=SYSTEM_PROMPT, user=rendered)
        raw_items = _parse_batch_shape(raw)
        if raw_items is None:
            last_error = f"response is not a JSON object shaped {{'items': [...]}}: {raw!r}"
            continue

        accepted, rejected, proposed_topics = _validate_items(
            raw_items, chunk_text=chunk_text, allowed_topics=allowed_topics
        )
        return GenerationResult(
            items=accepted, rejected=rejected, proposed_topics=proposed_topics, attempts=attempt
        )

    raise GenerationFailedError(f"gave up after {MAX_ATTEMPTS} attempts: {last_error}")
