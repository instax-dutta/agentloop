# SWE-bench-Verified Benchmark Results

This directory contains the reproducible benchmark suite and results for AgentLoop evaluated on 50 tasks from [SWE-bench-Verified](https://github.com/princeton-nlp/SWE-bench).

## Summary Comparison

| Harness | Resolve Rate (Raw) | Resolve Rate (+ AgentLoop) | Lift | Cost / Task | Time / Task |
|---------|-------------------|--------------------------|------|-------------|-------------|
| **Claude Code** | 64.0% | **80.0%** | **+16.0%** | $0.38 | 42s |
| **OpenCode** | 58.0% | **80.0%** | **+22.0%** | $0.25 | 38s |

---

## Methodology

1. **Dataset**: 50 verified task instances from SWE-bench-Verified.
2. **Environment**: Isolated sandbox container per task with `--docker`.
3. **Verification**: Held-out oracle evaluation using `oracle.py record` and `oracle.py grade`.
4. **Limits**: Max 10 iterations per task, $5.00 budget cap, 1800s wall-clock limit.

## Raw Results

- [Claude Code Raw JSONL Log](results/2026-07-27_claude.jsonl)
- [OpenCode Raw JSONL Log](results/2026-07-27_opencode.jsonl)
