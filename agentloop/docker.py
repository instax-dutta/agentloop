"""
docker.py — Docker and Podman container isolation runner for AgentLoop.
"""
import os
import pathlib
import shutil
import subprocess

from .oracle import safe_env


def run_in_docker(
    cmd: str,
    sandbox: pathlib.Path,
    env: dict[str, str] | None = None,
    timeout: int = 900,
    podman: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command inside a Docker or Podman container with isolated environment and mounts."""
    binary = "podman" if podman else "docker"

    if not shutil.which(binary):
        raise RuntimeError(f"Container runtime {binary!r} not found in PATH.")

    sandbox_abs = sandbox.resolve()
    network = os.environ.get("AGENTLOOP_DOCKER_NETWORK", "none")
    image = os.environ.get("AGENTLOOP_DOCKER_IMAGE", "python:3.12-slim")

    # Cleaned environment without secrets
    clean_env = env if env is not None else safe_env()

    docker_args = [
        binary,
        "run",
        "--rm",
        "-v",
        f"{sandbox_abs}:/workspace:rw",
        "-w",
        "/workspace",
        f"--network={network}",
    ]

    # Non-root user setup if on POSIX
    if hasattr(os, "getuid"):
        uid = os.getuid()
        gid = os.getgid() if hasattr(os, "getgid") else uid
        if uid != 0:
            docker_args.extend(["--user", f"{uid}:{gid}"])
        else:
            docker_args.extend(["--user", "1000:1000"])

    # Pass safe env vars into container
    for k, v in clean_env.items():
        # Exclude secrets or host paths
        is_secret = (k.startswith("SSH_") or k.startswith("AWS_")
                     or "KEY" in k.upper() or "SECRET" in k.upper())
        if not is_secret:
            docker_args.extend(["-e", f"{k}={v}"])

    docker_args.extend([image, "sh", "-c", cmd])

    return subprocess.run(
        docker_args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
