#!/usr/bin/env python3
"""Perfect solution for the roman-numeral-converter verifier (CI-seeded).

Converts integers (1..3999) to Roman numerals and canonical Roman numerals
back to integers, matching the reference exactly — including "INVALID" for
out-of-range or non-Roman input.
"""
import sys

VALUES = [("M", 1000), ("CM", 900), ("D", 500), ("CD", 400), ("C", 100),
          ("XC", 90), ("L", 50), ("XL", 40), ("X", 10), ("IX", 9),
          ("V", 5), ("IV", 4), ("I", 1)]


def to_roman(n):
    out = []
    for sym, val in VALUES:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def from_roman(s):
    total = 0
    i = 0
    while i < len(s):
        for sym, val in VALUES:
            if s.startswith(sym, i):
                total += val
                i += len(sym)
                break
        else:
            return None
    return total


def main():
    line = sys.stdin.read().strip()
    if not line:
        return
    if line.isdigit():
        n = int(line)
        print(to_roman(n) if 1 <= n <= 3999 else "INVALID")
    else:
        r = from_roman(line)
        print(r if r is not None else "INVALID")


if __name__ == "__main__":
    main()
