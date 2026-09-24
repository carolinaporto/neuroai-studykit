"""Loads the controlled topic vocabulary from `packages/ingest/topics.yaml` (see that
file's header for the format and why it exists).

Pure data access (invariant 4): no db, no app config. `generator.py` uses this to build the
"choose only from this list" section of the prompt for a given week, and to validate and
normalize the `topics` an item comes back with.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

TOPICS_PATH = Path(__file__).parent / "topics.yaml"

# Real syllabus weeks run 2-14 this semester (see topics.yaml `units`; some have no unit —
# a pure-intro week, the midterm, a no-class week, or content not yet written). 90/91 are
# not real course weeks — they exist only so the synthetic fixture corpus (tests/fixtures/)
# can be synced under a week number and run through `generate` as a smoke test, without a
# real week's number ever colliding with fixture data in a dev database. No separate "dev
# mode" flag is needed because the numbers themselves can never appear in a real
# content/weekNN folder.
# 90 -> u02 (neurons/synapses: the PDF fixture, real week 4) and 91 -> u03 (Hebbian
# learning + ML/RL basics: the pptx/vtt fixtures) are the closest units to what those
# fixtures cover — u03 is parked at week 0 (not taught this semester, topics.yaml's own
# comment on it), which is fine here: this alias only needs *a* week whose unit offers
# hebbian-plasticity, not a real one.
FIXTURE_WEEK_ALIASES = {90: 4, 91: 0}


class TopicEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    label: str
    side: Literal["neuro", "ai", "bridge"]
    aliases: list[str] = Field(default_factory=list)
    deprecated: bool = False


class Unit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    week: int
    title: str
    topics: list[TopicEntry]


class TopicsVocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    cross_cutting: list[TopicEntry] = Field(default_factory=list)
    units: list[Unit]

    def title_for_week(self, week: int) -> str | None:
        """The unit title for a syllabus week (e.g. "Learning, development, and the growth
        of intelligence" for week 3) — used by the Sources page's week header. `None` for a
        week with no matching unit, same fallback behavior as `topics_for_week` but without
        raising, since listing sources for an unmapped week is a normal read, not a
        generation-time error."""
        lookup_week = FIXTURE_WEEK_ALIASES.get(week, week)
        unit = next((u for u in self.units if u.week == lookup_week), None)
        return unit.title if unit else None

    def topics_for_week(self, week: int) -> list[TopicEntry]:
        """Cross-cutting topics plus that week's unit topics — never the whole vocabulary,
        so the prompt stays focused (deprecated entries are never offered). Falls back to
        `FIXTURE_WEEK_ALIASES` for the synthetic fixture's own week numbers (90/91)."""
        lookup_week = FIXTURE_WEEK_ALIASES.get(week, week)
        unit = next((u for u in self.units if u.week == lookup_week), None)
        if unit is None:
            raise ValueError(f"topics.yaml has no unit with week={week}")
        offered = [*self.cross_cutting, *unit.topics]
        return [t for t in offered if not t.deprecated]

    @staticmethod
    def alias_map(topics: list[TopicEntry]) -> dict[str, str]:
        """Maps lowercased slug/alias -> canonical slug, for normalizing what the model
        returns. Built only from the topics actually offered to the prompt, not the whole
        vocabulary, so an item can't claim a topic it was never shown."""
        mapping: dict[str, str] = {}
        for topic in topics:
            mapping[topic.slug.lower()] = topic.slug
            for alias in topic.aliases:
                mapping[alias.lower()] = topic.slug
        return mapping


def load_topics(path: Path = TOPICS_PATH) -> TopicsVocabulary:
    data = yaml.safe_load(path.read_text())
    return TopicsVocabulary.model_validate(data)
