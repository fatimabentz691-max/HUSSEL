"""
DeepSeek Token 用量监控 — 入口

启动悬浮窗、系统托盘、反向代理
"""

from __future__ import annotations

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import load_settings
from token_tracker import TokenTracker
from proxy_server import ProxyServer
from overlay import OverlayWindow
from tray_icon import TrayManager
import config


def main() -> None:
    settings = load_settings(config.SETTINGS_FILE)
    data_file = settings.get("data_file", config.DATA_FILE)
    if not os.path.isabs(data_file):
        data_file = os.path.join(config.BASE_DIR, data_file)

    tracker = TokenTracker(data_file, settings)
    proxy = ProxyServer(
        tracker,
        port=settings.get("proxy_port", config.DEFAULT_PROXY_PORT),
        host=settings.get("proxy_host", config.PROXY_HOST),
    )

    shutdown_flag = threading.Event()

    def on_manual_entry() -> None:
        from manual_dialog import ManualDialog
        ManualDialog(overlay.root, tracker, on_submit=lambda: overlay.refresh())

    def on_toggle_proxy() -> None:
        if proxy.is_running:
            proxy.stop()
        else:
            proxy.restart()
        overlay.update_proxy_status(proxy.is_running, proxy.port)

    def on_quit() -> None:
        shutdown_flag.set()
        proxy.stop()
        tray.stop()
        overlay.destroy()

    overlay = OverlayWindow(
        tracker,
        on_manual_entry=on_manual_entry,
        on_toggle_proxy=on_toggle_proxy,
        on_quit=on_quit,
    )

    tray = TrayManager(overlay, proxy, tracker, on_quit=on_quit)

    proxy.start()
    overlay.update_proxy_status(True, proxy.port)

    tray_thread = threading.Thread(target=tray.run, daemon=True, name="tray")
    tray_thread.start()

    overlay.start_refresh_loop()

    try:
        overlay.run()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_flag.set()
        proxy.stop()
        tray.stop()


if __name__ == "__main__":
    main()
