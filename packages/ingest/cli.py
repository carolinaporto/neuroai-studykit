"""CLI for the ingestion pipeline. M1 only has `parse`: no db, no app config (invariant 4)."""

import argparse
import json
import sys
from pathlib import Path

from .chunker import chunk_blocks
from .models import Chunk, Locator, ParsedBlock
from .parsers.pdf import parse_pdf
from .parsers.pptx import parse_pptx
from .parsers.transcript import parse_transcript

_PARSERS = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
    ".vtt": parse_transcript,
    ".srt": parse_transcript,
}


def parse_file(path: Path) -> list[ParsedBlock]:
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ValueError(f"no parser registered for extension {path.suffix!r}")
    return parser(path.read_bytes())


def _format_locator(locator: Locator) -> str:
    return ", ".join(f"{key}={value}" for key, value in locator.as_dict().items())


def _print_chunks(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        locators = " | ".join(_format_locator(loc) for loc in chunk.locators)
        print(f"--- chunk {chunk.ordinal} ({chunk.token_count} tokens) [{locators}] ---")
        print(chunk.text)
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="parse a file into chunks and print them")
    parse_cmd.add_argument("path", type=Path)
    parse_cmd.add_argument("--json", action="store_true", help="print chunks as JSON instead")

    args = parser.parse_args(argv)

    if args.command == "parse":
        blocks = parse_file(args.path)
        chunks = chunk_blocks(blocks)
        if args.json:
            print(json.dumps([c.model_dump() for c in chunks], indent=2))
        else:
            _print_chunks(chunks)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
