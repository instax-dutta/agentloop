"""
parallel.py — Parallel multi-agent fan-out and DAG execution for AgentLoop.
"""
import concurrent.futures
import pathlib
import re
import threading
import time
from typing import Any


class TaskNode:
    def __init__(self, task_id: int, name: str, depends_on: list[int] | None = None):
        self.task_id = task_id  # 1-indexed ID
        self.name = name
        self.depends_on: list[int] = depends_on if depends_on is not None else []
        self.status = "pending"  # pending, running, completed, failed, skipped
        self.returncode: int | None = None


def parse_plan_dag(text: str) -> list[TaskNode]:
    """Parse markdown plan text into a list of TaskNodes with DAG dependencies."""
    raw_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- [ ]"):  # only UNchecked tasks are runnable
            raw_lines.append(line[5:].strip())
        elif line.startswith("- ") or line.startswith("* "):
            raw_lines.append(line[2:].strip())
        elif line.startswith("## ") and not line.startswith("###"):
            raw_lines.append(line[3:].strip())

    nodes: list[TaskNode] = []
    name_to_id: dict[str, int] = {}

    # First pass: assign IDs and clean names
    for idx, raw in enumerate(raw_lines, start=1):
        # Extract dependency annotations e.g. (depends on: #1) or (after: #1) or (depends on: task_name)
        clean_name = re.sub(r"\((?:depends on|after):.*?\)", "", raw, flags=re.IGNORECASE).strip()
        clean_name = re.sub(r"\|.*$", "", clean_name).strip()
        name_to_id[clean_name.lower()] = idx
        nodes.append(TaskNode(task_id=idx, name=clean_name))

    # Second pass: parse dependencies (supports comma-separated lists, e.g.
    # `(depends on: #2, #3)` or `(after: Task B, Task C)`)
    for idx, raw in enumerate(raw_lines):
        node = nodes[idx]
        deps: set[int] = set()

        for ann in re.findall(r"\((?:depends on|after):\s*([^)]*)\)", raw, re.IGNORECASE):
            for tok in ann.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                if tok.lstrip("#").isdigit():
                    dep_id = int(tok.lstrip("#"))
                    if 1 <= dep_id <= len(nodes) and dep_id != node.task_id:
                        deps.add(dep_id)
                else:
                    target = tok.lower()
                    if target in name_to_id and name_to_id[target] != node.task_id:
                        deps.add(name_to_id[target])

        node.depends_on = sorted(list(deps))

    return nodes


def run_plan_parallel(
    nodes: list[TaskNode],
    worker_fn: Any,
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """Execute a DAG of task nodes in parallel using worker_fn(node, sandbox_dir, state_file)."""
    lock = threading.Lock()
    results: list[dict[str, Any]] = []

    def _execute_node(node: TaskNode) -> dict[str, Any]:
        with lock:
            node.status = "running"
            print(f"  [RUNNING] Task {node.task_id}: {node.name}")

        sandbox_dir = pathlib.Path.cwd() / "sandbox" / f"task-{node.task_id}"
        state_file = pathlib.Path.cwd() / f"agentloop.state.task-{node.task_id}.json"

        try:
            rc = worker_fn(node, sandbox_dir, state_file)
        except Exception:
            rc = 1

        with lock:
            if rc == 0:
                node.status = "completed"
                node.returncode = 0
                print(f"  ✅ [PASSED] Task {node.task_id}: {node.name}")
            else:
                node.status = "failed"
                node.returncode = rc
                print(f"  ❌ [FAILED] Task {node.task_id}: {node.name} (exit={rc})")

        return {"task_id": node.task_id, "name": node.name, "passed": (rc == 0), "returncode": rc}

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    futures: dict[concurrent.futures.Future[Any], TaskNode] = {}

    try:
        while True:
            with lock:
                # Check for ready tasks
                all_done = True
                for node in nodes:
                    if node.status in ("pending", "running"):
                        all_done = False

                    if node.status == "pending":
                        # Check dependencies
                        dep_nodes = [nodes[d - 1] for d in node.depends_on]
                        any_failed = any(d.status in ("failed", "skipped") for d in dep_nodes)
                        all_passed = all(d.status == "completed" for d in dep_nodes)

                        if any_failed:
                            node.status = "skipped"
                            print(f"  ⏭️ [SKIPPED] Task {node.task_id}: {node.name} "
                                  "(upstream dependency failed)")
                            results.append({"task_id": node.task_id, "name": node.name,
                                            "passed": False, "returncode": 1, "skipped": True})
                        elif all_passed:
                            # Ready to run!
                            fut = executor.submit(_execute_node, node)
                            futures[fut] = node

                if all_done:
                    break

            time.sleep(0.05)

        # Wait for all running tasks
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results.append(res)

    finally:
        executor.shutdown(wait=True)

    # Sort by task_id
    results.sort(key=lambda r: r["task_id"])
    return results
