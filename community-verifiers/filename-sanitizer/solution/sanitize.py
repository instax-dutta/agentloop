#!/usr/bin/env python3
"""Perfect solution for the filename-sanitizer verifier (CI-seeded).

Renames every file and directory under the given root so spaces become
underscores: hidden entries are left untouched, collisions get a numeric
suffix, and contents are renamed before their parent directory so children
are never orphaned.
"""
import os
import sys


def rename_entry(directory, name):
    """Rename one entry in place; returns nothing. Skips hidden and
    space-free names; appends _2, _3, ... when the target already exists."""
    if name.startswith("."):
        return
    if " " not in name:
        return
    base = name.replace(" ", "_")
    target = os.path.join(directory, base)
    n = 2
    while os.path.exists(target):
        stem, ext = os.path.splitext(base)
        target = os.path.join(directory, f"{stem}_{n}{ext}")
        n += 1
    os.rename(os.path.join(directory, name), target)


def sanitize(root):
    # bottom-up so files are renamed before their (renamed) parent dirs
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            rename_entry(dirpath, name)
        for name in dirnames:
            rename_entry(dirpath, name)


if __name__ == "__main__":
    sanitize(sys.argv[1])
