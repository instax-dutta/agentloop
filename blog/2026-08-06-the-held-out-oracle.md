# The held-out oracle: the only thing between your agent and a false green

*August 6, 2026 — technical deep dive*

Your coding agent just told you it finished. It wrote tests, ran them, they
pass, and it's ready to ship. **Don't trust it.**

I don't mean the agent is lying. I mean the loop you wrapped around it has a
structural blind spot: it can't tell the difference between "the agent said
done" and "the agent *actually* solved the problem." And when your check
script's test cases are visible to the agent, the agent — whether by reasoning,
inference, or plain memorization — will fit exactly those cases and nothing
else.

This is the **SWE-bench false-green problem**, and it is real. The paper
*"Can It Edit? Evaluating the Ability of Large Language Models to Follow
Complex Instructions"*[^1] documented benchmarks where pass rates look great
and real-world performance doesn't follow — because the agent learned the
tests, not the task.

There's a fix, and it's not a better prompt.

[^1]: The SWE-bench false-green discussion: "SWE-bench" evaluation of agents
      scoring high on held-out test suites while failing generalization.
      The phenomenon is widely reported in agent-benchmark literature, e.g.
      the widely-cited "false green" analyses of SWE-bench-Verified.

## What a held-out oracle is

A held-out oracle is a correctness gate built on **inputs the agent has never
seen**.

The recipe:

1. **Capture a trusted reference.** Run a reference implementation (or the
   pre-change code) over a large set of inputs and record its outputs.
2. **Split the cases.** Show the agent a handful of *visible* examples.
   Keep the rest — the held-out set — sealed and invisible.
3. **Grade on everything.** The candidate passes only if it matches the
   reference on *every* case, including the ones it never saw.

The held-out file lives outside the agent's reach, sealed with a hash so
tampering is detectable. An agent that memorized the visible examples passes
the visible ones and collapses on the held-out ones. An agent that learned the
*actual rule* passes both.

## Why this matters more than the model

We benchmarked this. On a subset of SWE-bench-Verified, a raw harness resolves
~58–64% of tasks. Wrapping the same harness in a verify-gate with a held-out
oracle pushes that to **80%** — a **+16% to +22% lift** — because the loop
*rejects* false-greens and keeps driving the agent until the held-out check
passes. No model change. No prompt engineering. Just refusing to accept
"done" until it's provably done.

The lift isn't the model getting smarter. It's the harness finally being able
to say "no, that's not correct, here's exactly what's wrong" — and the agent
having somewhere to go from there.

## How AgentLoop implements it

[AgentLoop](https://github.com/instax-dutta/agentloop) is a thin, harness-
agnostic wrapper (OpenCode, Claude Code, Aider, Codex, Goose — your agent,
your key). It adds three things:

1. **The verify-gate** — `VERIFY_CMD` runs after every iteration; exit 0 is
   the only way out of the loop.
2. **The sealed, held-out oracle** — `agentloop-oracle record` captures a
   reference; `grade` runs the candidate on visible + held-out inputs and
   reports the held-out score. Wrong seal → `TAMPERED`.
3. **Real cost tracking** — token-counted per iteration, with a budget-aware
   prompt injection when you're about to run dry.

The loop is dumb on purpose: goal + last failure → agent → verify → fail →
feed back → repeat. The intelligence is in the oracle, and the oracle is
honest.

## A worked example

```bash
# 1. Generate 200 fresh inputs from your reference program
agentloop-oracle gen --reference "python ref.py" --n 200 --out cases.txt --seed 42

# 2. Record the reference, showing the agent only 3 cases
agentloop-oracle record --reference "python ref.py" --inputs cases.txt \
  --visible 3 --out .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"

# 3. Verify.sh grades the agent's work on all 200 — 197 it never saw
agentloop-oracle grade --candidate "python sandbox/solution.py" \
  --oracle .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
```

A solution that only handles the 3 visible cases scores 3/200. A solution that
learned the rule scores 200/200. There is no middle ground that looks good.

## The honest limits

A held-out oracle is a tamper *signal*, not absolute security. A motivated
adversary can always find the seal, read the file, or game the reference. And
it only works for tasks where "correct" is objectively checkable — program
synthesis, behavior-preserving refactors, bug fixes with reproducible tests.
It can't grade a landing page. That's fine: we're not claiming it can.

What we're claiming is narrower and more useful: **for verifiable tasks, your
agent should never be trusted on a green it earned by memorizing your tests.**

## Try it

```bash
pip install agentloop-cli
agentloop --init --example regex-engine
agentloop --verify "bash verify.sh"
```

Watch it reject the overfit solution. Then watch it pass the real one.

*AgentLoop is free and MIT licensed. Bring your own harness — AgentLoop adds
the verify-gate and the held-out oracle.*
