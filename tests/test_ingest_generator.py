"""Tests for `ingest.generator` against `FakeLLM` (CLAUDE.md invariant 5: no test calls the
real Anthropic API). Uses the real `packages/ingest/topics.yaml` — week 0 (topics.yaml's
u03: Hebbian plasticity / LTP / supervised & reinforcement learning, parked there because
it isn't taught this semester, but its vocabulary is still real and still needs a unit
some week can resolve to), not a mock vocabulary, so these tests exercise the actual
controlled vocabulary the generator will run against.
"""

import json

import pytest
from ingest.generator import GenerationFailedError, generate_items_for_chunk
from ingest.topics import load_topics

from packages.core.llm import FakeLLM

CHUNK_TEXT = (
    'Hebbian plasticity is often summarized as "cells that fire together wire together." '
    "Long-term potentiation is a persistent increase in synaptic strength following brief "
    "high-frequency stimulation of a presynaptic pathway."
)

GOOD_RUBRIC = [
    {
        "point": "Repeated joint activity of two connected neurons strengthens their connection.",
        "weight": 1.0,
        "support_quote": 'Hebbian plasticity is often summarized as "cells that fire together '
        'wire together."',
    },
    {
        "point": "A brief burst of high-frequency stimulation can produce a lasting increase "
        "in synaptic strength.",
        "weight": 1.0,
        "support_quote": "Long-term potentiation is a persistent increase in synaptic strength "
        "following brief high-frequency stimulation of a presynaptic pathway.",
    },
]


def _good_item(**overrides: object) -> dict:
    item = {
        "type": "free_recall",
        "prompt": "Explain what determines whether repeated activity between two connected "
        "neurons leads to a lasting change in the strength of their connection.",
        "reference_answer": "When a presynaptic neuron repeatedly helps drive a postsynaptic "
        "neuron to fire, the connection between them strengthens; a brief high-frequency "
        "burst of activity can produce this kind of lasting increase in synaptic strength.",
        "rubric": GOOD_RUBRIC,
        "difficulty": 2,
        "bloom": "understand",
        "topics": ["hebbian-plasticity", "LTP"],  # "LTP" is an alias of ltp-ltd
        "proposed_topics": [],
    }
    item.update(overrides)
    return item


def _vocabulary():
    return load_topics()


