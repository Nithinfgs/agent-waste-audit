"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .detectors import Config, run_all
from .parser import ParseError, default_roots, discover, parse_session
from .report import SessionReport, render_text


def _positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agentwaste",
        description="Find avoidable token waste in Claude Code session transcripts. Runs fully offline.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="transcript .jsonl files or directories (default: ~/.claude/projects)",
    )
    p.add_argument(
        "-n", "--limit", type=_positive, default=5, help="newest N sessions to analyse (default 5)"
    )
    p.add_argument("--top", type=_positive, default=8, help="findings shown per session (default 8)")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p.add_argument(
        "--oversized-chars",
        type=_positive,
        default=Config.oversized_chars,
        help="tool-result size that counts as oversized (default 20000)",
    )
    p.add_argument(
        "--fail-over",
        type=float,
        metavar="PCT",
        help="exit 1 if any session's avoidable share of new tokens exceeds PCT (0-100)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fail_over is not None and not 0 <= args.fail_over <= 100:
        print("error: --fail-over must be between 0 and 100", file=sys.stderr)
        return 2
    try:
        files = discover(args.paths or default_roots())
    except (ParseError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("error: no .jsonl transcripts found", file=sys.stderr)
        return 2

    cfg = Config(oversized_chars=args.oversized_chars)
    reports: list[SessionReport] = []
    for f in files[: args.limit]:
        try:
            session = parse_session(f)
        except ParseError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            continue
        if session.turns:
            reports.append(SessionReport(session, run_all(session, cfg)))
    if not reports:
        print("error: no analysable sessions (no assistant turns found)", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        print(render_text(reports, args.top))

    if args.fail_over is not None and any(r.ratio * 100 > args.fail_over for r in reports):
        return 1
    return 0
