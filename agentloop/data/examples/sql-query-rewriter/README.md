# sql-query-rewriter

Behavior-equivalence oracle.

## What it teaches

The strongest oracle pattern there is: instead of checking *how* the output
looks, run the output and compare *behavior*. The verifier builds a SQLite
fixture, executes the original query and the agent's rewritten query, and
compares result sets row-for-row. Any rewrite that changes results fails —
even if it looks more elegant.

## Oracle pattern

Embedded Python checker using stdlib `sqlite3`. 8 queries covering joins,
aggregates, `IN`, `BETWEEN`, and ordering. This is the pattern to copy for
any "behavior-preserving" task (refactors, rewriters, transpilers).

## Run it

```bash
agentloop --init --example sql-query-rewriter
agentloop --verify "bash verify.sh"
```

Expected runtime: ~1–3 minutes. Expected cost: < $0.10.
