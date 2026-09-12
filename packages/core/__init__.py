"""Shared, dependency-light infrastructure used by both `apps/api` and `packages/ingest`.

Lives outside `apps/api` for the same reason `packages/db` does (see its `base.py`):
invariant 4 forbids `packages/ingest` from importing `apps.api`, but `packages/ingest`
(the offline generator) and `apps/api` (the future online grader) both need `LLMClient`.
"""
