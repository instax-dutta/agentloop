# Quickstart

## Install

```bash
pip install agentloop-cli
agentloop --init        # scaffolds goal.txt + verify.sh + .env
./launch.sh             # or: agentloop "your goal" --verify "bash verify.sh"
```

No API key from us. The harness you already use supplies the model.

## Try a real example

```bash
agentloop --examples                      # list all 10 bundled examples
agentloop --init --example regex-engine   # seed goal.txt + verify.sh
agentloop --verify "bash verify.sh"
```

## Check your setup

```bash
agentloop --doctor      # diagnoses missing agent CLI / verifier / sandbox
agentloop --dry-run     # prints the resolved configuration, runs nothing
```

## Common commands

| Command | What it does |
|---------|-------------|
| `agentloop "task" --verify "bash verify.sh"` | Run one task to completion |
| `agentloop --run plan.md --workers 4` | Run a plan's tasks in parallel (DAG-aware) |
| `agentloop --status` | Show current run status + cost breakdown |
| `agentloop --cost` | Print the cost summary of the latest run |
| `agentloop --serve` | Web monitor at http://localhost:8080 |
| `agentloop --docker` / `--podman` | Hard container isolation |

## Exit codes

| Status | Code | Meaning |
|--------|------|---------|
| completed | 0 | Goal met, verification passed |
| blocked | 1 | Agent gave up |
| config / missing agent | 2 | Setup problem (run `agentloop --doctor`) |
| timeout | 3 | Wall-clock limit hit |
| exhausted | 4 | Max iterations reached |
| over-budget | 5 | Cost cap exceeded |
| stopped | 130 | SIGTERM/SIGINT / STOP file |
