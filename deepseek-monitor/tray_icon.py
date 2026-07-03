"""
DeepSeek Token 用量监控 — 系统托盘图标

左键点击切换悬浮窗显示/隐藏，右键展开菜单
"""

from __future__ import annotations

import threading
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from overlay import OverlayWindow
    from proxy_server import ProxyServer
    from token_tracker import TokenTracker


class TrayManager:
    """系统托盘管理器."""

    def __init__(
        self,
        overlay: "OverlayWindow",
        proxy: "ProxyServer",
        tracker: "TokenTracker",
        on_quit: Callable[[], None] | None = None,
    ):
        self._overlay = overlay
        self._proxy = proxy
        self._tracker = tracker
        self._on_quit = on_quit
        self._icon = None

    def _create_image(self):
        """生成 'DS' 托盘图标."""
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([1, 1, 30, 30], radius=7,
                               fill="#1e1e2e", outline="#45475a", width=1)
        draw.text((7, 5), "DS", fill="#89b4fa")
        return img

    def _build_menu(self):
        import pystray
        return pystray.Menu(
            pystray.MenuItem("显示/隐藏", self._toggle_overlay, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "代理状态",
                pystray.Menu(
                    pystray.MenuItem(
                        "运行中", self._noop,
                        checked=lambda item: self._proxy.is_running,
                    ),
                ),
            ),
            pystray.MenuItem("手动录入...", self._trigger_manual),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit),
        )

    def _toggle_overlay(self, icon, item) -> None:
        self._root_after(lambda: (
            self._overlay.hide() if self._overlay.is_visible()
            else self._overlay.show()
        ))

    def _trigger_manual(self, icon, item) -> None:
        self._root_after(lambda: self._show_manual())

    def _quit(self, icon, item) -> None:
        if self._on_quit:
            self._root_after(self._on_quit)

    def _noop(self, icon, item) -> None:
        pass

    def _root_after(self, callback) -> None:
        try:
            self._overlay.root.after(0, callback)
        except Exception:
            pass

    def _show_manual(self) -> None:
        from manual_dialog import ManualDialog
        ManualDialog(
            self._overlay.root, self._tracker,
            on_submit=lambda: self._overlay.refresh(),
        )

    def run(self) -> None:
        import pystray
        self._icon = pystray.Icon(
            "deepseek_monitor",
            self._create_image(),
            "DeepSeek 用量监控",
            self._build_menu(),
        )
        self._icon.run()

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
