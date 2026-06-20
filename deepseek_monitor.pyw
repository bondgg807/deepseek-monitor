"""
DeepSeek Monitor — API 用量桌面挂件
入口文件，组装所有模块，启动主循环。
使用 pythonw 运行可隐藏控制台窗口。
"""

import os
import sys
import ctypes

# ── 任务栏图标 ID（必须在窗口创建前设置） ─────────────────────────
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DeepSeek.Monitor")

# ── 单实例：已有实例 → 激活/闪烁；否则创建互斥锁 ────────────────
_MUTEX_NAME = "DeepSeekMonitor_SingleInstance"
_k32 = ctypes.windll.kernel32
_mutex = _k32.CreateMutexW(None, False, _MUTEX_NAME)
if _k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    # 找到已有窗口并激活
    _hwnd = ctypes.windll.user32.FindWindowW(None, "DeepSeek Monitor")
    if _hwnd:
        ctypes.windll.user32.ShowWindow(_hwnd, 9)  # SW_RESTORE
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p),
                        ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint),
                        ("dwTimeout", ctypes.c_uint)]
        fwi = FLASHWINFO()
        fwi.cbSize = ctypes.sizeof(FLASHWINFO)
        fwi.hwnd = _hwnd
        fwi.dwFlags = 0x00000003 | 0x00000004  # FLASHW_TRAY | FLASHW_TIMER | FLASHW_TIMERNOFG
        fwi.uCount = 4
        fwi.dwTimeout = 120  # 快速闪烁
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(fwi))
        ctypes.windll.user32.SetForegroundWindow(_hwnd)
    sys.exit(0)

# 确保当前目录在 sys.path；PyInstaller 打包后改用 exe 所在目录
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from config_manager import ConfigManager
from api_client import APIClient
from balance_tracker import BalanceTracker
from ui import DeepSeekMonitor, setup_theme
from tray_icon import TrayIcon


def main():
    # ── 路径 ──────────────────────────────────────────────────────
    claude_settings = os.path.expandvars(
        os.path.join(os.environ.get("USERPROFILE", "~"), ".claude", "settings.json")
    )
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    history_path = os.path.join(SCRIPT_DIR, "balance_history.json")

    # ── 初始化模块 ────────────────────────────────────────────────
    config_mgr = ConfigManager(config_path, claude_settings)
    api_client = APIClient()
    balance_tracker = BalanceTracker(history_path)

    # 检查 API Key ──────────────────────────────────────────────────
    # 首次使用：config.json 不存在或没有 key → 弹出输入框
    api_key = config_mgr.get("api_key", "").strip()
    if not api_key:
        # 首次使用：弹出输入框
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        key = tk.simpledialog.askstring(
            "DeepSeek Monitor - 首次配置",
            "请输入你的 DeepSeek API Key：\n（可从 platform.deepseek.com 获取）",
            parent=root,
            show="*",
        )
        root.destroy()
        if key and key.strip().startswith("sk-"):
            config_mgr.set_api_key(key.strip())
            api_key = key.strip()
        else:
            messagebox.showerror("错误", "API Key 无效，程序将退出。\n请重新启动并输入以 sk- 开头的 Key。")
            sys.exit(1)

    # ── 配置主题 ──────────────────────────────────────────────────
    setup_theme()

    # ── 启动 UI ───────────────────────────────────────────────────
    monitor = DeepSeekMonitor(config_mgr, api_client, balance_tracker)

    # ── 系统托盘 ──────────────────────────────────────────────────
    tray = TrayIcon(
        on_show=monitor.toggle_visibility,
        on_refresh=monitor.manual_refresh,
        on_exit=monitor.destroy,
    )

    # 在 UI 准备好后启动托盘和轮询
    def on_ready():
        tray.start()
        monitor.start_polling()

    monitor.after(500, on_ready)

    # ── 主循环 ────────────────────────────────────────────────────
    try:
        monitor.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        tray.stop()


if __name__ == "__main__":
    main()