@pytest.mark.asyncio
async def test_good_output_is_accepted_with_normalized_topics() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_item()]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.rejected == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.topics == ["hebbian-plasticity", "ltp-ltd"]  # alias normalized to canonical
    assert [p.id for p in item.rubric] == ["p1", "p2"]
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_empty_batch_is_success_not_a_failure() -> None:
    """A chunk with no substantive content (title slide, references page) should yield zero
    items without that being treated as an error."""
    llm = FakeLLM([json.dumps({"items": []})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert result.rejected == []
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_invented_quote_is_rejected_not_the_whole_batch() -> None:
    bad_rubric = [
        GOOD_RUBRIC[0],
        {
            "point": "A fabricated claim not present in the chunk.",
            "weight": 1.0,
            "support_quote": "This exact sentence does not appear anywhere in the chunk text.",
        },
    ]
    llm = FakeLLM(
        [json.dumps({"items": [_good_item(), _good_item(rubric=bad_rubric)]})]
    )

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert len(result.items) == 1  # the good item in the same batch is still saved
    assert len(result.rejected) == 1
    assert "support_quote not found verbatim" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_quote_with_mid_sentence_newline_in_chunk_is_still_accepted() -> None:
    """PyMuPDF wraps PDF text with a literal newline wherever the page renderer wrapped a
    line, including mid-sentence; a model quoting that sentence normalizes it to a space,
    exactly like a person copying text off a page would. That's an extraction artifact, not
    a paraphrase, and CLAUDE.md invariant 1 now explicitly tolerates only this one class of
    difference — this test is what proves that tolerance actually fires."""
    pdf_like_chunk = (
        "Hebbian plasticity is often summarized as \"cells that fire together wire\ntogether.\" "
        "Long-term potentiation is a persistent increase in synaptic strength following brief "
        "high-frequency stimulation of a presynaptic pathway."
    )
    rubric = [
        {
            "point": GOOD_RUBRIC[0]["point"],
            "weight": 1.0,
            # same words as the chunk, but with a plain space where the chunk has "\n"
            "support_quote": 'Hebbian plasticity is often summarized as "cells that fire '
            'together wire together."',
        },
        GOOD_RUBRIC[1],
    ]
    llm = FakeLLM([json.dumps({"items": [_good_item(rubric=rubric)]})])

    result = await generate_items_for_chunk(
        chunk_text=pdf_like_chunk, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.rejected == []
    assert len(result.items) == 1


@pytest.mark.asyncio
async def test_quote_differing_by_more_than_whitespace_is_still_rejected() -> None:
    """Whitespace collapse must not become a crack that lets a genuinely altered quote
    through — only runs of space/tab/newline are equivalent, nothing else."""
    pdf_like_chunk = (
        "Hebbian plasticity is often summarized as \"cells that fire together wire\ntogether.\" "
        "Long-term potentiation is a persistent increase in synaptic strength following brief "
        "high-frequency stimulation of a presynaptic pathway."
    )
    rubric = [
        {
            "point": GOOD_RUBRIC[0]["point"],
            "weight": 1.0,
            # one word changed ("wired" instead of "wire") on top of the whitespace change
            "support_quote": 'Hebbian plasticity is often summarized as "cells that fire '
            'together wired together."',
        },
        GOOD_RUBRIC[1],
    ]
    llm = FakeLLM([json.dumps({"items": [_good_item(rubric=rubric)]})])

    result = await generate_items_for_chunk(
        chunk_text=pdf_like_chunk, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "support_quote not found verbatim" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_malformed_json_retries_once_then_fails() -> None:
    llm = FakeLLM(["not json at all", "still not json, sorry"])

    with pytest.raises(GenerationFailedError):
        await generate_items_for_chunk(
            chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
        )

    assert len(llm.calls) == 2  # exactly one retry, not more


@pytest.mark.asyncio
async def test_malformed_json_then_good_response_succeeds_on_retry() -> None:
    llm = FakeLLM(["{not valid json", json.dumps({"items": [_good_item()]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert len(result.items) == 1
    assert result.attempts == 2
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_one_point_rubric_is_rejected() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_item(rubric=[GOOD_RUBRIC[0]])]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "schema validation failed" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_self_answerable_item_is_rejected() -> None:
    leaking_prompt = (
        'Given that Hebbian plasticity is often summarized as "cells that fire together wire '
        'together." explain why that happens in terms of synaptic strength.'
    )
    llm = FakeLLM([json.dumps({"items": [_good_item(prompt=leaking_prompt)]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "self-answerable" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_unknown_topic_is_rejected() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_item(topics=["quantum-entanglement"])]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "unknown topic" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_item_with_no_matching_topic_is_kept_untagged() -> None:
    """A chunk whose concepts the week's vocabulary doesn't cover comes back with
    `topics: []` and the concept in `proposed_topics`. The item is anchored and gradable, so
    it must be saved untagged — not rejected over a tag."""
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "items": [
                        _good_item(
                            topics=[], proposed_topics=["evolutionary views of intelligence"]
                        )
                    ]
                }
            )
        ]
    )

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.rejected == []
    assert len(result.items) == 1
    assert result.items[0].topics == []
    assert result.proposed_topics == ["evolutionary views of intelligence"]


@pytest.mark.asyncio
async def test_proposed_topics_are_collected_but_never_persisted() -> None:
    llm = FakeLLM(
        [json.dumps({"items": [_good_item(proposed_topics=["synaptic tagging and capture"])]})]
    )

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert len(result.items) == 1
    assert not hasattr(result.items[0], "proposed_topics")
    assert result.proposed_topics == ["synaptic tagging and capture"]


@pytest.mark.asyncio
async def test_json_wrapped_in_markdown_fence_is_still_accepted() -> None:
    """Real models sometimes wrap the JSON in ```json fences despite being told not to —
    that's a formatting quirk, not a malformed response, and shouldn't burn the retry."""
    fenced = "```json\n" + json.dumps({"items": [_good_item()]}) + "\n```"
    llm = FakeLLM([fenced])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert len(result.items) == 1
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_prompt_is_rendered_with_week_scoped_topics_only() -> None:
    """The prompt must offer only week 0's unit topics + cross_cutting, never the full
    155-topic vocabulary."""
    llm = FakeLLM([json.dumps({"items": []})])

    await generate_items_for_chunk(chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm)

    rendered = llm.calls[0]["user"]
    assert "hebbian-plasticity" in rendered  # week 0 unit topic
    assert "single-unit-recording" in rendered  # cross_cutting topic
    assert "hubel-wiesel" not in rendered  # a week 0 topic must not leak in


def _good_mcq_item(**overrides: object) -> dict:
    item = {
        "type": "mcq",
        "prompt": "Which mechanism is described as cells that fire together wiring together?",
        "reference_answer": "Hebbian plasticity",
        "rubric": [GOOD_RUBRIC[0]],
        "choices": {"options": ["Hebbian plasticity", "Long-term depression", "Apoptosis"]},
        "difficulty": 2,
        "bloom": "recall",
        "topics": ["hebbian-plasticity"],
        "proposed_topics": [],
    }
    item.update(overrides)
    return item


def _good_cloze_item(**overrides: object) -> dict:
    item = {
        "type": "cloze",
        "prompt": "_____ is often summarized as cells that fire together wire together.",
        "reference_answer": "Hebbian plasticity",
        "rubric": [GOOD_RUBRIC[0]],
        "difficulty": 1,
        "bloom": "recall",
        "topics": ["hebbian-plasticity"],
        "proposed_topics": [],
    }
    item.update(overrides)
    return item


@pytest.mark.asyncio
async def test_good_mcq_item_is_accepted_with_shuffled_choices() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_mcq_item()]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.rejected == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.choices is not None
    assert set(item.choices["options"]) == {
        "Hebbian plasticity",
        "Long-term depression",
        "Apoptosis",
    }
    assert item.reference_answer in item.choices["options"]
    assert len(item.rubric) == 1


@pytest.mark.asyncio
async def test_mcq_missing_choices_is_rejected() -> None:
    raw = _good_mcq_item()
    del raw["choices"]
    llm = FakeLLM([json.dumps({"items": [raw]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "schema validation failed" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_mcq_reference_answer_not_among_choices_is_rejected() -> None:
    llm = FakeLLM(
        [json.dumps({"items": [_good_mcq_item(reference_answer="Something else entirely")]})]
    )

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "reference_answer" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_mcq_with_two_rubric_points_is_rejected() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_mcq_item(rubric=GOOD_RUBRIC)]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "exactly 1 rubric point" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_good_cloze_item_is_accepted() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_cloze_item()]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.rejected == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.choices is None
    assert len(item.rubric) == 1
    assert item.reference_answer == "Hebbian plasticity"


@pytest.mark.asyncio
async def test_cloze_prompt_with_no_blank_is_rejected() -> None:
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "items": [
                        _good_cloze_item(
                            prompt="Hebbian plasticity is cells that fire together wire together."
                        )
                    ]
                }
            )
        ]
    )

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "exactly one" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_cloze_prompt_with_two_blanks_is_rejected() -> None:
    llm = FakeLLM(
        [json.dumps({"items": [_good_cloze_item(prompt="_____ is _____ wire together.")]})]
    )

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "exactly one" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_free_recall_still_rejects_choices_and_still_needs_two_to_five_points() -> None:
    """Regression: M7's per-type rubric/choices rules must not loosen the original types."""
    with_choices = _good_item(choices={"options": ["a", "b", "c"]})
    one_point = _good_item(rubric=[GOOD_RUBRIC[0]])
    llm = FakeLLM([json.dumps({"items": [with_choices, one_point]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=0, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 2
