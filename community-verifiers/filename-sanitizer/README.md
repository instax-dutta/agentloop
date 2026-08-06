# filename-sanitizer

tags: fixture

A real-world "batch rename" task verified with a **fixture + post-conditions**
oracle: the verifier builds a realistic directory tree in a temp dir, runs the
agent's script against a *copy*, and asserts what the tree must look like
afterwards.

## How it follows the checklist

- **Runs with cwd = project root** — the sandbox is located by walking up from
  `SCRIPT_DIR` to the nearest ancestor containing a `sandbox/` dir (any nesting
  depth), or via an explicit `AGENTLOOP_SANDBOX=/abs/path` override. If neither
  resolves, it exits 2 with a fix-it message instead of a misleading failure.
- **Exit 0 means *correct*** — any failed post-condition exits 1; a missing
  candidate exits 2.
- **No secrets** — the script and fixtures contain nothing sensitive.
- **Deterministic** — fixed fixture content, no randomness, no network, no
  clock dependence.
- **Never mutates the sandbox** — the candidate runs against a `cp -R` copy in
  `mktemp -d`, cleaned up by a `trap` on `EXIT`.
- **Adversarial cases** — hidden files with spaces must be ignored, an
  existing-name collision must get a `_2` suffix instead of overwriting, deep
  nesting forces bottom-up renaming, and the top-level entry count must stay
  exactly 8 (no spurious files the agent might add as "backup" copies).

## The gotcha this catches

Most naive solutions rename `docs/sub folder` *before* its contents, so
`docs/sub folder/read me.txt` no longer exists when they try to rename it —
the `docs/read_me.txt` post-condition catches that instantly. The hidden-file
case catches scripts that blindly `replace(" ", "_")` everything.

## Use it

Copy `verify.sh` + `goal.txt` next to your project's `sandbox/` directory,
then:

```bash
agentloop --verify "bash verify.sh"
```

Expected runtime: < 5 seconds. Expected cost: $0.
