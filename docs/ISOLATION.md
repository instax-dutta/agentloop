# AgentLoop Isolation Matrix

This document outlines the isolation guarantees and security boundaries provided by each AgentLoop execution mode.

| Mode | Filesystem | Network | Process | Secrets | Use Case |
|------|-----------|---------|---------|---------|----------|
| **default** (cwd=sandbox) | Host | Host | Host | Scrubbed | Trusted local development |
| **`--docker`** | Container (`/workspace` only) | Restricted (`--network=none` by default) | Container | Scrubbed | Untrusted agents / untrusted code |
| **`--podman`** | Container (`/workspace` only) | Restricted (`--network=none` by default) | Container | Scrubbed | Daemonless & rootless enterprise environments |

---

## Detailed Isolation Properties

### 1. Filesystem Isolation
- **default**: The agent process executes on the host with `cwd=sandbox`. It relies on proper agent tool usage to stay within the sandbox.
- **`--docker` / `--podman`**: Mounts only `sandbox/` as read-write at `/workspace` inside the container. Host configuration directories (such as `~/.ssh`, `~/.aws`, `~/.config`) are **not** mounted.

### 2. Network Isolation
- **default**: Full host network access.
- **`--docker` / `--podman`**: Defaults to `--network=none`. If your agent CLI needs model API access, set `AGENTLOOP_DOCKER_NETWORK=host` or a custom container network name.

### 3. Process & User Isolation
- **default**: Runs as the host user.
- **`--docker` / `--podman`**: Runs as non-root user inside the container (`--user <uid>:<gid>`).

### 4. Secret Scrubbing
In all modes, AgentLoop strips credential environment variables (such as `AWS_SECRET_ACCESS_KEY`, `SSH_AUTH_SOCK`, `GITHUB_TOKEN`, etc.) before passing environment to the agent process.
