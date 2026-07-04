"""
DeepSeek Token Monitor — 悬浮窗
Apple 风格 · 全粗体 · 数字动画过渡 · 极简数据面板
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import math
import tkinter as tk
from typing import Callable, TYPE_CHECKING

import config
from utils import (
    format_tokens, format_tokens_compact, format_cost_cny,
    get_today_key,
)

if TYPE_CHECKING:
    from token_tracker import TokenTracker


F = config.FONT_FAMILY  # 统一字体 — 微软雅黑 UI


def _set_rounded_region(hwnd: int, w: int, h: int, r: int) -> bool:
    try:
        hrgn = ctypes.windll.gdi32.CreateRoundRectRgn(
            0, 0, w + 1, h + 1, r * 2, r * 2)
        ctypes.windll.user32.SetWindowRgn(
            ctypes.wintypes.HWND(hwnd), hrgn, True)
        return True
    except Exception:
        return False


# ── 缓动函数 ────────────────────────────────────────────────

def _ease_out(t: float) -> float:
    """ease-out quad"""
    return 1 - (1 - t) * (1 - t)


def _ease_out_cubic(t: float) -> float:
    """ease-out cubic — 更柔和的减速"""
    return 1 - (1 - t) ** 3


# ── 动画引擎 ────────────────────────────────────────────────

class Animator:
    """轻量级数字动画引擎，基于 tkinter after()"""

    def __init__(self, widget: tk.Widget):
        self._widget = widget
        self._running: dict[str, bool] = {}

    def animate_number(
        self,
        canvas: tk.Canvas,
        item_id: int,
        from_val: float,
        to_val: float,
        formatter: Callable[[float], str],
        font: tuple,
        fill: str,
        anchor: str,
        ox: int | None = None,
        oy: int | None = None,
        steps: int = config.ANIM_STEPS,
        interval: int = config.ANIM_INTERVAL,
    ) -> None:
        """平滑地从 from_val 过渡到 to_val，用缓动函数驱动"""
        key = str(item_id)
        self._running[key] = True

        def _frame(i: int):
            if not self._running.get(key):
                return
            if i >= steps:
                canvas.itemconfig(item_id, text=formatter(to_val))
                return
            t = _ease_out_cubic(i / steps)
            cur = from_val + (to_val - from_val) * t
            canvas.itemconfig(item_id, text=formatter(cur))
            if ox is not None and oy is not None:
                canvas.coords(item_id, ox, oy)
            canvas.after(interval, lambda: _frame(i + 1))

        _frame(0)

    def animate_text(
        self,
        canvas: tk.Canvas,
        item_id: int,
        from_text: str,
        to_text: str,
        font: tuple,
        fill: str,
        anchor: str,
        ox: int | None = None,
        oy: int | None = None,
    ) -> None:
        """瞬间切换文字（数字动画的辅助）"""
        canvas.itemconfig(item_id, text=to_text)
        if ox is not None and oy is not None:
            canvas.coords(item_id, ox, oy)


# ── 解析 token 字符串为数值 (用于动画) ────────────────────

def _parse_token_val(s: str) -> float:
    """'1.2K' -> 1200, '3.5M' -> 3500000, '500' -> 500"""
    s = s.strip()
    if s.endswith("M"):
        return float(s[:-1]) * 1_000_000
    elif s.endswith("K"):
        return float(s[:-1]) * 1_000
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_yuan_val(s: str) -> float:
    """'¥ 1.23' -> 1.23, '¥ 0.0050' -> 0.005"""
    s = s.replace("¥", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


# ── Overlay ───────────────────────────────────────────────────

class OverlayWindow:
    """Apple 风格悬浮数据面板 — 带数字动画"""

    def __init__(
        self,
        tracker: "TokenTracker",
        on_manual_entry: Callable[[], None] | None = None,
        on_toggle_proxy: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ):
        self._tracker = tracker
        self._on_manual_entry = on_manual_entry
        self._on_toggle_proxy = on_toggle_proxy
        self._on_quit = on_quit
        self._drag_x = 0
        self._drag_y = 0
        self._anim = Animator(self.root if False else None)  # placeholder

        W, H = config.COMPACT_WIDTH, config.COMPACT_HEIGHT

        self.root = tk.Tk()
        self.root.title("用量监控")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=config.BG_BASE)

        self._canvas = tk.Canvas(
            self.root, width=W, height=H,
            bg=config.BG_BASE, highlightthickness=0)
        self._canvas.pack(padx=0, pady=0)

        self._anim = Animator(self.root)
        self._W, self._H = W, H
        self._r = config.CORNER_RADIUS

        sw = self.root.winfo_screenwidth()
        self._x = sw - W - config.OVERLAY_MARGIN
        self._y = config.OVERLAY_MARGIN
        self.root.geometry(f"{W}x{H}+{self._x}+{self._y}")

        # 缓存上一次的数值用于动画
        self._prev_today_tokens = 0.0
        self._prev_month_tokens = 0.0
        self._prev_total_tokens = 0.0

        self.root.after(10, self._apply_rounded)
        self._draw()

        self._ctx = tk.Menu(self.root, tearoff=0,
                            bg="#1c1c1e", fg=config.TEXT_PRIMARY,
                            activebackground=config.ACCENT,
                            activeforeground="#ffffff",
                            font=(F, config.S_BASE, "bold"), borderwidth=0, relief="flat")
        self._ctx.add_command(label="手动录入…", command=self._menu_manual)
        self._ctx.add_separator()
        self._ctx.add_command(label="开关代理", command=self._menu_proxy)
        self._ctx.add_separator()
        self._ctx.add_command(label="隐藏到托盘", command=self.hide)
        self._ctx.add_command(label="退出", command=self._menu_quit)
        self._canvas.bind("<Button-3>", self._on_rclick)

    def _apply_rounded(self):
        hwnd = ctypes.windll.user32.GetParent(self._canvas.winfo_id())
        _set_rounded_region(hwnd, self._W, self._H, self._r)

    # ══════ 绘制 ═════════════════════════════════════════════════

    def _draw(self):
        c = self._canvas
        W, H = self._W, self._H
        px = config.PAD_X

        # ── 标题栏 ──────────────────────────────────────────
        hdr_h = 34
        c.create_rectangle(0, 0, W, hdr_h, fill="#0f0f12", outline="")

        dot_y = hdr_h // 2
        for i, clr in enumerate(["#ff5f57", "#ffbd2e", "#28ca42"]):
            c.create_oval(px + i * 14, dot_y - 4, px + i * 14 + 8, dot_y + 4,
                          fill=clr, outline="")

        c.create_text(W // 2, dot_y, text="用量监控",
                      fill=config.TEXT_PRIMARY, anchor="center",
                      font=(F, config.S_BASE, "bold"))

        # 拖拽
        self._drag_rect = c.create_rectangle(0, 0, W, hdr_h,
                                             fill="", outline="", tags="drag")
        c.tag_bind("drag", "<Button-1>", self._on_drag_start)
        c.tag_bind("drag", "<B1-Motion>", self._on_drag_motion)

        cx = W - px
        self._rbtn = c.create_text(cx - 22, dot_y, text="↻",
                                    fill=config.TEXT_MUTED, anchor="center",
                                    font=(F, config.S_BASE + 3, "bold"),
                                    tags="refresh")
        c.tag_bind("refresh", "<Button-1>", lambda e: self.refresh())
        c.tag_bind("refresh", "<Enter>",
                   lambda e: c.itemconfig(self._rbtn, fill=config.ACCENT))
        c.tag_bind("refresh", "<Leave>",
                   lambda e: c.itemconfig(self._rbtn, fill=config.TEXT_MUTED))

        self._close = c.create_text(cx, dot_y, text="×",
                                     fill=config.TEXT_MUTED, anchor="center",
                                     font=(F, config.S_BASE + 4, "bold"),
                                     tags="close")
        c.tag_bind("close", "<Button-1>", lambda e: self.hide())
        c.tag_bind("close", "<Enter>",
                   lambda e: c.itemconfig(self._close, fill=config.RED))
        c.tag_bind("close", "<Leave>",
                   lambda e: c.itemconfig(self._close, fill=config.TEXT_MUTED))

        # ══ 今日用量 — Hero 区域 (大间隙) ═══════════════════
        # 标签 → 数字之间加大间距
        y = hdr_h + 18

        c.create_text(W // 2, y, text="今日用量",
                      fill=config.TEXT_SECONDARY, anchor="center",
                      font=(F, config.S_BASE, "bold"))

        y += 16  # 标签和数字之间的间隙
        self._val_today = c.create_text(
            W // 2, y, text="0",
            fill=config.TEXT_TITLE, anchor="center",
            font=(F, config.S_XL, "bold"))

        y += 40  # 大数字和费用之间的间隙
        self._cost_today = c.create_text(
            W // 2, y, text="¥ 0.00",
            fill=config.TEXT_SECONDARY, anchor="center",
            font=(F, config.S_LG, "bold"))

        y += config.S_LG + 14
        self._req_today = c.create_text(
            W // 2, y, text="0 次请求",
            fill=config.TEXT_MUTED, anchor="center",
            font=(F, config.S_XS, "bold"))

        # ── 分隔 ────────────────────────────────────────────
        y += 24
        c.create_line(px, y, W - px, y, fill=config.BORDER, width=1)
        y += 24

        # ══ 本月用量 ════════════════════════════════════════
        c.create_text(px, y, text="本月用量",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(F, config.S_BASE, "bold"))
        self._val_month = c.create_text(
            W - px, y, text="0 tokens",
            fill=config.TEXT_PRIMARY, anchor="e",
            font=(F, config.S_MD, "bold"))
        y += config.S_MD + 10

        self._cost_month = c.create_text(
            W - px, y, text="¥ 0.00",
            fill=config.TEXT_SECONDARY, anchor="e",
            font=(F, config.S_SM, "bold"))

        y += config.S_SM + 14

        # ══ 累计总计 ════════════════════════════════════════
        c.create_text(px, y, text="累计总计",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(F, config.S_BASE, "bold"))
        self._val_total = c.create_text(
            W - px, y, text="0 tokens",
            fill=config.TEXT_PRIMARY, anchor="e",
            font=(F, config.S_MD, "bold"))
        y += config.S_MD + 10

        self._cost_total = c.create_text(
            W - px, y, text="¥ 0.00",
            fill=config.TEXT_SECONDARY, anchor="e",
            font=(F, config.S_SM, "bold"))

        # ── 分隔 ────────────────────────────────────────────
        y += config.S_SM + 24
        c.create_line(px, y, W - px, y, fill=config.BORDER, width=1)
        y += 24

        # ══ 近 7 天 ════════════════════════════════════════
        c.create_text(px, y, text="近 7 天",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(F, config.S_BASE, "bold"))
        y += config.S_BASE + 16
        self._chart_top = y
        chart_h = 74
        base = y + chart_h - 4
        self._chart_bottom = base + 4
        cl, cr = px + 2, W - px - 2
        self._chart_left, self._chart_right = cl, cr

        c.create_line(cl, base, cr, base, fill="#2c2c30", width=1)
        for frac in (0.5, 1.0):
            gy = int(y + chart_h * 0.7 * (1 - frac))
            c.create_line(cl, gy, cr, gy, fill="#1e1e22", width=1, dash=(4, 8))

        self._bars, self._bar_lbls, self._bar_vals = [], [], []
        n, gap = 7, 12
        tw = cr - cl
        bar_w = (tw - gap * (n - 1)) / n
        for i in range(n):
            bx = cl + i * (bar_w + gap)
            bar = c.create_rectangle(bx, base, bx + bar_w, base,
                                      fill=config.CHART_BAR, outline="",
                                      tags="chart")
            self._bars.append(bar)
            lbl = c.create_text(bx + bar_w / 2, base + 10, text="",
                                fill=config.TEXT_MUTED, anchor="n",
                                font=(F, config.S_BASE - 2, "bold"))
            self._bar_lbls.append(lbl)
            val = c.create_text(bx + bar_w / 2, base, text="",
                                fill=config.TEXT_PRIMARY, anchor="s",
                                font=(F, config.S_XS, "bold"))
            self._bar_vals.append(val)

        self._bar_tip = c.create_text(
            W // 2, self._chart_top - 10, text="",
            fill=config.ACCENT, anchor="s",
            font=(F, config.S_BASE, "bold"))
        c.tag_bind("chart", "<Enter>", self._on_bar_hover)
        c.tag_bind("chart", "<Leave>", self._on_bar_leave)

        # ══ 底部 ════════════════════════════════════════════
        y = self._chart_bottom + config.S_XS + 8
        y += 24
        c.create_line(px, y, W - px, y, fill=config.BORDER, width=1)
        y += 14
        self._footer = c.create_text(
            W // 2, y, text="● 代理运行中",
            fill=config.GREEN, anchor="center",
            font=(F, config.S_XS, "bold"))

    # ══════ 拖拽 ═══════════════════════════════════════════════

    def _on_drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _on_drag_motion(self, e):
        self.root.geometry(
            f"+{self.root.winfo_x() + e.x - self._drag_x}"
            f"+{self.root.winfo_y() + e.y - self._drag_y}")

    # ══════ 菜单 ═══════════════════════════════════════════════

    def _on_rclick(self, e):
        try:
            self._ctx.tk_popup(e.x_root, e.y_root)
        finally:
            self._ctx.grab_release()

    def _menu_manual(self):
        if self._on_manual_entry:
            self._on_manual_entry()

    def _menu_proxy(self):
        if self._on_toggle_proxy:
            self._on_toggle_proxy()

    def _menu_quit(self):
        if self._on_quit:
            self._on_quit()

    # ══════ 图表悬停 ═══════════════════════════════════════════

    def _on_bar_hover(self, e):
        c = self._canvas
        past = self._tracker.get_past_7_days()
        n, gap = 7, 12
        tw = self._chart_right - self._chart_left
        bar_w = (tw - gap * (n - 1)) / n
        for i in range(n):
            bx = self._chart_left + i * (bar_w + gap)
            if bx <= e.x <= bx + bar_w and i < len(past):
                d = past[i]
                c.itemconfig(self._bar_tip,
                             text=f"{d['date']}  {format_tokens(d['total_tokens'])} tokens  {format_cost_cny(d['cost'])}")
                return
        c.itemconfig(self._bar_tip, text="")

    def _on_bar_leave(self, e):
        self._canvas.itemconfig(self._bar_tip, text="")

    # ══════ 刷新 (带动画) ═════════════════════════════════════

    def refresh(self, animated: bool = True):
        c = self._canvas
        W, px = self._W, config.PAD_X
        try:
            today = self._tracker.get_today_stats()
            month = self._tracker.get_month_stats()
            total = self._tracker.get_total_stats()
            past = self._tracker.get_past_7_days()

            today_tokens = today["total_tokens"]
            month_tokens = month["total_tokens"]
            total_tokens = total["total_tokens"]

            today_txt = format_tokens(today_tokens)
            cost_today_txt = format_cost_cny(today["cost"])
            month_txt = f"{format_tokens(month_tokens)} tokens"
            cost_month_txt = format_cost_cny(month["cost"])
            total_txt = f"{format_tokens(total_tokens)} tokens"
            cost_total_txt = format_cost_cny(total["cost"])

            if animated:
                # 今日 Token 数动画
                old_today = self._prev_today_tokens
                self._prev_today_tokens = today_tokens
                self._anim.animate_number(
                    c, self._val_today, old_today, today_tokens,
                    lambda v: format_tokens(int(v)),
                    (F, config.S_XL, "bold"),
                    config.TEXT_TITLE, "center",
                    W // 2, 84)  # 固定坐标防止抖动

                # 今日费用 — 瞬间切换更稳定
                c.itemconfig(self._cost_today, text=cost_today_txt)
                c.itemconfig(self._req_today, text=f"{today['requests']} 次请求")

                # 本月 Token 数动画
                old_month = self._prev_month_tokens
                self._prev_month_tokens = month_tokens
                self._anim.animate_number(
                    c, self._val_month, old_month, month_tokens,
                    lambda v: f"{format_tokens(int(v))} tokens",
                    (F, config.S_MD, "bold"),
                    config.TEXT_PRIMARY, "e",
                    W - px, 182)  # 固定坐标

                c.itemconfig(self._cost_month, text=cost_month_txt)

                # 累计 Token 数动画
                old_total = self._prev_total_tokens
                self._prev_total_tokens = total_tokens
                self._anim.animate_number(
                    c, self._val_total, old_total, total_tokens,
                    lambda v: f"{format_tokens(int(v))} tokens",
                    (F, config.S_MD, "bold"),
                    config.TEXT_PRIMARY, "e",
                    W - px, 230)  # 固定坐标

                c.itemconfig(self._cost_total, text=cost_total_txt)
            else:
                # 无动画 — 直接赋值 + 置位坐标
                c.itemconfig(self._val_today, text=today_txt)
                c.coords(self._val_today, W // 2, 84)
                c.itemconfig(self._cost_today, text=cost_today_txt)
                c.coords(self._cost_today, W // 2, 136)
                c.itemconfig(self._req_today, text=f"{today['requests']} 次请求")
                c.coords(self._req_today, W // 2, 153)

                c.itemconfig(self._val_month, text=month_txt)
                c.coords(self._val_month, W - px, 182)
                c.itemconfig(self._cost_month, text=cost_month_txt)
                c.coords(self._cost_month, W - px, 204)

                c.itemconfig(self._val_total, text=total_txt)
                c.coords(self._val_total, W - px, 230)
                c.itemconfig(self._cost_total, text=cost_total_txt)
                c.coords(self._cost_total, W - px, 252)

            # 预算进度条已移除

            # 近 7 天柱状图
            max_t = max((d.get("total_tokens", 0) for d in past), default=1) or 1
            today_key = get_today_key()
            top, base = self._chart_top, self._chart_bottom - 6
            area_h = max(base - top, 1)
            n, gap = 7, 12
            tw = self._chart_right - self._chart_left
            bar_w = (tw - gap * (n - 1)) / n
            for i, dd in enumerate(past):
                tokens = dd.get("total_tokens", 0)
                dk = dd["date"]
                bh = max(int(area_h * (tokens / max_t)), 4) if tokens > 0 else 0
                bx = self._chart_left + i * (bar_w + gap)
                t = base - bh
                clr = config.CHART_BAR_TODAY if dk == today_key else config.CHART_BAR
                c.coords(self._bars[i], bx, t, bx + bar_w, base)
                c.itemconfig(self._bars[i], fill=clr)
                c.itemconfig(self._bar_lbls[i], text=dk[5:])
                if tokens > 0:
                    c.itemconfig(self._bar_vals[i], text=format_tokens_compact(tokens))
                    c.coords(self._bar_vals[i], bx + bar_w / 2, t - 4)
                else:
                    c.itemconfig(self._bar_vals[i], text="")

        except Exception:
            pass

    def update_proxy_status(self, running, port=7890):
        if running:
            self._canvas.itemconfig(self._footer, text="● 代理运行中", fill=config.GREEN)
        else:
            self._canvas.itemconfig(self._footer, text="● 代理已停止", fill=config.RED)

    def start_refresh_loop(self):
        # 首次刷新不用动画
        self.refresh(animated=False)

        def _loop():
            self.refresh(animated=True)
            self.root.after(config.REFRESH_MS, _loop)

        self.root.after(config.REFRESH_MS, _loop)

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def hide(self):
        self.root.withdraw()

    def is_visible(self):
        return self.root.state() not in ("withdrawn", "iconic")

    def run(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root.mainloop()

    def destroy(self):
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
