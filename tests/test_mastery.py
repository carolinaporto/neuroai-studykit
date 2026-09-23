"""Pure unit tests for `apps.api.services.mastery.mastery_by_topic` — no database, no app.
`apps/test_api_progress.py` and `tests/test_api_checkin.py` cover the same cases end-to-end
through the real endpoints; these exist because the aggregation itself is a pure function
and deserves a fast, direct test of its own.
"""

import uuid

import pytest

from apps.api.services.mastery import mastery_by_topic


def test_fans_a_score_out_across_every_topic_an_item_carries() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    item_topics = [(a, ["x"]), (b, ["x", "y"])]
    scores = {a: 1.0, b: 0.6}

    result = mastery_by_topic(item_topics, scores, {"x": "X label", "y": "Y label"})
    by_slug = {t.slug: t for t in result}

    assert by_slug["x"].item_count == 2
    assert by_slug["x"].attempted_count == 2
    assert by_slug["x"].avg_score == pytest.approx(0.8)
    assert by_slug["x"].label == "X label"
    assert by_slug["y"].item_count == 1
    assert by_slug["y"].avg_score == pytest.approx(0.6)


def test_unattempted_topic_has_null_avg_and_sorts_last() -> None:
    attempted, never = uuid.uuid4(), uuid.uuid4()
    item_topics = [(attempted, ["attempted"]), (never, ["never"])]
    scores = {attempted: 0.9}

    result = mastery_by_topic(item_topics, scores, {})
    by_slug = {t.slug: t for t in result}

    assert by_slug["never"].avg_score is None
    assert by_slug["never"].attempted_count == 0
    assert by_slug["never"].item_count == 1
    assert [t.slug for t in result] == ["attempted", "never"]


def test_sorts_weakest_first() -> None:
    low, mid, high = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    item_topics = [(low, ["low"]), (mid, ["mid"]), (high, ["high"])]
    scores = {low: 0.2, mid: 0.5, high: 0.9}

    result = mastery_by_topic(item_topics, scores, {})

    assert [t.slug for t in result] == ["low", "mid", "high"]


def test_a_topic_not_in_the_label_map_gets_a_null_label_not_an_error() -> None:
    item_id = uuid.uuid4()

    result = mastery_by_topic([(item_id, ["unknown-slug"])], {item_id: 1.0}, {})

    assert result[0].label is None
