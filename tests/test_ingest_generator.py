"""Tests for `ingest.generator` against `FakeLLM` (CLAUDE.md invariant 5: no test calls the
real Anthropic API). Uses the real `packages/ingest/topics.yaml` (week 3 = Hebbian
plasticity / LTP / supervised & reinforcement learning), not a mock vocabulary, so these
tests exercise the actual controlled vocabulary the generator will run against.
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
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
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
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
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
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
    )

    assert len(result.items) == 1  # the good item in the same batch is still saved
    assert len(result.rejected) == 1
    assert "support_quote not found verbatim" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_malformed_json_retries_once_then_fails() -> None:
    llm = FakeLLM(["not json at all", "still not json, sorry"])

    with pytest.raises(GenerationFailedError):
        await generate_items_for_chunk(
            chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
        )

    assert len(llm.calls) == 2  # exactly one retry, not more


@pytest.mark.asyncio
async def test_malformed_json_then_good_response_succeeds_on_retry() -> None:
    llm = FakeLLM(["{not valid json", json.dumps({"items": [_good_item()]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
    )

    assert len(result.items) == 1
    assert result.attempts == 2
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_one_point_rubric_is_rejected() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_item(rubric=[GOOD_RUBRIC[0]])]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
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
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "self-answerable" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_unknown_topic_is_rejected() -> None:
    llm = FakeLLM([json.dumps({"items": [_good_item(topics=["quantum-entanglement"])]})])

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
    )

    assert result.items == []
    assert len(result.rejected) == 1
    assert "unknown topic" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_proposed_topics_are_collected_but_never_persisted() -> None:
    llm = FakeLLM(
        [json.dumps({"items": [_good_item(proposed_topics=["synaptic tagging and capture"])]})]
    )

    result = await generate_items_for_chunk(
        chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm
    )

    assert len(result.items) == 1
    assert not hasattr(result.items[0], "proposed_topics")
    assert result.proposed_topics == ["synaptic tagging and capture"]


@pytest.mark.asyncio
async def test_prompt_is_rendered_with_week_scoped_topics_only() -> None:
    """The prompt must offer only week 3's unit topics + cross_cutting, never the full
    155-topic vocabulary."""
    llm = FakeLLM([json.dumps({"items": []})])

    await generate_items_for_chunk(chunk_text=CHUNK_TEXT, week=3, vocabulary=_vocabulary(), llm=llm)

    rendered = llm.calls[0]["user"]
    assert "hebbian-plasticity" in rendered  # week 3 unit topic
    assert "single-unit-recording" in rendered  # cross_cutting topic
    assert "hubel-wiesel" not in rendered  # a week 5 topic must not leak in
