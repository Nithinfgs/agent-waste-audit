# Contributing

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

- New detector: add a function `(Session, Config) -> list[Finding]` to `src/agentwaste/detectors.py`, register it in `DETECTORS`, and add a test using a small synthetic transcript (see `tests/`).
- Never commit real transcripts; they contain your prompts and file contents. `examples/make_sample.py` generates the synthetic one.
- Support for another agent's transcript format belongs in a new parser that returns `Session`.
