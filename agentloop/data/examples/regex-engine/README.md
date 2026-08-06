# regex-engine

Held-out oracle with adversarial inputs.

## What it teaches

The classic "the agent overfits to your examples" failure. The goal is a regex
matcher with 25+ adversarial cases (invalid patterns, anchors, empty inputs,
backtracking traps). Only 3 cases are shown to the agent; the other 22 are
held-out and sealed — a solution that only handles the visible cases fails.

## Oracle pattern

`agentloop-oracle record` captures Python's `re` as the trusted reference, then
`agentloop-oracle grade` runs the agent's `regex_matcher.py` on every case and
demands a perfect held-out score.

## Run it

```bash
agentloop --init --example regex-engine
agentloop --verify "bash verify.sh"
```

Expected runtime: ~1–3 minutes. Expected cost: < $0.10.
