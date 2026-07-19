#!/usr/bin/env python3
"""Process a list of dicts with x/y coordinates and produce labelled results."""
import json
import sys


def process(data):
    """Classify and compute values based on x/y sign combinations."""
    result = []
    for i in range(len(data)):
        d = data[i]
        x = d['x']
        y = d['y']
        if x > 0:
            if y > 0:
                result.append({'label': 'A', 'val': x + y})
            else:
                result.append({'label': 'B', 'val': x - y})
        else:
            if y > 0:
                result.append({'label': 'C', 'val': y - x})
            else:
                result.append({'label': 'D', 'val': x * y})
    return result


if __name__ == '__main__':
    inp = json.loads(sys.stdin.read())
    out = process(inp)
    print(json.dumps(out))
