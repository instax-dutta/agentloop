"""
cost.py — Real cost tracking and usage parsing for AgentLoop.
"""
import json
import re
from typing import Any

# Official pricing per 1 million tokens (USD)
PRICING_TABLE: dict[str, dict[str, float]] = {
    "claude-3-7-sonnet": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "claude-3-5-sonnet": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "claude-3-5-haiku": {"input_per_mtok": 0.80, "output_per_mtok": 4.00},
    "claude-3-opus": {"input_per_mtok": 15.00, "output_per_mtok": 75.00},
    "gpt-4o": {"input_per_mtok": 2.50, "output_per_mtok": 10.00},
    "gpt-4o-mini": {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
    "o1": {"input_per_mtok": 15.00, "output_per_mtok": 60.00},
    "o3-mini": {"input_per_mtok": 1.10, "output_per_mtok": 4.40},
    "deepseek-chat": {"input_per_mtok": 0.14, "output_per_mtok": 0.28},
    "deepseek-coder": {"input_per_mtok": 0.14, "output_per_mtok": 0.28},
}


class CostTracker:
    def __init__(self, running_cost: float = 0.0, iterations: int = 0, by_iter: list[dict[str, Any]] | None = None):
        self.running_cost = running_cost
        self.iterations = iterations
        self.by_iter: list[dict[str, Any]] = by_iter if by_iter is not None else []

    def record_iteration(
        self,
        iter_num: int,
        preset: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        model_name: str | None = None,
        estimated_fallback_cost: float = 0.10,
    ) -> dict[str, Any]:
        """Record usage and cost for an iteration. Returns iter info dict."""
        model = model_name or _default_model_for_preset(preset)
        pricing = PRICING_TABLE.get(model.lower())

        if input_tokens is not None and output_tokens is not None and pricing:
            cost = (input_tokens * pricing["input_per_mtok"] + output_tokens * pricing["output_per_mtok"]) / 1_000_000.0
            is_estimated = False
        else:
            cost = estimated_fallback_cost
            is_estimated = True

        self.running_cost += cost
        self.iterations += 1

        iter_data = {
            "iter": iter_num,
            "preset": preset,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(cost, 6),
            "running_cost": round(self.running_cost, 4),
            "is_estimated": is_estimated,
        }
        self.by_iter.append(iter_data)
        return iter_data

    def to_dict(self) -> dict[str, Any]:
        return {
            "running_cost": round(self.running_cost, 4),
            "iterations": self.iterations,
            "by_iter": self.by_iter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostTracker":
        return cls(
            running_cost=data.get("running_cost", 0.0),
            iterations=data.get("iterations", 0),
            by_iter=data.get("by_iter", []),
        )


def _default_model_for_preset(preset: str) -> str:
    preset_lower = (preset or "").lower()
    if "claude" in preset_lower:
        return "claude-3-7-sonnet"
    if "aider" in preset_lower or "opencode" in preset_lower:
        return "gpt-4o-mini"
    return "gpt-4o-mini"


def parse_harness_output(preset: str, stdout: str) -> tuple[int, int, str | None] | None:
    """Extract (input_tokens, output_tokens, model_name) from harness output. Returns None if unparseable."""
    if not stdout:
        return None

    # Try JSON parsing first
    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            # Standard OpenAI / Anthropic format
            usage = data.get("usage", {})
            if isinstance(usage, dict):
                in_tok = usage.get("input_tokens") or usage.get("prompt_tokens")
                out_tok = usage.get("output_tokens") or usage.get("completion_tokens")
                model = data.get("model")
                if in_tok is not None and out_tok is not None:
                    return int(in_tok), int(out_tok), str(model) if model else None
    except Exception:
        pass

    # Regex search for JSON blocks embedded in stdout
    json_match = re.search(r'\{.*"usage"\s*:\s*\{[^}]+\}.*\}', stdout, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            usage = data.get("usage", {})
            in_tok = usage.get("input_tokens") or usage.get("prompt_tokens")
            out_tok = usage.get("output_tokens") or usage.get("completion_tokens")
            model = data.get("model")
            if in_tok is not None and out_tok is not None:
                return int(in_tok), int(out_tok), str(model) if model else None
        except Exception:
            pass

    # Aider format regex: Tokens: 1.2k sent, 300 received or Tokens: 1200 sent, 300 received
    aider_match = re.search(
        r"Tokens:\s*([\d\.\,\s]+[kM]?)\s*sent,\s*([\d\.\,\s]+[kM]?)\s*received", stdout, re.IGNORECASE
    )
    if aider_match:
        in_tok = _parse_token_count(aider_match.group(1))
        out_tok = _parse_token_count(aider_match.group(2))
        if in_tok is not None and out_tok is not None:
            return in_tok, out_tok, None

    # General token pattern search: e.g. "Tokens: input=1234, output=567"
    gen_match = re.search(
        r"(?:tokens|usage):\s*input[=:]\s*(\d+).*?output[=:]\s*(\d+)", stdout, re.IGNORECASE
    )
    if gen_match:
        return int(gen_match.group(1)), int(gen_match.group(2)), None

    return None


def _parse_token_count(val_str: str) -> int | None:
    val_str = val_str.strip().replace(",", "")
    if not val_str:
        return None
    try:
        if val_str.lower().endswith("k"):
            return int(float(val_str[:-1]) * 1000)
        if val_str.lower().endswith("m"):
            return int(float(val_str[:-1]) * 1_000_000)
        return int(float(val_str))
    except Exception:
        return None
