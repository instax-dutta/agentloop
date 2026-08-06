#!/usr/bin/env python3
"""Perfect solution for the uniq-reimplementation verifier (CI-seeded).

Deduplicates CONSECUTIVE duplicate lines (first occurrence wins), preserving
order and exact line text. With -c, prefixes each output line with the run
length. Empty input yields no output.
"""
import sys


def uniq(lines, count):
    out = []
    i = 0
    n = len(lines)
    while i < n:
        j = i + 1
        while j < n and lines[j] == lines[i]:
            j += 1
        if count:
            out.append(f"{j - i} {lines[i]}")
        else:
            out.append(lines[i])
        i = j
    return out


def main():
    data = sys.stdin.read()
    if data.endswith("\n"):
        data = data[:-1]
    lines = data.split("\n")
    out = uniq(lines, "-c" in sys.argv[1:])
    if out:
        sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
