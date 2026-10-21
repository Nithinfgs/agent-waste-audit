"""Data model shared by the parser, detectors and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CHARS_PER_TOKEN = 4  # rough heuristic; transcripts do not record per-result token counts


def est_tokens(chars: int) -> int:
    return chars // CHARS_PER_TOKEN


@dataclass
class Usage:
    input: int = 0
    cache_creation: int = 0
    cache_read: int = 0
    output: int = 0


@dataclass
class Turn:
    """One assistant API response (deduplicated by message id)."""

    index: int
    usage: Usage
    timestamp: float | None = None  # unix seconds


@dataclass
class Call:
    id: str
    name: str
    input: dict[str, Any]
    turn: int
    result_chars: int = 0
    result_hash: str = ""
    is_error: bool = False
    has_result: bool = False

    @property
    def result_tokens(self) -> int:
        return est_tokens(self.result_chars)


@dataclass
class Session:
    path: str
    session_id: str
    turns: list[Turn] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    skipped_lines: int = 0

    @property
    def total_new_tokens(self) -> int:
        """Tokens that were freshly processed or generated (excludes cache reads)."""
        return sum(t.usage.input + t.usage.cache_creation + t.usage.output for t in self.turns)

    @property
    def total_cache_read(self) -> int:
        return sum(t.usage.cache_read for t in self.turns)


@dataclass
class Finding:
    kind: str
    summary: str
    tokens: int  # estimated avoidable tokens, counted once
    carried: int  # estimated extra tokens re-read from cache on later turns
    turn: int
    detail: str = ""
    hint: str = ""
