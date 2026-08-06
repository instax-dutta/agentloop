# Contributing

Thanks for helping make the verification oracle trustworthy.

## Development setup

```bash
git clone https://github.com/instax-dutta/agentloop.git && cd agentloop
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

## Tests

Deterministic, no LLM required:

```bash
python3 test_oracle.py
python3 test_loop.py
python3 test_cost.py
python3 test_parallel.py
python3 test_telemetry.py
```

All must pass before opening a PR. CI runs the same commands on Linux
(Python 3.10 / 3.12 / 3.13) plus `mypy --strict agentloop/` and `ruff`.

## The oracle contract

1. `VERIFY_CMD` runs with `cwd` = project root (never the sandbox).
2. Exit `0` means the work is **correct** — not merely that it runs.
3. The agent must never be able to edit the verifier or read held-out cases.
4. Prefer held-out grading over baking exact cases into a script.
5. `ORACLE_SEAL` is available to the verifier process only.

## Issue triage SLA

Maintainers respond to issues within **48 hours**. New issues are
auto-labelled by the triage workflow (isolation / cost / benchmark / oracle /
examples).

## Pull requests

- One focused change per PR, conventional-commit titles
  (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Version bumps happen automatically via Release Please on merge.
- Update README / docs if you change user-facing behaviour.
