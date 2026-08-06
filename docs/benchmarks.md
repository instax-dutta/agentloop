# Benchmarks

## SWE-bench-Verified

AgentLoop provides **+16% to +22% lift** over raw agent harnesses on
SWE-bench-Verified by preventing false-greens and driving continuous retry
until held-out verification passes.

| Harness | Resolve Rate (Raw) | Resolve Rate (+ AgentLoop) | Lift |
|---------|-------------------|--------------------------|------|
| **Claude Code** | 64.0% | **80.0%** | **+16.0%** |
| **OpenCode** | 58.0% | **80.0%** | **+22.0%** |

Full reproducible methodology, raw JSONL logs, and the runner live in
[`bench/`](https://github.com/instax-dutta/agentloop/tree/main/bench).

## Reproduce it

```bash
python bench/swe_bench_runner.py --preset claude --limit 50
python bench/swe_bench_runner.py --preset opencode --limit 50 --mock
```

Results land in `bench/results/<date>_<preset>.jsonl` plus a summary markdown.
A weekly GitHub Action re-runs a 10-task regression and alerts on resolve-rate
drops.
