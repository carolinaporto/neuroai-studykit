"""Pure ingestion package.

Invariant (CLAUDE.md #4): this package never imports from apps.api. It receives
bytes/paths and returns Pydantic objects, so it can run and be tested without a server.
"""
