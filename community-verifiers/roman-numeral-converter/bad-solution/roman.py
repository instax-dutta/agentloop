#!/usr/bin/env python3
"""Plausible-but-wrong solution (CI adversarial fixture).

Additive-only conversion: no subtractive pairs. 4 becomes IIII and IV parses
as 6. Passes the 3 visible cases (1, I, 5) and every purely-additive input —
fails on all held-out subtraction cases, which is exactly the overfitting trap
the held-out oracle exists to expose.
"""
import sys

VALUES = [("M", 1000), ("D", 500), ("C", 100), ("L", 50),
          ("X", 10), ("V", 5), ("I", 1)]


def to_roman(n):
    if not 1 <= n <= 3999:
        return "INVALID"
    out = []
    for sym, val in VALUES:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def from_roman(s):
    total = 0
    for ch in s:
        for sym, val in VALUES:
            if ch == sym:
                total += val
                break
        else:
            return None
    return total


def main():
    line = sys.stdin.read().strip()
    if not line:
        return
    if line.isdigit():
        print(to_roman(int(line)))
    else:
        r = from_roman(line)
        print(r if r is not None else "INVALID")


if __name__ == "__main__":
    main()
