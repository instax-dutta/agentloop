#!/usr/bin/env python3
"""Plausible-but-wrong solution (CI adversarial fixture).

Removes ALL duplicates globally instead of collapsing only consecutive runs:
non-adjacent repeats get merged, and the -c flag is ignored entirely. Looks
right on tidy inputs, diverges on the exact gotchas the verifier exists to
catch.
"""
import sys


def main():
    data = sys.stdin.read()
    if data.endswith("\n"):
        data = data[:-1]
    lines = data.split("\n")
    out = []
    for ln in lines:
        if ln not in out:
            out.append(ln)
    if out:
        sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
