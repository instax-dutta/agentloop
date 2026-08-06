# tax-demo

The starter example — a realistic domain oracle.

## What it teaches

The full loop on a real (if small) domain: US income tax brackets, standard
deductions, and capital gains. The verifier runs the candidate's
`tax_calc.py` against bracketed test cases and checks the computed tax, not
just that the script runs.

## Oracle pattern

Fixed test cases in bash with exact-output comparison, reusing the repo's
`verify.sh`. This is the example `agentloop --init` seeds by default.

## Run it

```bash
agentloop --init --example tax-demo
agentloop --verify "bash verify.sh"
```

Expected runtime: ~1–2 minutes. Expected cost: < $0.10.
