#!/usr/bin/env python3
"""Tests for agentloop.parallel DAG execution module."""
import time
from agentloop.parallel import parse_plan_dag, run_plan_parallel

# 1. Test DAG parsing
plan_text = """
# Execution Plan
- [ ] Task 1: Initialize database
- [ ] Task 2: Build API endpoint (after: #1)
- [ ] Task 3: Build background worker (depends on: #1)
- [ ] Task 4: Run E2E tests (depends on: #2, #3)
"""
nodes = parse_plan_dag(plan_text)
assert len(nodes) == 4, f"expected 4 nodes, got {len(nodes)}"
assert nodes[0].depends_on == []
assert nodes[1].depends_on == [1]
assert nodes[2].depends_on == [1]
assert nodes[3].depends_on == [2, 3]
print("DAG PARSING TEST: PASS")

# 2. Test Parallel execution and DAG order
executed_order = []
def mock_worker(node, sandbox_dir, state_file):
    time.sleep(0.01)
    executed_order.append(node.task_id)
    return 0

results = run_plan_parallel(nodes, mock_worker, max_workers=4)
assert len(results) == 4
assert results[0]["passed"] is True
assert executed_order[0] == 1, "Task 1 must execute first"
print("PARALLEL DAG EXECUTION TEST: PASS")

# 3. Test Failure Cancellation / Downstream Skipping
fail_plan = """
- [ ] Step A
- [ ] Step B (after: #1)
- [ ] Step C (after: #2)
"""
fail_nodes = parse_plan_dag(fail_plan)

def mock_failing_worker(node, sandbox_dir, state_file):
    if node.task_id == 1:
        return 1  # Fail step 1
    return 0

fail_results = run_plan_parallel(fail_nodes, mock_failing_worker, max_workers=2)
assert fail_results[0]["passed"] is False
assert fail_results[1].get("skipped") is True, "Step B should be skipped"
assert fail_results[2].get("skipped") is True, "Step C should be skipped"
print("DAG FAILURE CANCELLATION TEST: PASS")

print("\nALL PARALLEL TESTS PASSED")
