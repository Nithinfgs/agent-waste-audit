"""Turn analysed sessions into text or JSON output."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .model import Finding, Session

_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|(?i:(?:token|secret|password|apikey|api_key)=)\S+|Bearer\s+\S{12,})"
)


def redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


@dataclass
class SessionReport:
    session: Session
    findings: list[Finding]

    @property
    def avoidable(self) -> int:
        return sum(f.tokens for f in self.findings)

    @property
    def carried(self) -> int:
        return sum(f.carried for f in self.findings)

    @property
    def ratio(self) -> float:
        total = self.session.total_new_tokens
        return self.avoidable / total if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        s = self.session
        return {
            "session": s.session_id,
            "path": s.path,
            "turns": len(s.turns),
            "tool_calls": len(s.calls),
            "new_tokens": s.total_new_tokens,
            "cache_read_tokens": s.total_cache_read,
            "avoidable_tokens": self.avoidable,
            "avoidable_ratio": round(self.ratio, 4),
            "carried_tokens": self.carried,
            "skipped_lines": s.skipped_lines,
            "findings": [{**asdict(f), "summary": redact(f.summary)} for f in self.findings],
        }


def _bar(ratio: float, width: int = 20) -> str:
    filled = min(width, round(ratio * width))
    return "#" * filled + "." * (width - filled)


def render_text(reports: list[SessionReport], top: int = 8) -> str:
    lines: list[str] = []
    for r in reports:
        s = r.session
        lines.append(f"Session {s.session_id}")
        lines.append(
            f"  {len(s.turns)} turns, {len(s.calls)} tool calls, "
            f"{s.total_new_tokens:,} new tokens, {s.total_cache_read:,} cache-read tokens"
        )
        lines.append(f"  avoidable ~{r.avoidable:,} tokens  [{_bar(r.ratio)}] {r.ratio:.1%} of new tokens")
        if r.carried:
            lines.append(f"  plus ~{r.carried:,} tokens re-read from cache on later turns")
        if s.skipped_lines:
            lines.append(f"  note: {s.skipped_lines} unparseable line(s) skipped")
        if not r.findings:
            lines.append("  no waste patterns found")
        for f in r.findings[:top]:
            lines.append(f"  - [{f.kind}] {redact(f.summary)}")
            lines.append(f"      ~{f.tokens:,} tokens (+{f.carried:,} carried) - {f.detail}")
            if f.hint:
                lines.append(f"      tip: {f.hint}")
        hidden = len(r.findings) - top
        if hidden > 0:
            lines.append(f"  ... {hidden} more (use --top or --json)")
        lines.append("")
    if len(reports) > 1:
        total = sum(r.avoidable for r in reports)
        new = sum(r.session.total_new_tokens for r in reports)
        pct = total / new if new else 0.0
        lines.append(
            f"TOTAL: {len(reports)} sessions, ~{total:,} avoidable of {new:,} new tokens ({pct:.1%})"
        )
    lines.append("Token counts for tool results are estimated at 4 characters/token.")
    return "\n".join(lines)
