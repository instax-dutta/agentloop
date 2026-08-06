# Example Gallery

Ten copy-paste-able verifier samples — plus three community-submitted
verifiers at the bottom. Each teaches a different **oracle
pattern** — the more patterns you know, the more tasks you can make
verifiable. Every example has `goal.txt` (the task) and `verify.sh` (the
oracle) and runs cleanly with:

```bash
agentloop --init --example <name>
agentloop --verify "bash verify.sh"
```

See the full list any time with `agentloop --examples`.

---

## Starter

### `tax-demo` — fixed test cases (the default scaffold)

- **Oracle pattern:** fixed test cases in bash with exact-output comparison.
- **What it teaches:** the full loop on a realistic domain (US tax brackets,
  capital gains) where the oracle checks *computed values*, not "it runs".
- **Runtime:** ~1–2 min · **Cost:** < $0.10.

### `json-linter` — fixed test cases, generated per iteration

- **Oracle pattern:** temporary test files (`/tmp/valid.json`,
  `/tmp/invalid.json`) with output assertions.
- **What it teaches:** a tiny, well-defined contract; the cheapest possible
  honest oracle.
- **Runtime:** ~1–2 min · **Cost:** < $0.10.

---

## Held-out / anti-overfitting

### `regex-engine` — held-out oracle with adversarial inputs

- **Oracle pattern:** `agentloop-oracle record` + `grade` with 25 adversarial
  cases (invalid patterns, anchors, empty inputs). Only 3 are visible; the
  agent must be correct on the 22 it never saw.
- **What it teaches:** defeating "overfit to my examples" solutions. If your
  task has edge cases an agent can dodge, this is the pattern.
- **Runtime:** ~1–3 min · **Cost:** < $0.10.

### `csv-sorter` — held-out oracle with property-based testing

- **Oracle pattern:** 40 randomly generated batches — including deliberate
  duplicate ids to probe sorting *stability* — recorded against a reference
  and graded held-out.
- **What it teaches:** property-based input generation for anything with a
  deterministic correct answer.
- **Runtime:** ~1–3 min · **Cost:** < $0.10.

### `refactor-regression` — held-out oracle for behavior-preserving refactors

- **Oracle pattern:** `gen` → `record` (3 visible / 197 held-out) → `grade`.
  The agent refactors code and must match the reference on unseen inputs.
- **What it teaches:** the pattern AgentLoop exists for — "make it better but
  don't change behaviour".
- **Runtime:** ~2–4 min · **Cost:** < $0.15.

---

## Output equivalence

### `markdown-to-html` — golden-file comparison

- **Oracle pattern:** 8 golden cases compared character-for-character,
  including HTML escaping.
- **What it teaches:** the zero-logic oracle for anything with a defined
  output format (compilers, formatters, converters).
- **Runtime:** ~1–3 min · **Cost:** < $0.10.

### `sql-query-rewriter` — behavior-equivalence oracle

- **Oracle pattern:** runs the original and the rewritten query against a real
  SQLite database and compares result sets row-for-row.
- **What it teaches:** the strongest oracle there is — verify *behaviour*, not
  *appearance*. Copy it for any rewriter / transpiler / refactor.
- **Runtime:** ~1–3 min · **Cost:** < $0.10.

---

## Tooling / integration

### `python-type-checker` — exit-code oracle

- **Oracle pattern:** `python3 -m py_compile` always; `mypy` when installed;
  plus a tiny behaviour spot-check.
- **What it teaches:** the cheapest honest oracle — the linter/type-checker IS
  the oracle. Use for "make this pass lint/type-check" tasks.
- **Runtime:** ~1–2 min · **Cost:** < $0.10.

### `api-endpoint` — integration oracle over HTTP

- **Oracle pattern:** boots the agent's server, waits for `/health`, probes
  JSON bodies and 404s over real HTTP, kills the server. Stdlib-only here;
  swap in `pytest + httpx` for a FastAPI app in production.
- **What it teaches:** verifying anything that *runs as a service*.
- **Runtime:** ~2–4 min · **Cost:** < $0.15.

### `git-history-rewriter` — fixture-based oracle with real git repos

- **Oracle pattern:** builds a real multi-author fixture repo, runs the agent's
  tool against a copy at `/tmp`, then asserts authors, topology, and contents.
- **What it teaches:** fixture oracles for tasks that *mutate a system* rather
  than produce one file.
- **Runtime:** ~2–4 min · **Cost:** < $0.15.

---

## Choosing a pattern

| Task shape | Pattern | Example |
|-----------|---------|---------|
| Small, well-defined output | Fixed test cases | `json-linter`, `tax-demo` |
| Many edge cases / overfitting risk | Held-out oracle | `regex-engine` |
| Random inputs possible | Property-based + held-out | `csv-sorter` |
| "Keep behaviour identical" | Behavior-equivalence | `sql-query-rewriter`, `refactor-regression` |
| Defined output format | Golden files | `markdown-to-html` |
| "Make it pass the linter" | Exit-code oracle | `python-type-checker` |
| Builds a service | Integration (HTTP) | `api-endpoint` |
| Mutates a system | Fixture + post-conditions | `git-history-rewriter` |

---

## Community verifiers

Community-submitted `verify.sh` patterns — each CI-checked in *both*
directions: a seeded correct `solution/` must pass, and a seeded incorrect
`bad-solution/` must fail. Copy any as the template for your own
contribution.

### `filename-sanitizer` — fixture + post-conditions (`tags: fixture`)

- **Oracle pattern:** builds a realistic directory tree in a temp dir, runs
  the agent's script against a *copy*, and asserts the exact post-conditions
  (hidden files untouched, collisions suffixed, deep nesting renamed
  bottom-up, no spurious files).
- **What it teaches:** verifying tasks that *mutate* a system — assert the
  resulting state, don't eyeball the code.
- **Runtime:** < 5 s · **Cost:** $0.

### `uniq-reimplementation` — behavior-equivalence (`tags: behavior-equivalence`)

- **Oracle pattern:** a seeded RNG generates random line batches (duplicate
  runs, blank lines, tabs, trailing spaces, unicode) and the candidate's
  stdout is compared byte-for-byte against a reference — with and without the
  `-c` count flag.
- **What it teaches:** reimplementing a CLI — the reference *defines* the
  spec, so correctness is proven by equivalence, not by example outputs.
- **Runtime:** < 10 s · **Cost:** $0.

### `roman-numeral-converter` — held-out oracle (`tags: held-out-oracle`)

- **Oracle pattern:** records a sealed reference on ~80 generated inputs
  (only 3 visible), then grades the candidate on *every* input.
- **What it teaches:** the anti-overfitting moat — an agent that memorizes
  the 3 visible cases fails every held-out input, and `grade` reports the
  exact first divergence back into the loop.
- **Runtime:** < 15 s · **Cost:** $0 (requires `agentloop-cli`).

### `rpn-calculator` — property-based invariants (`tags: property-based`)

- **Oracle pattern:** a seeded generator emits pairs of RPN expressions that
  are algebraically guaranteed to evaluate to the same integer
  (commutativity, associativity, distributivity, identity laws); the
  candidate's outputs must agree on both sides — no reference
  implementation, no expected values.
- **What it teaches:** the invariant *is* the oracle — ideal for anything
  with laws that must hold (calculators, validators, algebraic transforms).
- **Runtime:** < 10 s · **Cost:** $0.

Built a verifier worth sharing? Add it to the
[community-verifiers gallery](../community-verifiers/) — the merge checklist
and tag taxonomy (held-out, golden-files, fixture, …) live in
[CONTRIBUTING.md](../CONTRIBUTING.md).
