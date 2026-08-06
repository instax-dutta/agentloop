# roman-numeral-converter

tags: held-out-oracle

A bidirectional integer ↔ Roman-numeral converter verified with the **held-out
oracle** — AgentLoop's anti-overfitting moat. The verifier records a trusted
reference on ~80 generated inputs, exposes only **3 visible** cases, seals the
rest, and grades the agent's `roman.py` on **every** input. It only passes if
it's correct on cases it never saw, so memorizing the visible examples is
worthless.

## How it follows the checklist

- **Resolves the sandbox robustly** — honors `AGENTLOOP_SANDBOX` first, then
  walks up to the nearest ancestor containing a `sandbox/` dir; exits 2 with a
  fix-it message if neither resolves.
- **Exit 0 means *correct*** — `grade` exits 0 only when the candidate matches
  the reference on ALL visible AND held-out inputs.
- **No secrets** — the seal is a fixed demo secret (`roman-demo-secret`),
  overridable via `ORACLE_SEAL`; the candidate never receives it (the oracle
  scrubs the env).
- **Deterministic** — seeded RNG (`1337`) and a fixed reference; no network,
  no clock.
- **Never mutates the sandbox** — the candidate only reads stdin; the sealed
  oracle is written under the verifier's own `.agentloop/oracle_sealed/`
  (gitignored), outside the sandbox.
- **Adversarial cases** — out-of-range integers (`0`, `3999` boundary),
  non-Roman input (`ABC`), and the classic subtraction traps (`IV`, `IX`,
  `XL`, `XC`, `CD`, `CM`, `MCMXCIV`).

## The gotcha this catches

An agent that hand-writes answers for the visible examples passes those 3
cases and fails every held-out input — `grade` reports the exact
`first_divergence` so the failure feeds straight back into the loop. A
reference-matching candidate must implement general conversion, not pattern
matching.

## Use it

Copy `verify.sh` + `goal.txt` next to your project's `sandbox/` directory,
then:

```bash
agentloop --verify "bash verify.sh"
```

Requires `agentloop-cli` installed (provides the `agentloop.oracle` module).
Expected runtime: < 15 seconds. Expected cost: $0.
