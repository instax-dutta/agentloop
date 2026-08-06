#!/usr/bin/env python3
"""CI check for the community-verifiers gallery.

Every verifier at `community-verifiers/<name>/` must ship a `solution/`
directory containing a *correct* implementation of the task. This script:

1. Replicates the in-repo layout in a throwaway temp dir — so verifiers that
   resolve the sandbox via `$SCRIPT_DIR`/`../..` styles find one WITHOUT
   touching the real repo's `sandbox/`.
2. Seeds that sandbox from the verifier's `solution/` dir.
3. Runs `verify.sh` (with `AGENTLOOP_SANDBOX` set as well) and requires
   exit 0.

A verifier that rejects correct code — or is missing its `solution/` — fails
CI, keeping every contribution provably green.

Usage:  python community-verifiers/check_verifiers.py
Exit 0 when every verifier passes, non-zero otherwise.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GALLERY = ROOT / "community-verifiers"


def _seed_and_run(verifier_dir: pathlib.Path) -> tuple[int, str]:
    """Replicate the gallery layout in a temp dir, seed the sandbox from
    solution/, and run verify.sh. Returns (returncode, output)."""
    with tempfile.TemporaryDirectory() as td:
        troot = pathlib.Path(td)
        # In-repo layout: community-verifiers/<name>/ next to a repo-root sandbox/
        t_verifier = troot / "community-verifiers" / verifier_dir.name
        shutil.copytree(verifier_dir, t_verifier)
        t_sandbox = troot / "sandbox"
        t_sandbox.mkdir()
        shutil.copytree(verifier_dir / "solution", t_sandbox, dirs_exist_ok=True)
        # Sibling sandboxes for `$SCRIPT_DIR/sandbox` (layout A) and
        # `$SCRIPT_DIR/../sandbox` (layout B) resolution styles.
        for extra in (t_verifier / "sandbox", troot / "community-verifiers" / "sandbox"):
            shutil.copytree(t_sandbox, extra, dirs_exist_ok=True)

        env = dict(os.environ)
        env["AGENTLOOP_SANDBOX"] = str(t_sandbox)
        # cwd = temp project root so even cwd-relative (`./sandbox`) resolvers
        # land in temp space and can never touch the real repo sandbox.
        r = subprocess.run(["bash", str(t_verifier / "verify.sh")],
                           capture_output=True, text=True, env=env,
                           cwd=str(troot))
        return r.returncode, (r.stdout or "") + (r.stderr or "")


def check_verifier(verifier_dir: pathlib.Path) -> list[str]:
    problems: list[str] = []
    name = verifier_dir.name
    for required, label in ((verifier_dir / "goal.txt", "goal.txt"),
                            (verifier_dir / "README.md", "README.md"),
                            (verifier_dir / "verify.sh", "verify.sh"),
                            (verifier_dir / "solution", "solution/")):
        if not required.exists():
            problems.append(f"{name}: missing {label}")
    if problems:
        return problems  # can't evaluate without the required pieces
    if not any(p.is_file() for p in (verifier_dir / "solution").rglob("*")):
        return [f"{name}: solution/ is empty — ship a correct implementation"]

    rc, out = _seed_and_run(verifier_dir)
    if rc != 0:
        problems.append(
            f"{name}: verify.sh FAILED against the seeded solution "
            f"(exit {rc}):\n{out[-1500:]}"
        )
    return problems


def main() -> int:
    if not GALLERY.is_dir():
        print(f"ERROR: gallery not found at {GALLERY}")
        return 1
    verifiers = sorted(d for d in GALLERY.iterdir()
                       if d.is_dir() and (d / "verify.sh").exists())
    if not verifiers:
        print("ERROR: no community verifiers found")
        return 1

    failures = 0
    for v in verifiers:
        problems = check_verifier(v)
        if problems:
            failures += 1
            for p in problems:
                print(f"FAIL: {p}")
        else:
            print(f"PASS: {v.name}")

    if failures:
        print(f"\n{failures}/{len(verifiers)} community verifiers FAILED")
        return 1
    print(f"\nAll {len(verifiers)} community verifiers PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
