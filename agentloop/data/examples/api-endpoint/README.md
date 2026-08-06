# api-endpoint

Integration oracle (HTTP).

## What it teaches

How to verify an agent that builds *something that runs*: boot it, hit it,
assert the contract. The verifier starts the server, waits for `/health`, then
checks JSON bodies and 404 behaviour over real HTTP. This version is stdlib-only
(`http.server` + `urllib`) so it works in any sandbox; in production you'd swap
in `pytest + httpx` against a FastAPI app with the same assertions.

## Oracle pattern

Subprocess lifecycle + HTTP contract assertions. Copy this pattern for any
"build a service / endpoint / worker" goal.

## Run it

```bash
agentloop --init --example api-endpoint
agentloop --verify "bash verify.sh"
```

Expected runtime: ~2–4 minutes. Expected cost: < $0.15.
