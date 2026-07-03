"""
DeepSeek Token 用量监控 — 工具函数
"""

from datetime import datetime, timedelta
from typing import Any


def get_today_key() -> str:
    """返回今天的日期键: 'YYYY-MM-DD'."""
    return datetime.now().strftime("%Y-%m-%d")


def get_month_key() -> str:
    """返回本月键: 'YYYY-MM'."""
    return datetime.now().strftime("%Y-%m")


def get_date_key(days_ago: int = 0) -> str:
    """返回指定天数前的日期键."""
    d = datetime.now() - timedelta(days=days_ago)
    return d.strftime("%Y-%m-%d")


def format_tokens(n: int) -> str:
    """格式化 token 数量."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K"
    else:
        return str(n)


def format_tokens_compact(n: int) -> str:
    """紧凑 token 格式 (用于柱状图标签)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 10_000:
        return f"{n / 1_000:.0f}K"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}K"
    else:
        return str(n)


def format_cost(amount: float) -> str:
    """格式化 USD 费用."""
    if amount >= 1.0:
        return f"${amount:.2f}"
    elif amount >= 0.01:
        return f"${amount:.4f}"
    else:
        return f"${amount:.6f}"


def format_cost_cny(amount: float, rate: float = 7.25) -> str:
    """格式化人民币费用."""
    cny = amount * rate
    if cny >= 1.0:
        return f"¥{cny:.2f}"
    elif cny >= 0.01:
        return f"¥{cny:.4f}"
    else:
        return f"¥{cny:.6f}"


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int = 0,
    reasoning_tokens: int = 0,
    model_pricing: dict[str, float] | None = None,
) -> float:
    """根据 token 数和模型定价计算费用."""
    if model_pricing is None:
        model_pricing = {"input": 0.14, "input_cache_hit": 0.014, "output": 1.10}

    if cache_hit_tokens > 0 or cache_miss_tokens > 0:
        cost_cache_hit = (cache_hit_tokens / 1_000_000) * model_pricing["input_cache_hit"]
        cost_cache_miss = (cache_miss_tokens / 1_000_000) * model_pricing["input"]
        input_cost = cost_cache_hit + cost_cache_miss
    else:
        input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]

    output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
    return input_cost + output_cost


def now_ts() -> str:
    """当前时间戳字符串."""
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    """带时间戳的日志."""
    print(f"[{now_ts()}] {msg}")
