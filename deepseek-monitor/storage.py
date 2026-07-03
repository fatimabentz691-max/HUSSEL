"""
DeepSeek Token 用量监控 — JSON 文件存储
"""

import json
import os
import tempfile
from typing import Any


def get_default_data() -> dict[str, Any]:
    """返回默认数据结构."""
    return {
        "version": 1,
        "model": "deepseek-chat",
        "daily": {},
        "monthly": {},
        "total_all_time": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "requests": 0,
        },
    }


def load_data(filepath: str) -> dict[str, Any]:
    """读 JSON，缺失或损坏则返回默认值."""
    if not os.path.exists(filepath):
        return get_default_data()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return get_default_data()
        defaults = get_default_data()
        for key in defaults:
            if key not in data:
                data[key] = defaults[key]
        return data
    except (json.JSONDecodeError, OSError):
        return get_default_data()


def save_data(filepath: str, data: dict[str, Any]) -> None:
    """原子写入 JSON."""
    dir_name = os.path.dirname(filepath) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_settings(filepath: str) -> dict[str, Any]:
    """加载设置文件，缺失则用默认值创建."""
    defaults = {
        "proxy_port": 7890,
        "model": "deepseek-chat",
        "daily_budget": 1.00,
        "monthly_budget": 30.00,
        "overlay_position": "top-right",
        "refresh_interval_seconds": 2,
    }
    if not os.path.exists(filepath):
        save_data(filepath, defaults)
        return defaults
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            settings = json.load(f)
        for key, value in defaults.items():
            settings.setdefault(key, value)
        return settings
    except (json.JSONDecodeError, OSError):
        return defaults
