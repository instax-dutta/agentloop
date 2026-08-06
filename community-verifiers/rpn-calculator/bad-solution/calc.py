#!/usr/bin/env python3
"""Plausible-but-wrong solution (CI adversarial fixture).

Pops operands in the wrong order: computes `a - b` and `a / b` where the
spec says `b - a` and `b / a`. Sails through every commutative, associative,
distributive, and identity check involving + and * — but violates the
`a 0 - = a` and `a 1 / = a` invariants and every subtraction/division edge
case. The property-based oracle catches it without ever knowing a single
expected answer.
"""
import sys


def evaluate(tokens):
    stack = []
    for tok in tokens:
        if tok in ("+", "-", "*", "/"):
            if len(stack) < 2:
                return None
            a = stack.pop()
            b = stack.pop()
            if tok == "+":
                stack.append(a + b)   # commutative — same result, no tell
            elif tok == "-":
                stack.append(a - b)   # WRONG ORDER: a - b, not b - a
            elif tok == "*":
                stack.append(a * b)   # commutative — same result, no tell
            else:  # "/" — WRONG ORDER: a / b, not b / a
                if b == 0:
                    return None
                q = abs(a) // abs(b)
                if (a < 0) != (b < 0):
                    q = -q
                stack.append(q)
        else:
            try:
                stack.append(int(tok))
            except ValueError:
                return None
    return stack[0] if len(stack) == 1 else None


def main():
    data = sys.stdin.read()
    if data.endswith("\n"):
        data = data[:-1]
    for line in data.split("\n"):
        if not line.strip():
            continue
        result = evaluate(line.split())
        sys.stdout.write("ERROR\n" if result is None else f"{result}\n")


if __name__ == "__main__":
    main()
