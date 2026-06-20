"""系统托盘图标（pystray + Pillow）"""

import threading
from typing import Callable, Optional

import pystray

from assets import create_tray_icon


class TrayIcon:
    """Windows 系统托盘图标管理器。"""

    TOOLTIP = "DeepSeek Monitor"

    def __init__(
        self,
        on_show: Optional[Callable] = None,
        on_refresh: Optional[Callable] = None,
        on_exit: Optional[Callable] = None,
    ):
        self._icon: Optional[pystray.Icon] = None
        self._on_show = on_show
        self._on_refresh = on_refresh
        self._on_exit = on_exit
        self._running = False

    def start(self):
        """在后台线程启动托盘图标。"""
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run_tray, daemon=True).start()

    def _run_tray(self):
        """创建并运行托盘图标。"""
        image = create_tray_icon(32)

        menu = pystray.Menu(
            pystray.MenuItem(
                "显示窗口",
                self._handle_show,
                default=True,     # 左键 = 显示
            ),
            pystray.MenuItem(
                "立即刷新",
                self._handle_refresh,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "退出",
                self._handle_exit,
            ),
        )

        self._icon = pystray.Icon(
            "deepseek_monitor",
            image,
            self.TOOLTIP,
            menu,
        )

        self._icon.run()

    # ── 事件处理 ──────────────────────────────────────────────────

    def _handle_show(self, icon=None, item=None):
        """左键/显示菜单：切换窗口可见性。"""
        if self._on_show:
            self._on_show()

    def _handle_refresh(self, icon=None, item=None):
        """立即刷新。"""
        if self._on_refresh:
            self._on_refresh()

    def _handle_exit(self, icon=None, item=None):
        """退出应用。"""
        self._running = False
        self.stop()
        if self._on_exit:
            self._on_exit()

    # ── 生命周期 ──────────────────────────────────────────────────

    def stop(self):
        """停止托盘图标。"""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
