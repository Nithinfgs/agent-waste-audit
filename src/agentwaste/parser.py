"""Parse Claude Code JSONL transcripts into a :class:`Session`."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from .model import Call, Session, Turn, Usage


class ParseError(Exception):
    """Raised when a file cannot be read as a transcript at all."""


def default_roots() -> list[Path]:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(base) if base else Path.home() / ".claude"
    return [root / "projects"]


def discover(paths: list[Path]) -> list[Path]:
    """Expand files/directories into a sorted (newest first) list of ``.jsonl`` files."""
    found: list[Path] = []
    for p in paths:
        if p.is_file():
            found.append(p)
        elif p.is_dir():
            found.extend(q for q in p.rglob("*.jsonl") if q.is_file())
        else:
            raise ParseError(f"path does not exist: {p}")
    return sorted(set(found), key=lambda f: f.stat().st_mtime, reverse=True)


def _ts(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _result_text_len(content: Any) -> tuple[int, str]:
    """Return (character count, content hash) of a tool_result payload."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        text = "\n".join(parts)
    else:
        text = ""
    return len(text), hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


def _records(path: Path) -> Iterator[dict[str, Any] | None]:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    yield None
                    continue
                yield obj if isinstance(obj, dict) else None
    except OSError as exc:
        raise ParseError(f"cannot read {path}: {exc}") from exc


def parse_session(path: Path) -> Session:
    session = Session(path=str(path), session_id=path.stem)
    calls_by_id: dict[str, Call] = {}
    turn_by_msg: dict[str, Turn] = {}

    for rec in _records(path):
        if rec is None:
            session.skipped_lines += 1
            continue
        if rec.get("isSidechain"):
            continue  # sub-agent traffic is billed separately; not analysed in v0.1
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        rtype = rec.get("type")

        if rtype == "assistant":
            msg_id = str(msg.get("id") or rec.get("uuid") or len(session.turns))
            turn = turn_by_msg.get(msg_id)
            if turn is None:
                u = msg.get("usage") or {}
                turn = Turn(
                    index=len(session.turns),
                    usage=Usage(
                        input=int(u.get("input_tokens") or 0),
                        cache_creation=int(u.get("cache_creation_input_tokens") or 0),
                        cache_read=int(u.get("cache_read_input_tokens") or 0),
                        output=int(u.get("output_tokens") or 0),
                    ),
                    timestamp=_ts(rec.get("timestamp")),
                )
                turn_by_msg[msg_id] = turn
                session.turns.append(turn)
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    inp = block.get("input")
                    call = Call(
                        id=str(block.get("id")),
                        name=str(block.get("name")),
                        input=inp if isinstance(inp, dict) else {},
                        turn=turn.index,
                    )
                    calls_by_id[call.id] = call
                    session.calls.append(call)

        elif rtype == "user":
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                target = calls_by_id.get(str(block.get("tool_use_id")))
                if target is None:
                    continue
                target.result_chars, target.result_hash = _result_text_len(block.get("content"))
                target.is_error = bool(block.get("is_error"))
                target.has_result = True
    return session
