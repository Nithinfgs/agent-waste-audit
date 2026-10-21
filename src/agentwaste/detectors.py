"""Waste detectors. Each takes a :class:`Session` and returns a list of findings."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from .model import Call, Finding, Session, est_tokens

READ_TOOLS = {"Read", "NotebookRead"}
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
CACHE_TTL_SECONDS = 300  # the default 5-minute prompt cache lifetime


@dataclass(frozen=True)
class Config:
    oversized_chars: int = 20_000
    cache_miss_min_tokens: int = 10_000
    repeat_min: int = 3


def _path(call: Call) -> str | None:
    for key in ("file_path", "notebook_path", "path"):
        v = call.input.get(key)
        if isinstance(v, str):
            return v
    return None


def _carried(session: Session, call_turn: int, tokens: int) -> int:
    """Tokens re-read from cache on every later turn while the content stays in context."""
    return tokens * max(0, len(session.turns) - 1 - call_turn)


def _label(call: Call) -> str:
    if call.name == "Bash":
        return "Bash: " + str(call.input.get("command", ""))[:70].replace("\n", " ")
    p = _path(call)
    if p:
        return f"{call.name} {p}"
    return f"{call.name} {json.dumps(call.input, sort_keys=True)[:60]}"


def _redundant_pairs(session: Session) -> list[tuple[Call, Call]]:
    """(first read, repeated read) pairs for file ranges re-read with no change in between."""
    seen: dict[tuple[str, object, object], Call] = {}
    pairs: list[tuple[Call, Call]] = []
    for call in session.calls:
        path = _path(call)
        if path is None:
            continue
        if call.name in WRITE_TOOLS:
            for key in [k for k in seen if k[0] == path]:
                del seen[key]
        elif call.name in READ_TOOLS and call.has_result and not call.is_error:
            key = (path, call.input.get("offset"), call.input.get("limit"))
            first = seen.get(key)
            if first is not None and first.result_hash == call.result_hash:
                pairs.append((first, call))
            else:
                seen[key] = call
    return pairs


def redundant_reads(session: Session, cfg: Config) -> list[Finding]:
    """A file range re-read although nothing in the session changed it."""
    out: list[Finding] = []
    for first, call in _redundant_pairs(session):
        tokens = call.result_tokens
        out.append(
            Finding(
                "redundant_read",
                f"{_path(call)} re-read unchanged",
                tokens,
                _carried(session, call.turn, tokens),
                call.turn,
                f"first read at turn {first.turn}, again at turn {call.turn}",
                "Reference earlier output, or read only the needed line range.",
            )
        )
    return out


def oversized_outputs(session: Session, cfg: Config) -> list[Finding]:
    """A single tool result far larger than the agent plausibly needed."""
    out: list[Finding] = []
    already_counted = {id(call) for _, call in _redundant_pairs(session)}
    for call in session.calls:
        if call.name in WRITE_TOOLS or call.result_chars <= cfg.oversized_chars:
            continue
        if id(call) in already_counted:
            continue  # the whole re-read is already reported as redundant
        excess = est_tokens(call.result_chars - cfg.oversized_chars)
        out.append(
            Finding(
                "oversized_output",
                f"{_label(call)} returned ~{call.result_tokens:,} tokens",
                excess,
                _carried(session, call.turn, excess),
                call.turn,
                f"{call.result_chars:,} characters; threshold {cfg.oversized_chars:,}",
                "Narrow it: grep/head/tail, Read with offset+limit, or a tighter glob.",
            )
        )
    return out


def repeated_calls(session: Session, cfg: Config) -> list[Finding]:
    """Identical non-read calls: failing retries, or repeats with byte-identical output."""
    groups: dict[str, list[Call]] = {}
    for call in session.calls:
        if call.name in READ_TOOLS or call.name in WRITE_TOOLS or not call.has_result:
            continue
        key = call.name + json.dumps(call.input, sort_keys=True)
        groups.setdefault(key, []).append(call)

    out: list[Finding] = []
    for calls in groups.values():
        if len(calls) < cfg.repeat_min:
            continue
        errors = [c for c in calls if c.is_error]
        if len(errors) >= cfg.repeat_min - 1:
            wasted, kind, why = errors[1:], "retry_loop", "failed identically"
            hint = "Stop after the second identical failure; change the approach or inspect the error."
        else:
            by_hash: dict[str, list[Call]] = {}
            for c in calls:
                by_hash.setdefault(c.result_hash, []).append(c)
            same = max(by_hash.values(), key=len)
            if len(same) < cfg.repeat_min:
                continue
            wasted, kind, why = same[1:], "repeated_call", "returned identical output"
            hint = "Cache the result in notes or rely on the earlier output."
        tokens = sum(c.result_tokens for c in wasted)
        carried = sum(_carried(session, c.turn, c.result_tokens) for c in wasted)
        out.append(
            Finding(
                kind,
                f"{_label(calls[0])} ran {len(calls)}x and {why}",
                tokens,
                carried,
                wasted[0].turn,
                f"repeat turns: {', '.join(str(c.turn) for c in wasted)}",
                hint,
            )
        )
    return out


def cache_misses(session: Session, cfg: Config) -> list[Finding]:
    """Turns that rewrote a large prompt prefix instead of reading it from cache."""
    out: list[Finding] = []
    prev_ts: float | None = None
    for turn in session.turns:
        u = turn.usage
        if turn.index > 0 and u.cache_read == 0 and u.cache_creation >= cfg.cache_miss_min_tokens:
            gap = turn.timestamp - prev_ts if turn.timestamp and prev_ts else None
            expired = gap is not None and gap > CACHE_TTL_SECONDS
            if gap is not None and expired:
                detail = f"{gap / 60:.0f} min idle gap exceeded the 5-minute cache window"
                hint = "Expected after a long pause; not counted as avoidable."
            else:
                detail = "no idle gap explains it" if gap is not None else "idle gap unknown"
                hint = "A changed system prompt, tool list or early message invalidates the cache."
            out.append(
                Finding(
                    "cache_expiry" if expired else "cache_miss",
                    f"turn {turn.index} rewrote {u.cache_creation:,} cached tokens",
                    0 if expired else u.cache_creation,
                    0,
                    turn.index,
                    detail,
                    hint,
                )
            )
        if turn.timestamp:
            prev_ts = turn.timestamp
    return out


DETECTORS: list[Callable[[Session, Config], list[Finding]]] = [
    redundant_reads,
    oversized_outputs,
    repeated_calls,
    cache_misses,
]


def run_all(session: Session, cfg: Config | None = None) -> list[Finding]:
    cfg = cfg or Config()
    findings: list[Finding] = []
    for det in DETECTORS:
        findings.extend(det(session, cfg))
    return sorted(findings, key=lambda f: f.tokens + f.carried, reverse=True)
