# rpn-calculator

tags: property-based

A reverse-Polish-notation integer calculator verified with **property-based
testing**: a seeded generator emits pairs of RPN expressions that are
algebraically guaranteed to evaluate to the same integer (commutativity,
associativity, distributivity, identity laws), and the verifier asserts the
candidate's outputs agree — with no reference implementation and no expected
values. **The invariant IS the oracle.**

## How it follows the checklist

- **Resolves the sandbox robustly** — honors `AGENTLOOP_SANDBOX` first, then
  walks up to the nearest ancestor containing a `sandbox/` dir; exits 2 with a
  fix-it message if neither resolves.
- **Exit 0 means *correct*** — any violated invariant, wrong line count,
  crash, or edge-case mismatch exits 1; a missing candidate exits 2.
- **No secrets** — script and fixtures contain nothing sensitive.
- **Deterministic** — the RNG is seeded (`1337`), no network, no clock.
- **Never mutates the sandbox** — the candidate only reads stdin; fixtures
  live in memory and `/tmp`-free heredocs.
- **Adversarial cases** — ~80 algebraically-equal expression pairs (the
  `a 0 -` and `a 1 /` identities specifically expose reversed operand order),
  plus fixed edge cases: division by zero, stack underflow, malformed tokens,
  leftover operands, empty input, and blank-line skipping.

## The gotcha this catches

An evaluator that pops operands in the wrong order (computing `a - b` where
`b - a` is meant) sails through every commutative and associative check — and
even the edge cases that only involve `+` and `*` — but violates the
`a 0 - ≡ a` and `a 1 / ≡ a` identities instantly. A solution that floors
instead of truncating division fails the negative-division edge cases
(`-7 2 /` must be `-3`, not `-4`). Property-based testing catches both
without ever listing an expected answer.

## Use it

Copy `verify.sh` + `goal.txt` next to your project's `sandbox/` directory,
then:

```bash
agentloop --verify "bash verify.sh"
```

Expected runtime: < 10 seconds. Expected cost: $0.
