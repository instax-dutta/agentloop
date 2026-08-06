# git-history-rewriter

Fixture-based oracle with real git repos.

## What it teaches

Building a *fixture* — a real, deterministic environment the agent cannot fake
— and asserting on its end state. Here the verifier constructs a multi-author
git repo, runs the agent's rewriter, and checks authors, topology, and file
contents. Fixture oracles are the right pattern whenever the task mutates a
system (git history, databases, package trees) rather than producing one file.

## Oracle pattern

Fixture construction + post-condition assertions. Note the agent's tool runs
against a COPY at `/tmp` — never the project repo itself.

## Run it

```bash
agentloop --init --example git-history-rewriter
agentloop --verify "bash verify.sh"
```

Expected runtime: ~2–4 minutes. Expected cost: < $0.15.
