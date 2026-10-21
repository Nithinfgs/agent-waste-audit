from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentwaste.cli import main
from agentwaste.detectors import Config, run_all
from agentwaste.parser import ParseError, discover, parse_session
from agentwaste.report import SessionReport, redact

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "sample_session.jsonl"


def kinds(path: Path) -> list[str]:
    return [f.kind for f in run_all(parse_session(path))]


def write(tmp_path: Path, records: list[dict | str]) -> Path:
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in records) + "\n")
    return p


def asst(
    i: int, calls: list[tuple[str, str, dict]], cr: int = 100, cc: int = 100, ts: str | None = None
) -> dict:
    rec = {
        "type": "assistant",
        "message": {
            "id": f"m{i}",
            "content": [{"type": "tool_use", "id": c, "name": n, "input": inp} for c, n, inp in calls],
            "usage": {
                "input_tokens": 1,
                "cache_read_input_tokens": cr,
                "cache_creation_input_tokens": cc,
                "output_tokens": 5,
            },
        },
    }
    if ts:
        rec["timestamp"] = ts
    return rec


def res(cid: str, text: str, err: bool = False) -> dict:
    return {
        "type": "user",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": cid, "content": text, "is_error": err}]
        },
    }


def test_sample_detects_every_pattern() -> None:
    found = set(kinds(SAMPLE))
    assert {"redundant_read", "oversized_output", "retry_loop", "repeated_call", "cache_expiry"} <= found


def test_sample_redundant_read_only_counts_unchanged_file() -> None:
    session = parse_session(SAMPLE)
    reads = [f for f in run_all(session) if f.kind == "redundant_read"]
    # utils.py second read (unchanged) and server.py second read; the post-edit read is legitimate
    assert sorted(f.summary.split()[0] for f in reads) == ["/app/server.py", "/app/utils.py"]


def test_retry_loop_counts_repeats_after_first() -> None:
    f = next(f for f in run_all(parse_session(SAMPLE)) if f.kind == "retry_loop")
    assert "3x" in f.summary
    assert f.tokens == 2 * (len("ModuleNotFoundError: no module 'foo'") // 4)


def test_edit_between_reads_clears_redundancy(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        [
            asst(0, [("a", "Read", {"file_path": "f"})]),
            res("a", "one"),
            asst(1, [("b", "Edit", {"file_path": "f"})]),
            res("b", "ok"),
            asst(2, [("c", "Read", {"file_path": "f"})]),
            res("c", "one"),
        ],
    )
    assert "redundant_read" not in kinds(p)


def test_different_ranges_are_not_redundant(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        [
            asst(0, [("a", "Read", {"file_path": "f", "offset": 0, "limit": 10})]),
            res("a", "x"),
            asst(1, [("b", "Read", {"file_path": "f", "offset": 10, "limit": 10})]),
            res("b", "x"),
        ],
    )
    assert kinds(p) == []


def test_two_identical_failures_are_below_threshold(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        [
            asst(0, [("a", "Bash", {"command": "x"})]),
            res("a", "e", True),
            asst(1, [("b", "Bash", {"command": "x"})]),
            res("b", "e", True),
        ],
    )
    assert kinds(p) == []


def test_cache_miss_without_idle_gap_counts_as_avoidable(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        [
            asst(0, [], 0, 50_000, "2026-01-01T00:00:00Z"),
            asst(1, [], 0, 50_000, "2026-01-01T00:00:30Z"),
        ],
    )
    f = run_all(parse_session(p))
    assert [x.kind for x in f] == ["cache_miss"]
    assert f[0].tokens == 50_000


def test_idle_gap_cache_expiry_is_not_counted(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        [
            asst(0, [], 0, 50_000, "2026-01-01T00:00:00Z"),
            asst(1, [], 0, 50_000, "2026-01-01T01:00:00Z"),
        ],
    )
    f = run_all(parse_session(p))
    assert f[0].kind == "cache_expiry" and f[0].tokens == 0


def test_oversized_threshold_is_configurable(tmp_path: Path) -> None:
    p = write(tmp_path, [asst(0, [("a", "Bash", {"command": "ls"})]), res("a", "y" * 5000)])
    s = parse_session(p)
    assert run_all(s, Config(oversized_chars=1000))[0].kind == "oversized_output"
    assert run_all(s, Config(oversized_chars=10_000)) == []


def test_split_assistant_message_counts_usage_once(tmp_path: Path) -> None:
    a = asst(0, [("a", "Bash", {"command": "ls"})])
    b = asst(0, [("b", "Bash", {"command": "pwd"})])  # same message id, second content block line
    s = parse_session(write(tmp_path, [a, b]))
    assert len(s.turns) == 1 and len(s.calls) == 2


def test_malformed_lines_and_sidechain_are_tolerated(tmp_path: Path) -> None:
    side = asst(9, [("z", "Bash", {"command": "q"})])
    side["isSidechain"] = True
    s = parse_session(write(tmp_path, ["{not json", "[1,2]", side, asst(0, [])]))
    assert s.skipped_lines == 2
    assert len(s.turns) == 1 and s.calls == []


def test_array_tool_result_content_is_measured(tmp_path: Path) -> None:
    r = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "a",
                    "content": [{"type": "text", "text": "abcd"}, {"type": "image", "source": {}}],
                }
            ]
        },
    }
    s = parse_session(write(tmp_path, [asst(0, [("a", "Bash", {})]), r]))
    assert s.calls[0].result_chars == 4


def test_discover_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ParseError):
        discover([tmp_path / "nope"])


def test_redact_masks_secrets() -> None:
    out = redact("curl -H 'Bearer abcdefghijklmnop' sk-abcdefghijklmnopqrstuv token=hunter2")
    assert "abcdefghijklmnop" not in out and "hunter2" not in out and "sk-abc" not in out


def test_cli_json_and_fail_over(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(SAMPLE), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["tool_calls"] == 13 and data[0]["avoidable_tokens"] > 0
    assert main([str(SAMPLE), "--fail-over", "1"]) == 1
    assert main([str(SAMPLE), "--fail-over", "99"]) == 0


def test_cli_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "missing")]) == 2
    assert main([str(SAMPLE), "--fail-over", "150"]) == 2
    empty = tmp_path / "e.jsonl"
    empty.write_text("")
    assert main([str(empty)]) == 2
    capsys.readouterr()


def test_report_ratio_zero_when_no_tokens(tmp_path: Path) -> None:
    s = parse_session(write(tmp_path, [asst(0, [], 0, 0)]))
    s.turns[0].usage.input = s.turns[0].usage.output = 0
    assert SessionReport(s, []).ratio == 0.0


def test_module_entrypoint_runs() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "agentwaste", str(SAMPLE), "--top", "2"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "avoidable" in out.stdout


def test_oversized_reread_is_not_double_counted() -> None:
    findings = run_all(parse_session(SAMPLE))
    big_reads = [f for f in findings if "/app/server.py" in f.summary]
    assert sorted(f.kind for f in big_reads) == ["oversized_output", "redundant_read"]
