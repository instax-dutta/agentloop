#!/usr/bin/env python3
"""Tests for agentloop.cost module."""
from agentloop.cost import CostTracker, parse_harness_output

# 1. Test Claude JSON parsing
claude_out = '{"model": "claude-3-7-sonnet", "usage": {"input_tokens": 1234, "output_tokens": 567}}'
res = parse_harness_output("claude", claude_out)
assert res is not None, "Failed to parse Claude output"
in_tok, out_tok, model = res
assert in_tok == 1234
assert out_tok == 567
assert model == "claude-3-7-sonnet"
print("CLAUDE COST PARSER TEST: PASS")

# 2. Test OpenCode / OpenAI JSON parsing
opencode_out = '{"model": "gpt-4o-mini", "usage": {"prompt_tokens": 1000, "completion_tokens": 200}}'
res2 = parse_harness_output("opencode", opencode_out)
assert res2 is not None, "Failed to parse OpenCode output"
assert res2[0] == 1000
assert res2[1] == 200
print("OPENCODE COST PARSER TEST: PASS")

# 3. Test Aider format parsing
aider_out = "Tokens: 1.5k sent, 500 received. Model: gpt-4o-mini"
res3 = parse_harness_output("aider", aider_out)
assert res3 is not None, "Failed to parse Aider output"
assert res3[0] == 1500
assert res3[1] == 500
print("AIDER COST PARSER TEST: PASS")

# 4. Test CostTracker calculation
tracker = CostTracker()
iter_info = tracker.record_iteration(
    iter_num=1,
    preset="claude",
    input_tokens=1000000,
    output_tokens=1000000,
    model_name="claude-3-7-sonnet"
)
# input: $3.00, output: $15.00 -> total $18.00
assert round(iter_info["cost"], 2) == 18.00
assert round(tracker.running_cost, 2) == 18.00
assert iter_info["is_estimated"] is False

# Fallback test
iter_info2 = tracker.record_iteration(
    iter_num=2,
    preset="opencode",
    estimated_fallback_cost=0.10
)
assert iter_info2["is_estimated"] is True
assert round(tracker.running_cost, 2) == 18.10
print("COST TRACKER TEST: PASS")

# 5. Codex: JSON block embedded in noisy stdout
codex_out = 'Some preamble\n{"model": "gpt-4o", "usage": {"prompt_tokens": 800, "completion_tokens": 120}}\ntrailing'
res5 = parse_harness_output("codex", codex_out)
assert res5 is not None, "Failed to parse Codex output"
assert res5[0] == 800 and res5[1] == 120
print("CODEX COST PARSER TEST: PASS")

# 6. Goose: OpenAI-compatible usage block
usages = [
    '{"usage": {"input_tokens": 60, "output_tokens": 40}}',
    '{"usage": {"prompt_tokens": 60, "completion_tokens": 40}}',
]
for goose_out in usages:
    res6 = parse_harness_output("goose", goose_out)
    assert res6 is not None, f"Failed to parse Goose output: {goose_out}"
    assert res6[0] == 60 and res6[1] == 40
print("GOOSE COST PARSER TEST: PASS")

# 7. Unparseable output falls back to None (caller uses the estimate)
assert parse_harness_output("claude", "no usage info here") is None
assert parse_harness_output("claude", "") is None
print("UNPARSEABLE OUTPUT FALLBACK TEST: PASS")

print("\nALL COST TESTS PASSED")
