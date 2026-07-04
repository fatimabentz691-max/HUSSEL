"""
DeepSeek Token Monitor — 手动录入对话框
Apple 风格 · 深邃暗黑 · 毛玻璃层次
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Any, TYPE_CHECKING

import config

if TYPE_CHECKING:
    from token_tracker import TokenTracker


class ManualDialog:
    """手动录入 token 用量对话框 — Apple 深色风格"""

    def __init__(self, parent: tk.Tk, tracker: "TokenTracker",
                 on_submit: Any | None = None):
        self._tracker = tracker
        self._on_submit = on_submit
        self._advanced_visible = False

        self._dlg = tk.Toplevel(parent)
        self._dlg.title("手动录入")
        self._dlg.configure(bg=config.BG_BASE)
        self._dlg.resizable(False, False)
        self._dlg.transient(parent)

        self._dlg.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        dw, dh = 400, 380
        self._dlg.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")
        self._dlg.grab_set()
        self._build()
        self._dlg.protocol("WM_DELETE_WINDOW", self._dlg.destroy)

        self._dlg.after(10, self._apply_dwm_rounded)

    def _build(self) -> None:
        p = {"padx": 16, "pady": 3}

        # 标题
        tk.Label(self._dlg, text="手动录入",
                 bg=config.BG_BASE, fg=config.TEXT_TITLE,
                 font=(config.FONT_FAMILY, config.FONT_SIZE_LG, "bold"),
                 ).pack(fill="x", padx=16, pady=(14, 2))

        tk.Label(self._dlg, text="记录一次 API 请求的 token 消耗",
                 bg=config.BG_BASE, fg=config.TEXT_SECONDARY,
                 font=(config.FONT_FAMILY, config.FONT_SIZE_SM),
                 ).pack(fill="x", padx=16, pady=(0, 12))

        # 模型选择
        self._lbl("模型")
        self._model_var = tk.StringVar(value="deepseek-chat")
        self._combo = ttk.Combobox(
            self._dlg, values=[config.MODELS[m]["label"] for m in config.MODELS],
            state="readonly", font=(config.FONT_FAMILY, config.FONT_SIZE_MD),
        )
        self._combo.pack(fill="x", **p)
        self._combo.current(0)

        # 输入 / 输出 token
        self._lbl("输入 Tokens")
        self._prompt_e = self._entry("0")

        self._lbl("输出 Tokens")
        self._completion_e = self._entry("0")

        # 高级选项
        self._adv_toggle = tk.Label(
            self._dlg, text="▸ 高级（缓存 / 推理）", bg=config.BG_BASE,
            fg=config.ACCENT, cursor="hand2",
            font=(config.FONT_FAMILY, config.FONT_SIZE_SM),
        )
        self._adv_toggle.pack(fill="x", **p)
        self._adv_toggle.bind("<Button-1>", self._toggle_advanced)

        self._adv = tk.Frame(self._dlg, bg=config.BG_BASE)
        self._lbl("缓存命中 Tokens", self._adv)
        self._cache_hit_e = self._entry("0", self._adv)
        self._lbl("缓存未命中 Tokens", self._adv)
        self._cache_miss_e = self._entry("0", self._adv)
        self._lbl("推理 Tokens", self._adv)
        self._reasoning_e = self._entry("0", self._adv)

        # JSON 粘贴
        tk.Label(self._adv, text="或粘贴 usage JSON:",
                 bg=config.BG_BASE, fg=config.TEXT_SECONDARY,
                 font=(config.FONT_FAMILY, config.FONT_SIZE_XS),
                 ).pack(fill="x", padx=16, pady=(8, 1))
        self._paste = tk.Text(self._adv, height=3, bg=config.BG_INPUT,
                               fg=config.TEXT_PRIMARY, relief="flat",
                               insertbackground=config.ACCENT,
                               font=(config.FONT_FAMILY, config.FONT_SIZE_XS))
        self._paste.pack(fill="x", padx=16, pady=(0, 2))
        self._paste.insert("1.0", '{"prompt_tokens":0,"completion_tokens":0}')
        tk.Button(self._adv, text="解析 JSON", command=self._parse_json,
                  bg=config.BG_INPUT, fg=config.ACCENT, relief="flat",
                  activebackground=config.BG_HOVER,
                  activeforeground="#ffffff",
                  font=(config.FONT_FAMILY, config.FONT_SIZE_XS),
                  ).pack(padx=16, pady=4, anchor="e")

        # 按钮栏
        bf = tk.Frame(self._dlg, bg=config.BG_BASE)
        bf.pack(fill="x", padx=16, pady=(16, 14))
        tk.Button(bf, text="取消", command=self._dlg.destroy,
                  bg=config.BG_INPUT, fg=config.TEXT_PRIMARY, relief="flat",
                  activebackground=config.BG_HOVER,
                  activeforeground=config.TEXT_TITLE,
                  font=(config.FONT_FAMILY, config.FONT_SIZE_MD),
                  ).pack(side="right", padx=(8, 0))
        tk.Button(bf, text="确认添加", command=self._on_add,
                  bg=config.ACCENT, fg="#ffffff", relief="flat",
                  activebackground=config.ACCENT_SOFT,
                  font=(config.FONT_FAMILY, config.FONT_SIZE_MD, "bold"),
                  ).pack(side="right")

    # ── 辅助 ────────────────────────────────────────────────────

    def _apply_dwm_rounded(self) -> None:
        try:
            import ctypes, ctypes.wintypes
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            hwnd = ctypes.windll.user32.GetParent(self._dlg.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.wintypes.HWND(hwnd),
                ctypes.c_uint32(DWMWA_WINDOW_CORNER_PREFERENCE),
                ctypes.byref(ctypes.c_uint32(DWMWCP_ROUND)),
                ctypes.sizeof(ctypes.c_uint32),
            )
        except Exception:
            pass

    def _lbl(self, text: str, parent: tk.Widget | None = None) -> None:
        tk.Label(parent or self._dlg, text=text, bg=config.BG_BASE,
                 fg=config.TEXT_SECONDARY,
                 font=(config.FONT_FAMILY, config.FONT_SIZE_SM),
                 ).pack(fill="x", padx=16, pady=(6, 1))

    def _entry(self, default: str, parent: tk.Widget | None = None) -> tk.Entry:
        e = tk.Entry(parent or self._dlg, bg=config.BG_INPUT, fg=config.TEXT_PRIMARY,
                     insertbackground=config.ACCENT, relief="flat",
                     font=(config.FONT_FAMILY, config.FONT_SIZE_MD))
        e.pack(fill="x", padx=16, pady=2)
        e.insert(0, default)
        return e

    def _toggle_advanced(self, event=None) -> None:
        if self._advanced_visible:
            self._adv.pack_forget()
            self._adv_toggle.config(text="▸ 高级（缓存 / 推理）")
        else:
            self._adv.pack(fill="x", after=self._adv_toggle)
            self._adv_toggle.config(text="▾ 高级（缓存 / 推理）")
        self._advanced_visible = not self._advanced_visible

    def _parse_json(self) -> None:
        raw = self._paste.get("1.0", "end-1c").strip()
        try:
            usage = json.loads(raw)
            usage = usage.get("usage", usage)
            self._prompt_e.delete(0, "end")
            self._prompt_e.insert(0, str(usage.get("prompt_tokens", 0)))
            self._completion_e.delete(0, "end")
            self._completion_e.insert(0, str(usage.get("completion_tokens", 0)))
            self._cache_hit_e.delete(0, "end")
            self._cache_hit_e.insert(0, str(usage.get("prompt_cache_hit_tokens", 0)))
            self._cache_miss_e.delete(0, "end")
            self._cache_miss_e.insert(0, str(usage.get("prompt_cache_miss_tokens", 0)))
            ctd = usage.get("completion_tokens_details", {})
            r = ctd.get("reasoning_tokens", 0) if isinstance(ctd, dict) else 0
            self._reasoning_e.delete(0, "end")
            self._reasoning_e.insert(0, str(r))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[对话框] JSON 解析失败: {e}")

    def _on_add(self) -> None:
        try:
            prompt = _p(self._prompt_e.get())
            completion = _p(self._completion_e.get())
            cache_hit = _p(self._cache_hit_e.get())
            cache_miss = _p(self._cache_miss_e.get())
            reasoning = _p(self._reasoning_e.get())
            idx = self._combo.current()
            keys = list(config.MODELS.keys())
            model = keys[idx] if 0 <= idx < len(keys) else "deepseek-chat"

            self._tracker.add_usage(
                model=model, prompt_tokens=prompt,
                completion_tokens=completion, cache_hit=cache_hit,
                cache_miss=cache_miss, reasoning=reasoning,
            )
            if self._on_submit:
                self._on_submit()
        except ValueError:
            pass
        self._dlg.destroy()


def _p(s: str) -> int:
    try:
        return int(s.strip() or "0")
    except ValueError:
        return 0
