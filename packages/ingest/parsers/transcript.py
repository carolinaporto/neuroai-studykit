"""VTT/SRT transcript parser: one ParsedBlock per cue, locator {"t0": seconds, "t1": seconds}.

Hand-rolled instead of pulling in a dependency: both formats are cue blocks separated by a
blank line, each with a timestamp line and one or more text lines. SRT prefixes the cue with
a numeric index and uses commas in timestamps; VTT starts with a "WEBVTT" header and uses
dots. A single regex on the timestamp line covers both.
"""

import re

from ..models import Locator, ParsedBlock

_TIMESTAMP = re.compile(
    r"(\d+):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[.,](\d{3})"
)


def _to_seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_transcript(data: bytes) -> list[ParsedBlock]:
    text = data.decode("utf-8")
    blocks: list[ParsedBlock] = []

    for raw_cue in re.split(r"\n\s*\n", text.strip()):
        lines = [line for line in raw_cue.splitlines() if line.strip()]
        match: re.Match[str] | None = None
        content_lines: list[str] = []

        for line in lines:
            if match is None:
                found = _TIMESTAMP.search(line)
                if found:
                    match = found
                    continue
                if line.strip().isdigit() or line.strip().upper() == "WEBVTT":
                    continue  # SRT cue index or the VTT header line
            else:
                content_lines.append(line.strip())

        if match is None or not content_lines:
            continue

        t0 = _to_seconds(*match.groups()[0:4])
        t1 = _to_seconds(*match.groups()[4:8])
        blocks.append(ParsedBlock(text=" ".join(content_lines), locator=Locator(t0=t0, t1=t1)))

    return blocks
