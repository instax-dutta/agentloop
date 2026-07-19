# Contributing to AgentLoop

Thanks for helping make the verification oracle trustworthy.

## Development setup

```bash
git clone <repo> agentloop && cd agentloop
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # never commit .env
```

## Tests

Deterministic, no LLM required:

```bash
python3 test_oracle.py
python3 test_loop.py
```

Both must pass before opening a PR. CI runs the same commands on Linux.

## The oracle contract

AgentLoop’s product is the **verification oracle**, not the agent:

1. `VERIFY_CMD` runs with `cwd` = project root (never the sandbox).
2. Exit `0` means the work is **correct** — not merely that it runs.
3. The agent must never be able to edit the verifier or read held-out cases.
4. Prefer held-out grading (`oracle.py record` / `grade`) over baking exact cases into a script the agent can reverse-engineer from failure messages alone.
5. `ORACLE_SEAL` is available to the verifier process only; it is stripped from the agent environment.

When changing `safe_env`, `run_verify`, or the loop’s DONE gate, add or update tests in `test_oracle.py` / `test_loop.py`.

## Code style

- Python 3.10+
- Keep the core surface small: `agentloop.py` (orchestrator) + `oracle.py` (gate)
- Prefer clear control flow over cleverness; dead code after `break` is a bug
- Do not log secrets (API keys, seals)

## Pull requests

- One focused change per PR
- Update `README.md` / `ISSUES.md` if you change user-facing behavior
- Bump version in `agentloop.py` (`__version__`) and `pyproject.toml` together when releasing
