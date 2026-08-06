# Community Verifiers

A growing library of copy-paste-able `verify.sh` patterns submitted by the
community, tagged by language / framework / oracle pattern. This is the
network effect: users share verifiers → more users → more verifiers.

## How to contribute

1. Copy the structure from any [bundled example](../examples/) — it needs at
   least a `verify.sh`, a `goal.txt`, and a one-line `README.md`.
2. Tag it: add a `tags:` line in the README, e.g.
   `tags: python, cli, held-out-oracle`.
3. Open a PR to `community-verifiers/<name>/`.

## Verifier checklist (required for merge)

- [ ] Runs with `cwd` = project root (uses `$SANDBOX` or resolves
      `../..`-style paths robustly).
- [ ] Exit 0 means *correct*, not merely "runs".
- [ ] No secrets in the script or its inputs.
- [ ] Deterministic: same inputs → same result, no network calls, no clock
      dependence.
- [ ] Doesn't mutate the agent's sandbox (works against a copy or read-only).
- [ ] Has at least one adversarial case (the point is defeating overfitting).

## Tag reference

| Tag | Pattern |
|-----|---------|
| `fixed-cases` | Fixed test cases with expected outputs |
| `held-out-oracle` | Sealed reference + grade on unseen inputs |
| `property-based` | Generated random inputs |
| `golden-files` | Byte-exact expected output |
| `behavior-equivalence` | Run both, compare results |
| `exit-code` | Linter / type-checker exit codes |
| `integration` | Boot a service and probe it |
| `fixture` | Real fixture environment + post-conditions |

## Contributed verifiers

- [`filename-sanitizer/`](filename-sanitizer/) — batch-rename a fixture tree and
  assert post-conditions (`tags: fixture`). First contribution — use it as the
  template for yours.
