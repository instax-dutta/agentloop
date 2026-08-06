# markdown-to-html

Golden-file comparison oracle.

## What it teaches

The golden-file pattern: a fixed set of inputs with hand-verified expected
output, compared character-for-character. No test *logic* in the verifier at
all — just expected output. Great for anything with a defined output format
(compilers, formatters, converters).

## Oracle pattern

8 golden cases embedded directly in `verify.sh`; the agent's `md2html.py`
must reproduce the expected HTML byte-for-byte, including HTML escaping.

## Run it

```bash
agentloop --init --example markdown-to-html
agentloop --verify "bash verify.sh"
```

Expected runtime: ~1–3 minutes. Expected cost: < $0.10.
