"""Shared value types across API schemas."""

from typing import Literal

# The course's three lenses — design/synapse's README: "tag notes and homework... using the
# course's own three lenses — Neuroscience, Computer Science, Psychology — never invented
# category names." Shared by Homework and Notes; not a Postgres enum, same reasoning as
# Item.topics: a fourth lens shouldn't need a migration.
Discipline = Literal["Neuroscience", "Computer Science", "Psychology"]
