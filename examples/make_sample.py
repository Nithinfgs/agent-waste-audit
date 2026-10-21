"""Generate examples/sample_session.jsonl: a synthetic transcript with known waste patterns.

Run:  python examples/make_sample.py
The data is fabricated for demonstration; it contains no real session content.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).with_name("sample_session.jsonl")
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

records: list[dict] = []
n_msg = 0


def turn(calls, seconds, cache_read, cache_creation, output=300):
    """Append one assistant message with the given tool calls."""
    global n_msg
    n_msg += 1
    records.append(
        {
            "type": "assistant",
            "timestamp": (T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
            "message": {
                "id": f"msg_{n_msg}",
                "content": [
                    {"type": "tool_use", "id": cid, "name": name, "input": inp}
                    for cid, name, inp, _, _ in calls
                ],
                "usage": {
                    "input_tokens": 3,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_creation,
                    "output_tokens": output,
                },
            },
        }
    )
    records.append(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": cid, "content": text, "is_error": err}
                    for cid, _, _, text, err in calls
                ]
            },
        }
    )


big = "def handler():\n    pass\n" * 1500  # ~34k chars
small = "x = 1\n" * 40

turn([("t1", "Read", {"file_path": "/app/server.py"}, big, False)], 0, 0, 9000)
turn(
    [("t2", "Bash", {"command": "pytest -x"}, "ModuleNotFoundError: no module 'foo'", True)], 20, 9000, 12000
)
turn([("t3", "Bash", {"command": "pytest -x"}, "ModuleNotFoundError: no module 'foo'", True)], 40, 21000, 500)
turn([("t4", "Bash", {"command": "pytest -x"}, "ModuleNotFoundError: no module 'foo'", True)], 60, 21500, 500)
turn([("t5", "Read", {"file_path": "/app/utils.py"}, small, False)], 80, 22000, 800)
turn([("t6", "Read", {"file_path": "/app/utils.py"}, small, False)], 100, 22800, 300)
turn(
    [("t7", "Edit", {"file_path": "/app/utils.py", "old_string": "x", "new_string": "y"}, "ok", False)],
    120,
    23100,
    300,
)
turn([("t8", "Read", {"file_path": "/app/utils.py"}, small.replace("1", "2"), False)], 140, 23400, 300)
turn([("t9", "Bash", {"command": "git status"}, "clean", False)], 160, 23700, 200)
turn([("t10", "Bash", {"command": "git status"}, "clean", False)], 180, 23900, 200)
turn([("t11", "Bash", {"command": "git status"}, "clean", False)], 200, 24100, 200)
turn([("t12", "Read", {"file_path": "/app/server.py"}, big, False)], 1000, 0, 26000)
turn([("t13", "Bash", {"command": "echo done"}, "done", False)], 1020, 26000, 200)

OUT.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(records)} records)")
