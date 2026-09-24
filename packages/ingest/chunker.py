"""Turns ParsedBlocks into Chunks: target 500-900 tokens, ~15% overlap, never split mid-block
except when a single block alone exceeds the ceiling (then split on sentence boundaries, never
mid-sentence). Short blocks (e.g. a sparse slide) are folded into a neighbor first, keeping
both locators, so a fragment never becomes its own chunk.
"""

import re
from dataclasses import dataclass, field

from .models import Chunk, Locator, ParsedBlock

MIN_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 900
OVERLAP_RATIO = 0.15
SHORT_BLOCK_TOKENS = 120
# A dense source naturally splits every ~2-4 pages anyway (token ceiling hits first); this
# only bites for sparse content, forcing a split before a chunk can sprawl across dozens of
# pages the way a real 40-page slide deck's bullet-per-page text otherwise would.
MAX_LOCATORS_PER_CHUNK = 5

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    """Cheap word-count heuristic (~1.3 tokens/word for English) — no tokenizer dependency."""
    words = text.split()
    if not words:
        return 0
    return max(1, round(len(words) * 1.3))


@dataclass
class _Piece:
    text: str
    locators: list[Locator]
    token_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.token_count = estimate_tokens(self.text)


def _split_long_pieces(pieces: list[_Piece], max_tokens: int) -> list[_Piece]:
    result: list[_Piece] = []
    for piece in pieces:
        if piece.token_count <= max_tokens:
            result.append(piece)
            continue
        current = ""
        for sentence in _SENTENCE_SPLIT.split(piece.text):
            candidate = f"{current} {sentence}".strip() if current else sentence
            if current and estimate_tokens(candidate) > max_tokens:
                result.append(_Piece(text=current, locators=list(piece.locators)))
                current = sentence
            else:
                current = candidate
        if current:
            result.append(_Piece(text=current, locators=list(piece.locators)))
    return result


def _tail_by_sentences(text: str, budget_tokens: int) -> str:
    """Trailing sentences of text that fit in budget_tokens — a sentence-safe partial overlap
    for when the whole preceding block is bigger than the overlap budget. Returns "" if even
    the last sentence alone doesn't fit: the max_tokens ceiling always wins over having some
    overlap."""
    tail = ""
    for sentence in reversed(_SENTENCE_SPLIT.split(text)):
        candidate = f"{sentence} {tail}".strip() if tail else sentence
        if estimate_tokens(candidate) > budget_tokens:
            break
        tail = candidate
    return tail


def _merge(a: _Piece, b: _Piece) -> _Piece:
    return _Piece(text=f"{a.text}\n\n{b.text}", locators=[*a.locators, *b.locators])


def _merge_short_pieces(
    pieces: list[_Piece], short_threshold: int, max_tokens: int, max_locators: int
) -> list[_Piece]:
    """Fold a short piece (e.g. a sparse slide) into a neighbor so it never becomes its own
    chunk — but only when the merge still fits under max_tokens, so a short trailing piece
    next to an already-large one is left standalone rather than pushed over the ceiling.
    Also capped by max_locators: without this, a long run of short blocks (e.g. a sparse
    slide deck's one-bullet-per-page text) would merge into a single piece carrying more
    locators than _accumulate's own cap allows — _accumulate can only flush *between*
    pieces, never split one apart, so the cap has to hold here too."""
    merged: list[_Piece] = []
    for piece in pieces:
        if (
            merged
            and merged[-1].token_count < short_threshold
            and merged[-1].token_count + piece.token_count <= max_tokens
            and len(merged[-1].locators) + len(piece.locators) <= max_locators
        ):
            merged.append(_merge(merged.pop(), piece))
        else:
            merged.append(piece)

    if (
        len(merged) > 1
        and merged[-1].token_count < short_threshold
        and merged[-2].token_count + merged[-1].token_count <= max_tokens
        and len(merged[-2].locators) + len(merged[-1].locators) <= max_locators
    ):
        last = merged.pop()
        prev = merged.pop()
        merged.append(_merge(prev, last))

    return merged


