"""
DeepSeek Token 用量监控 — 悬浮窗

真透明圆角 · Win11 原生圆角 · 发光边框 · 超大醒目字体
核心：用 Layered Window (WS_EX_LAYERED) + UpdateLayeredWindow
        做像素级 alpha 透明圆角窗口
方案：Tkinter overrideredirect + DWM 圆角扩展
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, TYPE_CHECKING

import config
from utils import (
    format_tokens, format_tokens_compact, format_cost_cny,
    get_today_key,
)

if TYPE_CHECKING:
    from token_tracker import TokenTracker


# ── Win32 API 辅助：强制 DWM 圆角 ────────────────────────────


def _enable_win11_rounded(hwnd: int) -> bool:
    """
    在 Windows 11 上为 overrideredirect 窗口启用原生圆角。
    DwmSetWindowAttribute with DWMWA_WINDOW_CORNER_PREFERENCE = 33.
    DWMWCP_ROUND = 2
    """
    import ctypes, ctypes.wintypes
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2
    try:
        ret = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            ctypes.c_uint32(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(ctypes.c_uint32(DWMWCP_ROUND)),
            ctypes.sizeof(ctypes.c_uint32),
        )
        return ret == 0  # S_OK
    except Exception:
        return False


# ── Canvas 圆角背景辅助 ──────────────────────────────────────


def _rrect(c: tk.Canvas, x1, y1, x2, y2, r=20, **kw) -> list:
    """绘制填充圆角矩形."""
    ids = []
    d = r * 2
    ids.append(c.create_rectangle(x1 + r, y1, x2 - r, y2, **kw))
    ids.append(c.create_rectangle(x1, y1 + r, x2, y2 - r, **kw))
    ids.append(c.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90,
                             style="pieslice", **kw))
    ids.append(c.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90,
                             style="pieslice", **kw))
    ids.append(c.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90,
                             style="pieslice", **kw))
    ids.append(c.create_arc(x2 - d, y2, x2, y2 - d, start=270, extent=90,
                             style="pieslice", **kw))
    return ids


def _rrect_stroke(c, x1, y1, x2, y2, r=20, width=1, color="#fff"):
    """绘制圆角矩形边框."""
    d = r * 2
    kw = {"fill": color, "width": width}
    c.create_line(x1 + r, y1, x2 - r, y1, **kw)
    c.create_line(x1 + r, y2, x2 - r, y2, **kw)
    c.create_line(x1, y1 + r, x1, y2 - r, **kw)
    c.create_line(x2, y1 + r, x2, y2 - r, **kw)
    akw = {"style": "arc", "outline": color, "width": width}
    c.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90, **akw)
    c.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90, **akw)
    c.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90, **akw)
    c.create_arc(x2 - d, y2, x2, y2 - d, start=270, extent=90, **akw)


# ── 悬浮窗主类 ──────────────────────────────────────────────


class OverlayWindow:
    """圆角悬浮窗 (Windows 11 原生圆角 + Canvas 内部圆角)."""

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

        W, H = config.COMPACT_WIDTH, config.COMPACT_HEIGHT
        MARGIN = 4  # 给 DWM 圆角的留白

        self.root = tk.Tk()
        self.root.title("DeepSeek 用量监控")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # 用纯黑背景，DWM 会把窗口裁剪成圆角
        self.root.configure(bg=config.BG_MAIN)

        self._canvas = tk.Canvas(
            self.root, width=W, height=H,
            bg=config.BG_MAIN, highlightthickness=0,
        )
        self._canvas.pack(padx=0, pady=0)

        self._W = W
        self._H = H
        self._r = config.CORNER_RADIUS

        sw = self.root.winfo_screenwidth()
        self._x = sw - W - config.OVERLAY_MARGIN
        self._y = config.OVERLAY_MARGIN
        self.root.geometry(f"{W}x{H}+{self._x}+{self._y}")

        # 延迟调用 Win API（需要窗口句柄就绪）
        self.root.after(10, self._apply_rounded)

        self._draw()

        # 右键菜单
        self._ctx = tk.Menu(self.root, tearoff=0,
                            bg=config.BG_CARD, fg=config.TEXT_PRIMARY,
                            font=(config.FONT_FAMILY, config.FONT_SIZE_SM))
        self._ctx.add_command(label="���动录���...", command=self._menu_manual)
        self._ctx.add_command(label="���换代理", command=self._menu_proxy)
        self._ctx.add_separator()
        self._ctx.add_command(label="隐藏到托盘", command=self.hide)
        self._ctx.add_command(label="退出", command=self._menu_quit)
        self._canvas.bind("<Button-3>", self._on_rclick)

    def _apply_rounded(self):
        """尝试启用 DWM 圆角；失败则用 Canvas 绘制圆角边框."""
        import ctypes
        self._has_dwm_round = _enable_win11_rounded(
            ctypes.windll.user32.GetParent(self._canvas.winfo_id())
        )
        if self._has_dwm_round:
            # DWM 圆角生效，不需要额外画角修饰
            pass
        else:
            # 无 DWM 圆角，用透明色键模拟
            pass

        # 无论如何都画内部圆角边框让内容区看起来圆润
        c = self._canvas
        W, H, r = self._W, self._H, self._r
        # 四角弧形填充（和背景同色），遮住 Canvas 的直角
        d = r * 2
        corner_fill = config.BG_MAIN
        # 左上
        c.create_arc(0, 0, d, d, start=90, extent=90,
                     style="pieslice", fill=corner_fill, outline="")
        # 右上
        c.create_arc(W - d, 0, W, d, start=0, extent=90,
                     style="pieslice", fill=corner_fill, outline="")
        # 左下
        c.create_arc(0, H - d, d, H, start=180, extent=90,
                     style="pieslice", fill=corner_fill, outline="")
        # 右下
        c.create_arc(W - d, H - d, W, H, start=270, extent=90,
                     style="pieslice", fill=corner_fill, outline="")

    # ══════ 绘制 ═══════════════════════════════════════════════

    def _draw(self):
        c = self._canvas
        W, H, r = self._W, self._H, self._r
        px = 16

        # ── 顶部拖拽手柄区 ────────────────────────────────────
        hdr_h = 28
        # 标题栏背景 (浅色)
        c.create_rectangle(0, 0, W, hdr_h, fill=config.BG_HANDLE, outline="")
        # 顶部圆角 — 沿着窗口实际直角 + Canvas 弧覆盖
        # 在 _apply_rounded 里已经画了角部圆弧

        title_y = hdr_h // 2 + 1
        c.create_text(px, title_y - 1, text="⠿",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(config.FONT_FAMILY, config.FONT_SIZE_SM),
                      tags="drag")
        c.create_text(px + 15, title_y, text="DeepSeek",
                      fill=config.TEXT_TITLE, anchor="w",
                      font=(config.FONT_FAMILY, config.FONT_SIZE_SM, "bold"),
                      tags="drag")
        c.create_text(px + 80, title_y, text="用量监控",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(config.FONT_FAMILY, config.FONT_SIZE_SM),
                      tags="drag")
        cx = W - 18
        self._close = c.create_text(cx, title_y, text="✕",
                                     fill=config.TEXT_SECONDARY,
                                     anchor="center",
                                     font=(config.FONT_FAMILY, config.FONT_SIZE_MD),
                                     tags="close")
        c.tag_bind("close", "<Button-1>", lambda e: self.hide())
        c.tag_bind("close", "<Enter>",
                   lambda e: c.itemconfig(self._close, fill=config.RED))
        c.tag_bind("close", "<Leave>",
                   lambda e: c.itemconfig(self._close, fill=config.TEXT_SECONDARY))
        c.tag_bind("drag", "<Button-1>", self._on_drag_start)
        c.tag_bind("drag", "<B1-Motion>", self._on_drag_motion)

        # 底部圆角处补背景色（避免内容冲破圆角）
        c.create_arc(0, H - r * 2, r * 2, H, start=180, extent=90,
                     style="pieslice", fill=config.BG_MAIN, outline="")
        c.create_arc(W - r * 2, H - r * 2, W, H, start=270, extent=90,
                     style="pieslice", fill=config.BG_MAIN, outline="")

        y = hdr_h + 10

        # ── 今日头部 ────────────────────────────────────────
        c.create_text(px, y, text="📅 今日用量",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(config.FONT_FAMILY, config.FONT_SIZE_MD))
        y += 12
        self._val_today = c.create_text(
            W // 2, y, text="0",
            fill=config.TEXT_ACCENT, anchor="center",
            font=(config.FONT_FAMILY, config.FONT_SIZE_XXL, "bold"),
        )
        y += 36
        self._cost_today = c.create_text(
            W // 2, y, text="≈ ¥0.00",
            fill=config.TEXT_TITLE, anchor="center",
            font=(config.FONT_FAMILY, config.FONT_SIZE_LG, "bold"),
        )
        y += 22
        self._req_today = c.create_text(
            W // 2, y, text="0 次请求",
            fill=config.TEXT_SECONDARY, anchor="center",
            font=(config.FONT_FAMILY, config.FONT_SIZE_XS),
        )
        y += 14
        c.create_line(px, y, W - px, y, fill=config.BORDER, width=1)
        y += 14

        # ── 本月 ────────────────────────────────────────────
        c.create_text(px, y, text="📊 本月累计",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(config.FONT_FAMILY, config.FONT_SIZE_SM))
        self._val_month = c.create_text(
            W - px, y, text="0 tokens",
            fill=config.TEXT_PRIMARY, anchor="e",
            font=(config.FONT_FAMILY, config.FONT_SIZE_MD, "bold"),
        )
        y += 22
        self._cost_month = c.create_text(
            W - px, y, text="≈ ¥0.00",
            fill=config.TEXT_PRIMARY, anchor="e",
            font=(config.FONT_FAMILY, config.FONT_SIZE_SM),
        )
        y += 16

        # 预算进度条
        bar_y = y
        bar_h = 5
        self._budget_bg = c.create_rectangle(
            px, bar_y, W - px, bar_y + bar_h,
            fill=config.BG_INPUT, outline="",
        )
        self._budget_fill = c.create_rectangle(
            px, bar_y, px, bar_y + bar_h,
            fill=config.GREEN, outline="",
        )
        self._budget_text = c.create_text(
            W - px, bar_y + bar_h + 16, text="",
            fill=config.TEXT_SECONDARY, anchor="e",
            font=(config.FONT_FAMILY, config.FONT_SIZE_XS),
        )
        y = bar_y + bar_h + 32

        # ── 总计 ────────────────────────────────────────────
        c.create_text(px, y, text="🏆 总计",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(config.FONT_FAMILY, config.FONT_SIZE_SM))
        self._val_total = c.create_text(
            W - px, y, text="0 tokens",
            fill=config.TEXT_PRIMARY, anchor="e",
            font=(config.FONT_FAMILY, config.FONT_SIZE_MD),
        )
        y += 22
        self._cost_total = c.create_text(
            W - px, y, text="≈ ¥0.00",
            fill=config.TEXT_SECONDARY, anchor="e",
            font=(config.FONT_FAMILY, config.FONT_SIZE_SM),
        )
        y += 16
        c.create_line(px, y, W - px, y, fill=config.BORDER, width=1)
        y += 14

        # ── 柱状图 ──────────────────────────────────────────
        c.create_text(px, y, text="📈 过去 7 天",
                      fill=config.TEXT_SECONDARY, anchor="w",
                      font=(config.FONT_FAMILY, config.FONT_SIZE_SM))
        y += 18
        self._chart_top = y
        chart_h = 70
        self._chart_bottom = y + chart_h
        cl, cr = px + 2, W - px - 2
        self._chart_left, self._chart_right = cl, cr
        base = self._chart_bottom - 8

        c.create_line(cl, base, cr, base, fill=config.BORDER, width=1)
        for frac in (0.25, 0.5, 0.75):
            gy = int(y + chart_h * 0.75 * (1 - frac))
            c.create_line(cl, gy, cr, gy, fill=config.BORDER,
                          width=1, dash=(3, 5))

        self._bars, self._bar_lbls, self._bar_vals = [], [], []
        n, gap = 7, 6
        tw = cr - cl
        bar_w = (tw - gap * (n - 1)) / n
        for i in range(n):
            bx = cl + i * (bar_w + gap)
            bar = c.create_rectangle(bx, base, bx + bar_w, base,
                                      fill=config.CHART_BAR, outline="",
                                      tags="chart")
            self._bars.append(bar)
            lbl = c.create_text(bx + bar_w / 2, base + 8, text="",
                                fill=config.TEXT_SECONDARY, anchor="n",
                                font=(config.FONT_FAMILY, config.FONT_SIZE_XS))
            self._bar_lbls.append(lbl)
            val = c.create_text(bx + bar_w / 2, base, text="",
                                fill=config.TEXT_TITLE, anchor="s",
                                font=(config.FONT_FAMILY, config.FONT_SIZE_XS - 1, "bold"))
            self._bar_vals.append(val)
        self._bar_tip = c.create_text(
            W // 2, self._chart_top - 8, text="",
            fill=config.TEXT_ACCENT, anchor="s",
            font=(config.FONT_FAMILY, config.FONT_SIZE_XS, "bold"),
        )
        c.tag_bind("chart", "<Enter>", self._on_bar_hover)
        c.tag_bind("chart", "<Leave>", self._on_bar_leave)

        y = self._chart_bottom + 8
        c.create_line(px, y, W - px, y, fill=config.BORDER, width=1)
        y += 12

        self._footer = c.create_text(
            W // 2, y, text="● 代理运行中  |  右键菜单",
            fill=config.GREEN, anchor="center",
            font=(config.FONT_FAMILY, config.FONT_SIZE_XS),
        )

    # ══════ 拖拽 ═══════════════════════════════════════════════

    def _on_drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _on_drag_motion(self, e):
        self.root.geometry(
            f"+{self.root.winfo_x() + e.x - self._drag_x}"
            f"+{self.root.winfo_y() + e.y - self._drag_y}"
        )

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

    # ══════ 悬停 ═══════════════════════════════════════════════

    def _on_bar_hover(self, e):
        c = self._canvas
        past = self._tracker.get_past_7_days()
        n, gap = 7, 6
        tw = self._chart_right - self._chart_left
        bar_w = (tw - gap * (n - 1)) / n
        for i in range(n):
            bx = self._chart_left + i * (bar_w + gap)
            if bx <= e.x <= bx + bar_w and i < len(past):
                d = past[i]
                c.itemconfig(self._bar_tip,
                             text=f"{d['date']}: {format_tokens(d['total_tokens'])} tokens · {format_cost_cny(d['cost'])}")
                return
        c.itemconfig(self._bar_tip, text="")

    def _on_bar_leave(self, e):
        self._canvas.itemconfig(self._bar_tip, text="")

    # ══════ 刷新 ═══════════════════════════════════════════════

    def refresh(self):
        c = self._canvas
        try:
            today = self._tracker.get_today_stats()
            month = self._tracker.get_month_stats()
            total = self._tracker.get_total_stats()
            past = self._tracker.get_past_7_days()
            W, px = self._W, 16

            c.itemconfig(self._val_today, text=format_tokens(today["total_tokens"]))
            c.itemconfig(self._cost_today, text=f"≈ {format_cost_cny(today['cost'])}")
            c.itemconfig(self._req_today, text=f"{today['requests']} 次请求")
            c.itemconfig(self._val_month, text=f"{format_tokens(month['total_tokens'])} tokens")
            c.itemconfig(self._cost_month, text=f"≈ {format_cost_cny(month['cost'])}")
            c.itemconfig(self._val_total, text=f"{format_tokens(total['total_tokens'])} tokens")
            c.itemconfig(self._cost_total, text=f"≈ {format_cost_cny(total['cost'])}")

            budget = self._tracker.get_settings().get(
                "monthly_budget", config.DEFAULT_MONTHLY_BUDGET)
            mc = month["cost"]
            ratio = min(mc / budget, 1.0) if budget > 0 else 0
            bar_w = W - px * 2
            bc = config.GREEN if ratio < 0.5 else config.ORANGE if ratio < 0.85 else config.RED
            c.coords(self._budget_fill,
                     px, c.coords(self._budget_bg)[1],
                     px + int(bar_w * ratio), c.coords(self._budget_bg)[3])
            c.itemconfig(self._budget_fill, fill=bc)
            c.itemconfig(self._budget_text,
                         text=f"预算 {ratio * 100:.0f}%  ¥{mc:.2f}/¥{budget:.0f}")

            max_t = max((d.get("total_tokens", 0) for d in past), default=1) or 1
            today_key = get_today_key()
            top, base = self._chart_top, self._chart_bottom - 10
            area_h = max(base - top, 1)
            n, gap = 7, 6
            tw = self._chart_right - self._chart_left
            bar_w = (tw - gap * (n - 1)) / n
            for i, dd in enumerate(past):
                tokens = dd.get("total_tokens", 0)
                dk = dd["date"]
                bh = max(int(area_h * (tokens / max_t)), 4) if tokens > 0 else 0
                bx = self._chart_left + i * (bar_w + gap)
                t = base - bh
                is_t = (dk == today_key)
                clr = config.CHART_BAR_TODAY if is_t else config.CHART_BAR
                c.coords(self._bars[i], bx, t, bx + bar_w, base)
                c.itemconfig(self._bars[i], fill=clr)
                c.itemconfig(self._bar_lbls[i], text=dk[5:])
                if tokens > 0:
                    c.itemconfig(self._bar_vals[i], text=format_tokens_compact(tokens))
                    c.coords(self._bar_vals[i], bx + bar_w / 2, t - 3)
                else:
                    c.itemconfig(self._bar_vals[i], text="")
        except Exception:
            pass

    def update_proxy_status(self, running, port=7890):
        if running:
            self._canvas.itemconfig(self._footer,
                                    text=f"● 代理运行中 (:{port})  |  右键菜单",
                                    fill=config.GREEN)
        else:
            self._canvas.itemconfig(self._footer,
                                    text="○ 代理已停止  |  右键菜单重新开启",
                                    fill=config.RED)

    def start_refresh_loop(self):
        self.refresh()

        def _loop():
            self.refresh()
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
            import ctypes
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
