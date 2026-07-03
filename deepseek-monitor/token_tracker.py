"""
DeepSeek Token 用量监控 — Token 追踪器

核心逻辑：累积 token、计算费用、预算状态
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from utils import compute_cost, get_today_key, get_month_key, get_date_key
from storage import load_data, save_data
import config


class TokenTracker:
    """线程安全的 token 用量追踪器."""

    def __init__(self, data_file: str, settings: dict[str, Any] | None = None):
        self._data_file = data_file
        self._lock = threading.Lock()
        self._data = load_data(data_file)
        self._settings = settings or {}
        self._change_callbacks: list[Callable[[], None]] = []

    # ── 属性 ──────────────────────────────────────────────────────

    @property
    def model(self) -> str:
        return self._data.get("model", config.DEFAULT_MODEL)

    @model.setter
    def model(self, value: str) -> None:
        self._data["model"] = value

    # ── 回调 ──────────────────────────────────────────────────────

    def on_change(self, callback: Callable[[], None]) -> None:
        self._change_callbacks.append(callback)

    def _notify(self) -> None:
        for cb in self._change_callbacks:
            try:
                cb()
            except Exception:
                pass

    # ── 核心：添加用量 ────────────────────────────────────────────

    def add_usage(
        self,
        model: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_hit: int = 0,
        cache_miss: int = 0,
        reasoning: int = 0,
    ) -> None:
        """记录一次 token 使用."""
        model = model or self.model
        total_tokens = prompt_tokens + completion_tokens
        pricing = config.MODELS.get(model, config.MODELS[config.DEFAULT_MODEL])

        cost = compute_cost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit_tokens=cache_hit,
            cache_miss_tokens=cache_miss,
            reasoning_tokens=reasoning,
            model_pricing=pricing,
        )

        with self._lock:
            self._data["model"] = model

            # 每日桶
            today = get_today_key()
            if today not in self._data["daily"]:
                self._data["daily"][today] = self._new_bucket()
            d = self._data["daily"][today]
            self._add_to_bucket(d, prompt_tokens, completion_tokens, total_tokens,
                                cache_hit, cache_miss, reasoning, cost)

            # 每月桶
            month = get_month_key()
            if month not in self._data["monthly"]:
                self._data["monthly"][month] = self._new_bucket()
            m = self._data["monthly"][month]
            self._add_to_bucket(m, prompt_tokens, completion_tokens, total_tokens,
                                cache_hit, cache_miss, reasoning, cost)

            # 总计
            t = self._data["total_all_time"]
            self._add_to_bucket(t, prompt_tokens, completion_tokens, total_tokens,
                                cache_hit, cache_miss, reasoning, cost)

            save_data(self._data_file, self._data)

        self._notify()

    # ── 查询 ──────────────────────────────────────────────────────

    def get_today_stats(self) -> dict[str, Any]:
        today = get_today_key()
        with self._lock:
            return self._data.get("daily", {}).get(today, self._new_bucket()).copy()

    def get_month_stats(self) -> dict[str, Any]:
        month = get_month_key()
        with self._lock:
            return self._data.get("monthly", {}).get(month, self._new_bucket()).copy()

    def get_total_stats(self) -> dict[str, Any]:
        with self._lock:
            return self._data.get("total_all_time", self._new_bucket()).copy()

    def get_past_7_days(self) -> list[dict[str, Any]]:
        """返回过去 7 天 (包括今天) 的每日统计列表 [oldest..today]."""
        result = []
        with self._lock:
            daily = self._data.get("daily", {})
        for i in range(6, -1, -1):
            key = get_date_key(i)
            bucket = daily.get(key, self._new_bucket())
            result.append({"date": key, **bucket.copy()})
        return result

    def get_budget_status(self) -> str:
        month = self.get_month_stats()
        budget = self._settings.get("monthly_budget", config.DEFAULT_MONTHLY_BUDGET)
        cost = month.get("cost", 0.0)
        if budget <= 0:
            return "green"
        ratio = cost / budget
        if ratio < config.BUDGET_GREEN_PCT:
            return "green"
        elif ratio < config.BUDGET_YELLOW_PCT:
            return "yellow"
        else:
            return "red"

    def get_settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def update_settings(self, new_settings: dict[str, Any]) -> None:
        self._settings.update(new_settings)

    # ── 辅助 ──────────────────────────────────────────────────────

    @staticmethod
    def _new_bucket() -> dict[str, Any]:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "requests": 0,
        }

    @staticmethod
    def _add_to_bucket(b: dict, prompt: int, completion: int, total: int,
                       ch: int, cm: int, reasoning: int, cost: float) -> None:
        b["prompt_tokens"] += prompt
        b["completion_tokens"] += completion
        b["total_tokens"] += total
        b["cache_hit_tokens"] += ch
        b["cache_miss_tokens"] += cm
        b["reasoning_tokens"] += reasoning
        b["cost"] += cost
        b["requests"] += 1
