#!/usr/bin/env python3
"""CI check for the community-verifiers gallery.

Every verifier at `community-verifiers/<name>/` must ship a `solution/`
directory containing a *correct* implementation of the task, and a
`bad-solution/` directory containing a plausible-but-*incorrect* one. This
script proves both directions:

1. Replicates the in-repo layout in a throwaway temp dir — so verifiers that
   resolve the sandbox via `$SCRIPT_DIR`/`../..` styles find one WITHOUT
   touching the real repo's `sandbox/`.
2. Seeds that sandbox from `solution/` and requires `verify.sh` to exit 0
   (the verifier must ACCEPT correct code).
3. Re-seeds the sandbox from `bad-solution/` and requires `verify.sh` to exit
   NON-zero (the verifier must REJECT incorrect code — the adversarial path).

A verifier that fails either direction — or is missing either seed dir — fails
CI, keeping every contribution provably green in both directions.

Usage:  python community-verifiers/check_verifiers.py
Exit 0 when every verifier passes both directions, non-zero otherwise.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
GALLERY = ROOT / "community-verifiers"


def _seed_and_run(verifier_dir: pathlib.Path,
                  seed_dir: pathlib.Path) -> tuple[int, str]:
    """Replicate the gallery layout in a temp dir, seed the sandbox from
    seed_dir (solution/ or bad-solution/), and run verify.sh.
    Returns (returncode, output)."""
    with tempfile.TemporaryDirectory() as td:
        troot = pathlib.Path(td)
        # In-repo layout: community-verifiers/<name>/ next to a repo-root sandbox/
        t_verifier = troot / "community-verifiers" / verifier_dir.name
        shutil.copytree(verifier_dir, t_verifier)
        t_sandbox = troot / "sandbox"
        t_sandbox.mkdir()
        shutil.copytree(seed_dir, t_sandbox, dirs_exist_ok=True)
        # Sibling sandboxes for `$SCRIPT_DIR/sandbox` (layout A) and
        # `$SCRIPT_DIR/../sandbox` (layout B) resolution styles.
        for extra in (t_verifier / "sandbox",
                      troot / "community-verifiers" / "sandbox"):
            shutil.copytree(t_sandbox, extra, dirs_exist_ok=True)

        env = dict(os.environ)
        env["AGENTLOOP_SANDBOX"] = str(t_sandbox)
        # held-out-oracle verifiers run `python3 -m agentloop.oracle`; make the
        # repo's agentloop importable even from the throwaway cwd below.
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        # cwd = temp project root so even cwd-relative (`./sandbox`) resolvers
        # land in temp space and can never touch the real repo sandbox.
        r = subprocess.run(["bash", str(t_verifier / "verify.sh")],
                           capture_output=True, text=True, env=env,
                           cwd=str(troot))
        return r.returncode, (r.stdout or "") + (r.stderr or "")


def _relative_files(directory: pathlib.Path) -> set[pathlib.Path]:
    return {p.relative_to(directory)
            for p in directory.rglob("*") if p.is_file()}


def check_verifier(verifier_dir: pathlib.Path) -> list[str]:
    problems: list[str] = []
    name = verifier_dir.name
    solution_dir = verifier_dir / "solution"
    bad_dir = verifier_dir / "bad-solution"
    for required, label in ((verifier_dir / "goal.txt", "goal.txt"),
                            (verifier_dir / "README.md", "README.md"),
                            (verifier_dir / "verify.sh", "verify.sh"),
                            (solution_dir, "solution/"),
                            (bad_dir, "bad-solution/")):
        if not required.exists():
            problems.append(f"{name}: missing {label}")
    if problems:
        return problems  # can't evaluate without the required pieces

    empty_problems = []
    for empty_dir, label, hint in ((solution_dir, "solution/",
                                    "ship a correct implementation"),
                                   (bad_dir, "bad-solution/",
                                    "ship a plausible INCORRECT implementation "
                                    "that verify.sh must reject")):
        if not any(p.is_file() for p in empty_dir.rglob("*")):
            empty_problems.append(f"{name}: {label} is empty — {hint}")
    if empty_problems:
        return empty_problems

    # Name-set gate: bad-solution/ must mirror solution/ file-for-file (same
    # relative paths), so verify.sh genuinely runs the bad code. A subset
    # could omit the exact file verify.sh invokes — then "file not found"
    # (exit 2) would trivially "reject" code that was never actually tested.
    solution_files = _relative_files(solution_dir)
    bad_files = _relative_files(bad_dir)
    missing_from_bad = sorted(solution_files - bad_files)
    missing_from_solution = sorted(bad_files - solution_files)
    if missing_from_bad or missing_from_solution:
        parts = []
        if missing_from_bad:
            parts.append(f"missing in bad-solution/: "
                         f"{', '.join(str(m) for m in missing_from_bad)}")
        if missing_from_solution:
            parts.append(f"no counterpart in solution/: "
                         f"{', '.join(str(m) for m in missing_from_solution)}")
        problems.append(f"{name}: bad-solution/ must mirror solution/ "
                        f"file-for-file; {'; '.join(parts)}")
        return problems

    # Positive path: the verifier must ACCEPT correct code.
    rc, out = _seed_and_run(verifier_dir, solution_dir)
    if rc != 0:
        problems.append(
            f"{name}: verify.sh FAILED against the seeded solution "
            f"(exit {rc}):\n{out[-1500:]}"
        )

    # Adversarial path: the verifier must REJECT incorrect code. Verifiers
    # reserve exit 2 for "unable to evaluate" (missing file / sandbox) and
    # exit 1 for "verification failed" — only the latter counts as a genuine
    # rejection, so exit 2 against bad-solution/ is a failure of this check.
    rc, out = _seed_and_run(verifier_dir, bad_dir)
    if rc == 0:
        problems.append(
            f"{name}: verify.sh ACCEPTED bad-solution/ (exit 0) — a verifier "
            f"that can't distinguish correct from incorrect is worthless.\n"
            f"verifier output:\n{out[-1500:]}"
        )
    elif rc == 2:
        problems.append(
            f"{name}: verify.sh exited 2 (\"unable to evaluate\") against "
            f"bad-solution/ — a genuine rejection must use exit 1; exit 2 "
            f"means the bad code was never actually tested.\n"
            f"verifier output:\n{out[-1500:]}"
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
            print(f"PASS: {v.name} (accepts solution/, rejects bad-solution/)")

    if failures:
        print(f"\n{failures}/{len(verifiers)} community verifiers FAILED")
        return 1
    print(f"\nAll {len(verifiers)} community verifiers PASS both directions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
