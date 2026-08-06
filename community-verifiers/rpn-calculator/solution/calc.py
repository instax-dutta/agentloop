#!/usr/bin/env python3
"""Perfect solution for the rpn-calculator verifier (CI-seeded).

Evaluates reverse-Polish-notation integer expressions: operands push onto a
stack, an operator pops the two top values (a = top, b = next) and pushes
`b <op> a`. Division truncates toward zero (like C). Any invalid line —
division by zero, underflow, malformed token, leftover operands — prints
ERROR. Blank lines are skipped; empty input yields no output.
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
                stack.append(b + a)
            elif tok == "-":
                stack.append(b - a)
            elif tok == "*":
                stack.append(b * a)
            else:  # "/" — integer division truncating toward zero
                if a == 0:
                    return None
                q = abs(b) // abs(a)
                if (b < 0) != (a < 0):
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
