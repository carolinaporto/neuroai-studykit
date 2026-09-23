"""Grades one student answer against an item's rubric.

CLAUDE.md invariant 2: the LLM only ever returns `covered: true|false` per rubric point —
`compute_score` is the one place a numeric score is produced, in plain Python, so the same
rubric + coverage always yields the same score. Invariant 7: the student's answer enters
the prompt as clearly delimited data (see `prompts/grade_v1.md`'s `<student_response>`
block), never concatenated into the instruction text.

Same shape as `packages/ingest/generator.py`: a versioned prompt file, one retry on a
malformed/non-conforming response, then give up. Every LLM call goes through the
`LLMClient` protocol (invariant 5) so tests inject `FakeLLM`.
"""

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from packages.core.llm import LLMClient

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "grade_v1.md"
MAX_ATTEMPTS = 2  # 1 try + 1 retry, per CLAUDE.md

SYSTEM_PROMPT = (
    "You follow the user's instructions exactly and respond with nothing but the JSON "
    "object requested: no markdown fences, no prose before or after it."
)


class GradedPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_id: str
    covered: bool
    evidence: str


class GradedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: list[GradedPoint]
    misconceptions: list[str]
    feedback_md: str


class GradingFailedError(Exception):
    """The model never returned a parseable, schema-conforming grading response, even
    after one retry."""


def load_prompt_template(path: Path = PROMPT_PATH) -> str:
    return path.read_text()


def prompt_version_hash(path: Path = PROMPT_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_DELIMITER_TAG_RE = re.compile(r"</?student_response>", re.IGNORECASE)


def _escape_delimiter(text: str) -> str:
    """Neutralizes a literal `<student_response>`/`</student_response>` inside untrusted
    student text before it's substituted into the prompt template.

    Invariant 7 says the student's text is delimited data, never able to act as an
    instruction — but a plain string substitution doesn't enforce that on its own: an
    answer containing the literal closing tag, followed by new instruction-like text, would
    render as content *outside* the delimited block, appearing to the model as if it came
    after the real boundary. Swapping `<`/`>` for the visually similar `‹`/`›` (U+2039/203A)
    keeps the text readable while making it impossible for the substituted text to match
    the exact string the prompt tells the model to treat as the boundary."""
    return _DELIMITER_TAG_RE.sub(lambda m: m.group(0).translate({60: "‹", 62: "›"}), text)


def render_prompt(
    template: str, *, item_prompt: str, rubric: list[dict], response_text: str
) -> str:
    points_block = "\n".join(f"- {p['id']}: {p['point']}" for p in rubric)
    rendered = template.replace("{{item_prompt}}", item_prompt)
    rendered = rendered.replace("{{rubric_points}}", points_block)
    rendered = rendered.replace("{{student_response}}", _escape_delimiter(response_text))
    return rendered


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def _strip_code_fence(raw: str) -> str:
    match = _CODE_FENCE_RE.match(raw.strip())
    return match.group(1) if match else raw


def _parse_response(raw: str) -> GradedResponse | None:
    """Returns the parsed `GradedResponse` if `raw` is valid JSON matching the schema,
    else None — the caller treats None as "malformed", worth a retry."""
    try:
        payload = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError:
        return None
    try:
        return GradedResponse.model_validate(payload)
    except ValidationError:
        return None


def compute_score(rubric: list[dict], covered_by_point_id: dict[str, bool]) -> float:
    """`Σ(weight of covered points) / Σ(weight)`, computed in plain Python — never asked
    of the LLM. A rubric point missing from `covered_by_point_id` counts as not covered:
    a safe default for aggregation, not an invented fact about the student's answer.

    Pure function of its inputs: the same `rubric` + `covered_by_point_id` always produces
    exactly the same score, deterministically, regardless of how many times it's called.
    """
    total_weight = sum(p["weight"] for p in rubric)
    covered_weight = sum(
        p["weight"] for p in rubric if covered_by_point_id.get(p["id"], False)
    )
    return covered_weight / total_weight


_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_response_text(text: str) -> str:
    """Normalization for the answer cache key only — unrelated to CLAUDE.md invariant 1's
    `collapse_whitespace` (that one governs literal `support_quote` matching). Here we
    also casefold, since two submissions that are the same answer modulo case should share
    one cached grading."""
    return _WHITESPACE_RUN.sub(" ", text).strip().casefold()


def response_hash_for(item_id: object, response_text: str) -> str:
    normalized = normalize_response_text(response_text)
    return hashlib.sha256(f"{item_id}:{normalized}".encode()).hexdigest()


# M7: `cloze`/`mcq` are graded without any LLM call (ARCHITECTURE.md §5) — both reduce to
# "does the student's text match `reference_answer`", so one function serves both. For mcq,
# `reference_answer` is the correct option's exact text (never its index — the client
# submits the option text it displayed), so the same check applies unchanged.
DETERMINISTIC_TYPES = {"cloze", "mcq"}


def grade_exact_match(
    *, rubric: list[dict], reference_answer: str, response_text: str
) -> tuple[dict[str, bool], str]:
    """Pure function, no ORM object, no LLM — same style as `grade_response`'s own
    signature. `rubric` always has exactly one point for these types (CLAUDE.md invariant 1
    still applies to it — see `generated_item.py`'s `_rubric_length_by_type`), so there's
    exactly one `covered_by_point_id` entry to produce."""
    point_id = rubric[0]["id"]
    correct = normalize_response_text(response_text) == normalize_response_text(reference_answer)
    feedback = "Correct." if correct else f"Not quite — the expected answer was: {reference_answer}"
    return {point_id: correct}, feedback


async def grade_response(
    *,
    item_prompt: str,
    rubric: list[dict],
    response_text: str,
    llm: LLMClient,
    prompt_template: str | None = None,
) -> GradedResponse:
    template = prompt_template if prompt_template is not None else load_prompt_template()
    rendered = render_prompt(
        template, item_prompt=item_prompt, rubric=rubric, response_text=response_text
    )

    last_error = "no attempts made"
    for _attempt in range(1, MAX_ATTEMPTS + 1):
        raw = await llm.complete_json(system=SYSTEM_PROMPT, user=rendered)
        parsed = _parse_response(raw)
        if parsed is None:
            last_error = f"response is not a JSON object matching the grading schema: {raw!r}"
            continue
        return parsed

    raise GradingFailedError(f"gave up after {MAX_ATTEMPTS} attempts: {last_error}")