def _accumulate(
    pieces: list[_Piece],
    min_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
    max_locators: int,
) -> list[Chunk]:
    if not pieces:
        return []

    overlap_budget = round(max_tokens * overlap_ratio)
    chunks: list[Chunk] = []
    current: list[_Piece] = []
    current_tokens = 0

    def flush(group: list[_Piece]) -> None:
        text = "\n\n".join(p.text for p in group)
        locators = [loc for p in group for loc in p.locators]
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                text=text,
                token_count=estimate_tokens(text),
                locators=locators,
            )
        )

    for piece in pieces:
        overflowing = current_tokens + piece.token_count > max_tokens
        # A sparse source (short blocks, e.g. a slide deck's bullet-per-page text) can
        # accumulate dozens of pages' worth of pieces without ever crossing max_tokens —
        # the token ceiling alone never fires, so one "chunk" ends up spanning the whole
        # source. This second trigger is independent of min_tokens on purpose: it has to
        # fire even when current_tokens never reaches it, which is exactly the case it
        # exists for.
        current_locators = sum(len(p.locators) for p in current)
        too_many_locators = current and current_locators + len(piece.locators) > max_locators
        if current and ((overflowing and current_tokens >= min_tokens) or too_many_locators):
            flush(current)
            # Leave room for `piece` itself so overlap + piece can never jointly exceed either
            # ceiling — a plain flush-on-next-overflow check wouldn't catch that combination.
            # The locator budget matters just as much as the token one here: without it, carrying
            # a full overlap piece forward plus the next piece can itself exceed max_locators,
            # even though each individually respects the cap (this is what broke the sparse-deck
            # case — flushing on locator count still isn't enough if overlap immediately puts the
            # new group right back over the limit).
            budget_for_step = max(0, min(overlap_budget, max_tokens - piece.token_count))
            locator_budget_for_step = max(0, max_locators - len(piece.locators))
            overlap: list[_Piece] = []
            overlap_tokens = 0
            overlap_locators = 0
            for prev_piece in reversed(current):
                remaining_budget = budget_for_step - overlap_tokens
                remaining_locator_budget = locator_budget_for_step - overlap_locators
                if remaining_budget <= 0 or remaining_locator_budget <= 0:
                    break
                if (
                    prev_piece.token_count <= remaining_budget
                    and len(prev_piece.locators) <= remaining_locator_budget
                ):
                    overlap.insert(0, prev_piece)
                    overlap_tokens += prev_piece.token_count
                    overlap_locators += len(prev_piece.locators)
                    continue
                tail_text = _tail_by_sentences(prev_piece.text, remaining_budget)
                if tail_text and len(prev_piece.locators) <= remaining_locator_budget:
                    tail_piece = _Piece(text=tail_text, locators=list(prev_piece.locators))
                    overlap.insert(0, tail_piece)
                    overlap_tokens += tail_piece.token_count
                    overlap_locators += len(tail_piece.locators)
                break
            current = overlap
            current_tokens = overlap_tokens
        current.append(piece)
        current_tokens += piece.token_count

    if current:
        flush(current)

    return chunks


def chunk_blocks(
    blocks: list[ParsedBlock],
    *,
    min_tokens: int = MIN_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_ratio: float = OVERLAP_RATIO,
    short_block_tokens: int = SHORT_BLOCK_TOKENS,
    max_locators_per_chunk: int = MAX_LOCATORS_PER_CHUNK,
) -> list[Chunk]:
    pieces = [_Piece(text=b.text.strip(), locators=[b.locator]) for b in blocks if b.text.strip()]
    pieces = _split_long_pieces(pieces, max_tokens)
    pieces = _merge_short_pieces(pieces, short_block_tokens, max_tokens, max_locators_per_chunk)
    return _accumulate(pieces, min_tokens, max_tokens, overlap_ratio, max_locators_per_chunk)
