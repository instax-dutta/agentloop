# AgentLoop

**Provable correctness for autonomous coding agents.**

A harness-agnostic verify-gate with a held-out oracle, so the agent can't fake
"done".

```bash
pip install agentloop-cli
agentloop "build a JSON linter" --verify "bash verify.sh"
```

Free. MIT licensed. Bring your own agent harness (OpenCode, Claude Code,
Aider, Codex, Goose) — AgentLoop adds the verify-gate and held-out oracle.

## Why AgentLoop

Coding agents are famous for stopping halfway and claiming they're done. A
naive loop can't tell "the agent said DONE" from "the work is actually
correct". AgentLoop's **verification oracle** is a correctness gate the agent
can't fake, edit, or overfit to:

```
   goal + feedback ──► your agent edits the sandbox ──► verification oracle
          ▲                                                   │
          └────────────── (fail) ◄───────────────────────────┘
                         (pass) ──► DONE  (and a sealed oracle agrees)
```

- **Continuity** — loops until the goal is proven correct.
- **Held-out grading** — the agent is graded on inputs it has never seen,
  sealed against tampering.
- **Safety** — your API key never reaches the agent; work is git-checkpointed
  and crash-resumable.

## When to use it

Program synthesis · behavior-preserving refactoring · bug fixes with
reproducible tests.

See [Concepts](concepts.md), [Quickstart](quickstart.md), and the
[Example Gallery](EXAMPLES.md).
