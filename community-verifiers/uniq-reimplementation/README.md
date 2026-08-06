# uniq-reimplementation

tags: behavior-equivalence

Reimplement the `uniq` line-dedup CLI and prove it correct by
**behavior-equivalence**: the verifier generates random line batches (with
deliberate duplicate runs, blank lines, tabs, trailing spaces, and unicode)
and compares the agent's stdout **byte-for-byte** against a reference
implementation — with and without the `-c` count flag.

## How it follows the checklist

- **Resolves the sandbox robustly** — honors `AGENTLOOP_SANDBOX` first, then
  walks up to the nearest ancestor containing a `sandbox/` dir; exits 2 with a
  fix-it message if neither resolves.
- **Exit 0 means *correct*** — any byte mismatch, crash, or non-zero exit
  fails the run.
- **No secrets** — script and fixtures contain nothing sensitive.
- **Deterministic** — the RNG is seeded (`1337`), no network, no clock.
- **Never mutates the sandbox** — the candidate only reads stdin; fixtures
  live in `/tmp`.
- **Adversarial cases** — empty input (must produce *no* output), all-blank
  runs, whitespace-only vs empty lines, non-adjacent repeats (must NOT merge),
  unicode, and exact `-c` formatting.

## The gotcha this catches

A naive "sort-then-merge" solution collapses *non-adjacent* duplicates
(`a b a` → `a b`) and loses the exact `-c` count format — both are caught by
the byte-for-byte comparison. The empty-input case catches candidates that
always print a trailing newline.

## Use it

Copy `verify.sh` + `goal.txt` next to your project's `sandbox/` directory,
then:

```bash
agentloop --verify "bash verify.sh"
```

Expected runtime: < 10 seconds. Expected cost: $0.
