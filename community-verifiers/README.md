# Community Verifiers

A growing library of copy-paste-able `verify.sh` patterns submitted by the
community, tagged by language / framework / oracle pattern. This is the
network effect: users share verifiers → more users → more verifiers.

## How to contribute

1. Copy the structure from any [bundled example](../examples/) — it needs a
   `verify.sh`, a `goal.txt`, a one-line `README.md`, a `solution/` directory
   containing a **correct** implementation of the task, and a `bad-solution/`
   directory containing a plausible-but-**incorrect** one that **mirrors
   `solution/` file-for-file** (same relative paths, so `verify.sh` actually
   runs it). CI seeds the sandbox from both.
2. Tag it: add a `tags:` line in the README, e.g.
   `tags: python, cli, held-out-oracle`.
3. Make sure `verify.sh` honors `AGENTLOOP_SANDBOX` (every worker and the CI
   check set it) and falls back to resolving the sandbox relative to the
   script.
4. Open a PR to `community-verifiers/<name>/`. CI runs
   [`check_verifiers.py`](check_verifiers.py), which proves both directions:
   it seeds the sandbox from your `solution/` and requires `verify.sh` to
   exit 0 (accepts correct code), then seeds from your `bad-solution/` and
   requires `verify.sh` to exit non-zero (rejects incorrect code). Verify
   locally with `python community-verifiers/check_verifiers.py` before
   opening the PR.

## Verifier checklist (required for merge)

- [ ] Resolves the sandbox robustly — honors `AGENTLOOP_SANDBOX`, `$SCRIPT_DIR`
      relative paths, and/or `./sandbox` from the project root. CI replays the
      verifier in a throwaway project root with all three layouts available.
- [ ] Exit 0 means *correct*, not merely "runs".
- [ ] No secrets in the script or its inputs.
- [ ] Deterministic: same inputs → same result, no network calls, no clock
      dependence.
- [ ] Doesn't mutate the agent's sandbox (works against a copy or read-only).
- [ ] Has at least one adversarial case (the point is defeating overfitting).
- [ ] Ships a `solution/` dir with a correct implementation — CI seeds the
      sandbox from it and fails if `verify.sh` doesn't exit 0.
- [ ] Ships a `bad-solution/` dir with a plausible-but-incorrect
      implementation that **mirrors `solution/` file-for-file** (same
      relative paths, so `verify.sh` genuinely runs it) — CI seeds the
      sandbox from it and fails if `verify.sh` doesn't exit 1. This is the
      adversarial check: a verifier that can't tell correct from incorrect is
      worthless.

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
  assert post-conditions (`tags: fixture`).
- [`uniq-reimplementation/`](uniq-reimplementation/) — reimplement the `uniq`
  CLI and prove it by byte-for-byte comparison against a reference on
  generated inputs (`tags: behavior-equivalence`).
- [`roman-numeral-converter/`](roman-numeral-converter/) — a bidirectional
  integer ↔ Roman-numeral converter graded by a sealed held-out oracle: only 3
  of ~80 generated cases are visible, and the candidate must pass them all
  (`tags: held-out-oracle`).

Use any as the template for yours — every verifier ships a `solution/` and a
`bad-solution/` dir that CI seeds and checks in both directions.
