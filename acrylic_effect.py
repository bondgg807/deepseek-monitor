"""Windows 11 云母/亚克力窗口特效（通过 ctypes 调用 dwmapi）"""

import ctypes

# ── 常量 ──────────────────────────────────────────────────────────

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_MICA = 1029                    # Windows 11 云母效果
DWMWA_SYSTEMBACKDROP_TYPE = 38       # Win11 22H2+
DWMSBT_MAINWINDOW = 2                # Mica
DWMSBT_TABBEDWINDOW = 4              # Mica Alt

# 颜色常量
DWM_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2                     # 圆角


def apply_mica(hwnd: int) -> bool:
    """
    为窗口应用 Windows 11 云母模糊背景。

    Args:
        hwnd: 窗口句柄（通过 ctypes.windll.user32.GetParent 或 winfo_id 获取）

    Returns:
        是否成功
    """
    try:
        # 尝试 Win11 22H2+ 的 DWM_SYSTEMBACKDROP_TYPE
        dwmapi = ctypes.windll.dwmapi
        hwnd_value = ctypes.c_int(hwnd)

        # 设置云母背景
        backdrop_type = ctypes.c_int(DWMSBT_MAINWINDOW)
        result = dwmapi.DwmSetWindowAttribute(
            hwnd_value,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop_type),
            ctypes.sizeof(backdrop_type),
        )
        if result == 0:
            return True

        # Fallback: 旧版 MICA 属性
        mica = ctypes.c_int(1)
        result = dwmapi.DwmSetWindowAttribute(
            hwnd_value,
            DWMWA_MICA,
            ctypes.byref(mica),
            ctypes.sizeof(mica),
        )
        return result == 0
    except Exception:
        return False


def apply_dark_titlebar(hwnd: int) -> bool:
    """为窗口标题栏应用暗色模式。"""
    try:
        dwmapi = ctypes.windll.dwmapi
        hwnd_value = ctypes.c_int(hwnd)
        dark = ctypes.c_int(1)
        result = dwmapi.DwmSetWindowAttribute(
            hwnd_value,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark),
            ctypes.sizeof(dark),
        )
        return result == 0
    except Exception:
        return False


def apply_rounded_corners(hwnd: int) -> bool:
    """为窗口启用 Win11 圆角。"""
    try:
        dwmapi = ctypes.windll.dwmapi
        hwnd_value = ctypes.c_int(hwnd)
        corner = ctypes.c_int(DWMWCP_ROUND)
        result = dwmapi.DwmSetWindowAttribute(
            hwnd_value,
            DWM_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        )
        return result == 0
    except Exception:
        return False


def get_screen_size() -> tuple:
    """获取主屏幕尺寸。"""
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
    height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return width, height
