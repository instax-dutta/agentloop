#!/usr/bin/env python3
"""Plausible-but-wrong solution (CI adversarial fixture).

Top-down walk renames parent directories before their children, so everything
inside a renamed folder is orphaned (deep nesting silently lost), and the
collision case raises FileExistsError. Correct on shallow, collision-free
trees — wrong on exactly the cases the verifier stresses.
"""
import os
import sys


def sanitize(root):
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.startswith(".") and " " in name:
                os.rename(os.path.join(dirpath, name),
                          os.path.join(dirpath, name.replace(" ", "_")))
        for name in dirnames:
            if not name.startswith(".") and " " in name:
                os.rename(os.path.join(dirpath, name),
                          os.path.join(dirpath, name.replace(" ", "_")))


if __name__ == "__main__":
    sanitize(sys.argv[1])
