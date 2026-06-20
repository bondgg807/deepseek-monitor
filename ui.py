"""主界面 — customtkinter 现代风格"""

import ctypes
import math
import os
import threading
import time
import webbrowser
import winsound
from typing import Optional

import customtkinter as ctk

from api_client import BalanceData, APIClientError
from acrylic_effect import apply_mica, apply_dark_titlebar, apply_rounded_corners, get_screen_size
from assets import create_tray_icon

# ── 配色 ──────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0f0f0f",
    "card_bg": "#1a1a1a",
    "card_border": "#2a2a2a",
    "text_primary": "#f0f0f0",
    "text_secondary": "#888888",
    "axis": "#555555",
    "accent_blue": "#4F46E5",
    "accent_green": "#10B981",
    "accent_red": "#EF4444",
    "accent_amber": "#F59E0B",
}

# 条形图渐变色（绿 → 黄 → 紫红）
BAR_GRADIENT_START = (16, 185, 129)    # #10B981 绿
BAR_GRADIENT_MID  = (245, 158, 11)     # #F59E0B 琥珀
BAR_GRADIENT_END  = (239, 68, 68)      # #EF4444 红


def lerp_color(ratio: float) -> str:
    """绿 → 琥珀 → 红 渐变。"""
    if ratio < 0.5:
        t = ratio / 0.5
        r = int(BAR_GRADIENT_START[0] + (BAR_GRADIENT_MID[0] - BAR_GRADIENT_START[0]) * t)
        g = int(BAR_GRADIENT_START[1] + (BAR_GRADIENT_MID[1] - BAR_GRADIENT_START[1]) * t)
        b = int(BAR_GRADIENT_START[2] + (BAR_GRADIENT_MID[2] - BAR_GRADIENT_START[2]) * t)
    else:
        t = (ratio - 0.5) / 0.5
        r = int(BAR_GRADIENT_MID[0] + (BAR_GRADIENT_END[0] - BAR_GRADIENT_MID[0]) * t)
        g = int(BAR_GRADIENT_MID[1] + (BAR_GRADIENT_END[1] - BAR_GRADIENT_MID[1]) * t)
        b = int(BAR_GRADIENT_MID[2] + (BAR_GRADIENT_END[2] - BAR_GRADIENT_MID[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def setup_theme():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


def format_currency(amount: float) -> str:
    return f"¥ {amount:,.2f}"


def format_tokens(count: int) -> str:
    if count >= 1_000_000:
        return f"{count/1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count/1_000:.1f}K"
    return str(count)


def format_time_ago(ts: float) -> str:
    diff = time.time() - ts
    if diff < 60:
        return f"{int(diff)}s"
    elif diff < 3600:
        return f"{int(diff / 60)}m"
    else:
        h = int(diff / 3600)
        m = int((diff % 3600) / 60)
        return f"{h}h{m:02d}m"


# ── 条形图 ────────────────────────────────────────────────────────

class BarChart(ctk.CTkCanvas):
    """近一小时 token 消耗条形图（双缓冲：无闪烁更新）。"""

    HEIGHT = 140         # 图表区高度
    MARGIN_L = 45        # Y 轴留白
    MARGIN_R = 10
    MARGIN_T = 10
    MARGIN_B = 30        # X 轴标签

    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=self.HEIGHT,
                         bg=COLORS["card_bg"], highlightthickness=0, bd=0, **kwargs)
        self._v = 0  # 版本号，用于双缓冲标签
        self._sweep_job = None  # 扫光定时器

    def set_data(self, buckets: list[dict]):
        """buckets: [{label, tokens, cny}, ...] 时间从左到右

        双缓冲：新内容全部画到 v{N} 标签，画完再删 v{N-1}。
        配合 LockWindowUpdate 确保同一帧呈现。
        """
        self._v += 1
        tag = f"v{self._v}"           # 本次绘制的标签
        prev = f"v{self._v - 1}"      # 上次的标签，画完后删除

        w = self.winfo_width()
        if w < 10:
            w = 300
        h = self.HEIGHT

        plot_w = w - self.MARGIN_L - self.MARGIN_R
        plot_h = h - self.MARGIN_T - self.MARGIN_B

        if not buckets or all(b["tokens"] == 0 for b in buckets):
            self.delete("sweep")
            if hasattr(self, '_sweep_job') and self._sweep_job:
                self.after_cancel(self._sweep_job)
                self._sweep_job = None
            self.create_text(w // 2, h // 2, text="近一小时暂无消耗",
                             fill=COLORS["text_secondary"],
                             font=("Microsoft YaHei UI", 10), tags=(tag,))
            self.delete(prev)
            return

        max_tokens = max(b["tokens"] for b in buckets)
        if max_tokens == 0:
            max_tokens = 1

        nice_max = self._nice_ceil(max_tokens)
        scale = plot_h / nice_max

        n = len(buckets)
        bar_gap = 3
        bar_w = max(6, (plot_w - bar_gap * (n - 1)) / n)

        # ── 先画底层：网格虚线（必须在柱子之前创建，确保在柱子下方） ──
        y_ticks = 4
        for i in range(1, y_ticks + 1):
            val = nice_max * i / y_ticks
            yy = self.MARGIN_T + plot_h - val * scale
            self.create_line(self.MARGIN_L, yy, w - self.MARGIN_R, yy,
                             fill="#222222", width=1, dash=(2, 4),
                             tags=(tag,))

        # ── 柱子（在网格线上方） ──
        for i, bucket in enumerate(buckets):
            x = self.MARGIN_L + i * (bar_w + bar_gap)
            bar_h_val = max(0, bucket["tokens"] * scale)
            yy = self.MARGIN_T + plot_h - bar_h_val

            ratio = bucket["tokens"] / nice_max if nice_max > 0 else 0
            color = lerp_color(ratio)

            self.create_rectangle(x, yy, x + bar_w, self.MARGIN_T + plot_h,
                                  fill=color, outline="", width=0,
                                  tags=(tag,))

            # 柱顶标注
            if bucket["tokens"] > 0:
                self.create_text(
                    x + bar_w / 2, yy - 6,
                    text=format_tokens(bucket["tokens"]),
                    fill=COLORS["text_secondary"],
                    font=("Microsoft YaHei UI", 7),
                    anchor="s", tags=(tag,),
                )

            # X 轴标签
            if i % 2 == 0 or n <= 6:
                self.create_text(
                    x + bar_w / 2, self.MARGIN_T + plot_h + 14,
                    text=bucket["label"],
                    fill=COLORS["text_secondary"],
                    font=("Microsoft YaHei UI", 7),
                    anchor="n", tags=(tag,),
                )

        # ── 顶层：Y 轴刻度线 + 标签 + X 轴 ──
        for i in range(y_ticks + 1):
            val = nice_max * i / y_ticks
            yy = self.MARGIN_T + plot_h - val * scale
            self.create_line(self.MARGIN_L - 4, yy, self.MARGIN_L, yy,
                             fill=COLORS["axis"], width=1, tags=(tag,))
            self.create_text(self.MARGIN_L - 6, yy, text=format_tokens(int(val)),
                             fill=COLORS["text_secondary"],
                             font=("Microsoft YaHei UI", 7), anchor="e",
                             tags=(tag,))

        # Y 轴标题
        self.create_text(10, self.MARGIN_T + plot_h // 2,
                         text="tokens", fill=COLORS["text_secondary"],
                         font=("Microsoft YaHei UI", 7), angle=90,
                         tags=(tag,))

        # X 轴 / Y 轴线
        self.create_line(self.MARGIN_L, self.MARGIN_T, self.MARGIN_L,
                         self.MARGIN_T + plot_h, fill=COLORS["axis"], width=1,
                         tags=(tag,))
        self.create_line(self.MARGIN_L, self.MARGIN_T + plot_h,
                         w - self.MARGIN_R, self.MARGIN_T + plot_h,
                         fill=COLORS["axis"], width=1, tags=(tag,))

        # ── 最新柱：从下往上扫光（有数据才启动） ──
        if n > 0 and buckets[-1]["tokens"] > 0:
            last_x = self.MARGIN_L + (n - 1) * (bar_w + bar_gap)
            last_h = buckets[-1]["tokens"] * scale
            bar_color = lerp_color(buckets[-1]["tokens"] / nice_max)
            self._start_sweep(last_x, last_h, bar_w, bar_color)
        else:
            self.delete("sweep")
            if hasattr(self, '_sweep_job') and self._sweep_job:
                self.after_cancel(self._sweep_job)
                self._sweep_job = None

        # ── 原子切换：删除旧版本（扫光由 _start_sweep 自行管理） ──
        self.delete(prev)

    def _start_sweep(self, x: float, bar_h: float, bar_w: float, bar_color: str):
        """最新柱扫光：每帧重建，遮罩裁剪，不出柱。"""
        bottom = self.MARGIN_T + (self.HEIGHT - self.MARGIN_T - self.MARGIN_B)
        strip_h = 24
        speed = 1
        sweep_tag = "sweep"
        bar_top = bottom - bar_h
        br, bg, bb = int(bar_color[1:3], 16), int(bar_color[3:5], 16), int(bar_color[5:7], 16)

        if hasattr(self, '_sweep_job') and self._sweep_job:
            self.after_cancel(self._sweep_job)

        strip_top = [bottom + strip_h]  # 从柱下方开始

        def _anim():
            self.delete(sweep_tag)
            if not self.find_withtag(f"v{self._v}"):
                return
            strip_top[0] -= speed
            if strip_top[0] < bar_top - strip_h:
                strip_top[0] = bottom + strip_h
            # 只在柱范围内画切片，alpha 基于光带位置
            for s in range(int(strip_h * 2)):
                yy = strip_top[0] - s
                if bar_top <= yy < bottom:
                    # t: 0=光带顶部, 1=光带底部
                    t = (strip_top[0] - yy) / strip_h
                    alpha = math.exp(-((t - 0.5) ** 2) / 0.03) * 0.8
                    rr = int(br + (255 - br) * alpha)
                    gg = int(bg + (255 - bg) * alpha)
                    rbb = int(bb + (255 - bb) * alpha)
                    c = f"#{rr:02x}{gg:02x}{rbb:02x}"
                    self.create_rectangle(x, yy, x + bar_w, yy + 1,
                                          fill=c, outline="", tags=(sweep_tag,))
            self._sweep_job = self.after(40, _anim)

        _anim()
    def _nice_ceil(self, val: int) -> int:
        """向上取整到美观刻度，留 15% 余量。"""
        if val <= 0:
            return 100
        val = int(val * 1.15)
        exp = 10 ** (len(str(val)) - 2)
        # 从大到小选，保证 3-6 条刻度线
        steps = [exp * s for s in [10, 5, 2.5, 2, 1]]
        for step in steps:
            ticks = math.ceil(val / step)
            if 3 <= ticks <= 6:
                return ticks * step
        return math.ceil(val / (exp * 10)) * exp * 10


# ── 余额卡片 ──────────────────────────────────────────────────────

class BalanceCard(ctk.CTkFrame):
    """当前余额 + 5分钟变化 + 本次消耗 + 上次任务。"""

    def __init__(self, parent, on_refresh=None, **kwargs):
        super().__init__(parent, fg_color=COLORS["card_bg"],
                         border_color=COLORS["card_border"], border_width=1,
                         corner_radius=10, **kwargs)
        self._on_refresh = on_refresh
        self._previous_total: Optional[float] = None
        self._flash_job = None
        self._cached_recent5m: Optional[float] = None
        self._prev_task_delta: Optional[float] = None
        self._prev_task_tokens: int = 0
        self._spinning = False
        self._pulse_job = None
        self._pulse_phase = 0

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=6)

        # ── 两栏 ──
        cols = ctk.CTkFrame(body, fg_color="transparent")
        cols.pack(fill="x")

        # 左栏
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.pack(side="left", fill="y")

        header = ctk.CTkFrame(left, fg_color="transparent")
        header.pack(fill="x")
        icon = ctk.CTkFrame(header, fg_color="transparent", width=22, height=28)
        icon.pack(side="left")
        icon.pack_propagate(False)
        ctk.CTkLabel(icon, text="💰", font=ctk.CTkFont(size=20)).place(x=-2, rely=0.35, anchor="w")
        ctk.CTkLabel(header, text="当前余额", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_secondary"]).pack(side="left", padx=(0, 0))

        # 金额行：¥ + 刷新图标
        amount_row = ctk.CTkFrame(left, fg_color="transparent")
        amount_row.pack(fill="x")
        self.balance_label = ctk.CTkLabel(
            amount_row, text="--", font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text_primary"])
        self.balance_label.pack(side="left")

        # 刷新图标
        self.refresh_btn = ctk.CTkButton(
            amount_row, text="⟳", font=ctk.CTkFont(size=16),
            fg_color="transparent", hover_color=COLORS["card_bg"],
            text_color=COLORS["text_secondary"],
            border_width=0, width=24, height=24,
            command=self._on_refresh if self._on_refresh else None)
        self.refresh_btn.pack(side="left", padx=(4, 0))
        self._spinning = False
        self._pulse_job = None
        self.refresh_btn.bind("<Enter>", self._on_icon_enter)
        self.refresh_btn.bind("<Leave>", self._on_icon_leave)

        self.consumption_label = ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=10),
            text_color=COLORS["text_secondary"], anchor="w")
        self.consumption_label.pack(fill="x")

        # 右栏
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.pack(side="right", anchor="n")

        self.recent_delta_label = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=10, weight="bold"),
            anchor="e")
        self.recent_delta_label.pack(anchor="e")

        self.prev_task_line1 = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=10),
            text_color=COLORS["text_secondary"], anchor="e")
        self.prev_task_line1.pack(anchor="e")

        self.prev_task_line2 = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=9),
            text_color=COLORS["text_secondary"], anchor="e")
        self.prev_task_line2.pack(anchor="e")

    def set_previous_task(self, delta: float, tokens: int):
        """设置上次任务数据（持久化恢复或新任务创建时调用）。"""
        self._prev_task_delta = delta
        self._prev_task_tokens = tokens
        self._refresh_prev_task_display()

    def get_previous_task(self) -> tuple:
        """返回 (delta, tokens) 供外部持久化。"""
        return (self._prev_task_delta or 0.0, self._prev_task_tokens)

    def _refresh_prev_task_display(self):
        if self._prev_task_delta is not None and self._prev_task_delta < -0.0001:
            self.prev_task_line1.configure(
                text=f"上次任务: -¥ {abs(self._prev_task_delta):,.2f}",
                text_color=COLORS["text_secondary"])
            self.prev_task_line2.configure(
                text=f"({format_tokens(self._prev_task_tokens)} tokens)",
                text_color=COLORS["text_secondary"])
        else:
            self.prev_task_line1.configure(text="")
            self.prev_task_line2.configure(text="")

    def update(self, total: float, session_delta: Optional[float] = None,
               session_tokens: int = 0, recent5m_delta: Optional[float] = None):
        # 闪烁
        if self._previous_total is not None and total != self._previous_total:
            color = COLORS["accent_green"] if total > self._previous_total else COLORS["accent_red"]
            self._flash(color)
        self._previous_total = total

        self.balance_label.configure(text=format_currency(total))

        # 本次消耗
        if session_delta is not None and session_delta < -0.001:
            self.consumption_label.configure(
                text=f"本次消耗: -¥ {abs(session_delta):,.2f}  ({format_tokens(session_tokens)} tokens)",
                text_color=COLORS["text_secondary"])
        elif session_delta is not None and session_delta > 0.001:
            self.consumption_label.configure(
                text=f"本次增加: +¥ {session_delta:,.2f}",
                text_color=COLORS["accent_green"])
        else:
            self.consumption_label.configure(text="暂无消耗")

        # 近5分钟余额变化（有新数据用新的，没新数据用缓存，都没就占位）
        display5m = recent5m_delta if recent5m_delta is not None else self._cached_recent5m
        if display5m is not None:
            if recent5m_delta is not None:
                self._cached_recent5m = recent5m_delta
            if display5m < -0.0001:
                text = f"近5分钟: -¥ {abs(display5m):,.4f}"
                color = COLORS["accent_red"]
            elif display5m > 0.0001:
                text = f"近5分钟: +¥ {display5m:,.4f}"
                color = COLORS["accent_green"]
            else:
                text = "近5分钟: ¥ 0.0000"
                color = COLORS["text_secondary"]
            self.recent_delta_label.configure(text=text, text_color=color)
            self._shine_label(self.recent_delta_label, color)
        else:
            self.recent_delta_label.configure(text="近5分钟: --",
                                              text_color=COLORS["text_secondary"])

    def _on_icon_enter(self, event=None):
        if not self._spinning:
            self.refresh_btn.configure(text_color=COLORS["accent_blue"])
        from tkinter import Toplevel, Label
        self._tooltip_win = Toplevel(self)
        self._tooltip_win.wm_overrideredirect(True)
        self._tooltip_win.attributes("-topmost", True, "-alpha", 0.0)
        x = self.refresh_btn.winfo_rootx() + 24
        y = self.refresh_btn.winfo_rooty() - 6
        self._tooltip_win.wm_geometry(f"+{x}+{y}")
        Label(self._tooltip_win, text="刷新", font=("Microsoft YaHei UI", 8),
              fg="#f0f0f0", bg="#2a2a2a", padx=6, pady=2).pack()
        steps, delay = 10, 1000 // 30
        def _fade(i):
            if i <= steps and hasattr(self, '_tooltip_win') and self._tooltip_win:
                self._tooltip_win.attributes("-alpha", i / steps)
                self.after(delay, lambda: _fade(i + 1))
        _fade(0)

    def _on_icon_leave(self, event=None):
        if not self._spinning:
            self.refresh_btn.configure(text_color=COLORS["text_secondary"])
        if hasattr(self, '_tooltip_win') and self._tooltip_win:
            self._tooltip_win.destroy()
            self._tooltip_win = None

    def _float_animation(self, amount: float, is_positive: bool):
        """浮动动画：透明顶层窗口，全程渐隐到卡片底色。"""
        from tkinter import Toplevel, Label as TkLabel
        sign = "+" if is_positive else "−"
        r1, g1, b1 = (16, 185, 129) if is_positive else (239, 68, 68)
        r2, g2, b2 = 26, 26, 26  # 卡片底色
        text = f"{sign}¥{abs(amount):,.2f}"
        win = Toplevel(self)
        win.wm_overrideredirect(True)
        win.attributes("-topmost", True, "-transparentcolor", COLORS["card_bg"])
        win.configure(bg=COLORS["card_bg"])
        lbl = TkLabel(win, text=text, font=("Microsoft YaHei UI", 16, "bold"),
                      fg=f"#{r1:02x}{g1:02x}{b1:02x}", bg=COLORS["card_bg"])
        lbl.pack()
        bx = self.balance_label.winfo_rootx() + self.balance_label.winfo_width() + 8
        by = self.balance_label.winfo_rooty() + 4
        x = self.winfo_rootx() + (bx - self.winfo_rootx())
        y = self.winfo_rooty() + (by - self.winfo_rooty())
        win.wm_geometry(f"+{x}+{y}")

        steps = 40
        dy = -50
        dt = 25

        def _anim(i):
            if i <= steps:
                t = i / steps
                eased = 0.5 - 0.5 * math.cos(t * math.pi)
                win.wm_geometry(f"+{x}+{int(y + dy * eased)}")
                # 全程渐隐：符号色 → 背景色
                alpha = max(0, 1 - t * 1.2)
                r = int(r2 + (r1 - r2) * alpha)
                g = int(g2 + (g1 - g2) * alpha)
                b = int(b2 + (b1 - b2) * alpha)
                lbl.configure(fg=f"#{r:02x}{g:02x}{b:02x}")
                self.after(dt, lambda: _anim(i + 1))
            else:
                win.destroy()

        _anim(0)

    def show_topup_animation(self, amount: float):
        self._float_animation(amount, True)

    def show_consumption_animation(self, amount: float):
        self._float_animation(amount, False)

    def _shine_label(self, label, base_color=None):
        """文字扫光：阴影视过——本色→暗→本色，3s smoothstep3 双弧。"""
        if base_color is None:
            base_color = COLORS["text_secondary"]
        r1, g1, b1 = int(base_color[1:3], 16), int(base_color[3:5], 16), int(base_color[5:7], 16)
        r2, g2, b2 = 0x2a, 0x2a, 0x2a  # 阴影色
        steps = 200
        def _step(i):
            if i <= steps:
                t = i / steps
                # easeInOutCubic 双弧 pulse: 1→0→1
                def _cubic(x):
                    return 4*x*x*x if x < 0.5 else 1 - pow(-2*x+2, 3)/2
                if t < 0.5:
                    pulse = _cubic(t * 2)
                else:
                    pulse = _cubic(2 - t * 2)
                ease = 1 - pulse
                r = int(r2 + (r1 - r2) * ease)
                g = int(g2 + (g1 - g2) * ease)
                b = int(b2 + (b1 - b2) * ease)
                label.configure(text_color=f"#{r:02x}{g:02x}{b:02x}")
                self.after(25, lambda: _step(i + 1))
        _step(0)

    def spin_icon(self):
        """手动刷新：占位符 + 呼吸脉冲。"""
        self._spinning = True
        self.balance_label.configure(text="¥ **.**", text_color=COLORS["text_secondary"])
        colors = [
            COLORS["text_secondary"],
            "#8888CC",
            COLORS["accent_blue"],
            "#8888CC",
        ]
        self._pulse_phase = 0

        def _pulse():
            if self._spinning:
                i = self._pulse_phase % len(colors)
                self.refresh_btn.configure(text_color=colors[i])
                self._pulse_phase += 1
                self._pulse_job = self.after(120, _pulse)

        _pulse()

    def stop_spin(self):
        """加载完成，恢复静止。"""
        self._spinning = False
        if self._pulse_job:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None
        self.refresh_btn.configure(text_color=COLORS["text_secondary"])

    def _flash(self, color: str):
        self.balance_label.configure(text_color=color)
        if self._flash_job:
            self.after_cancel(self._flash_job)
        self._flash_job = self.after(350, lambda: self.balance_label.configure(
            text_color=COLORS["text_primary"]))


# ── 状态栏 ────────────────────────────────────────────────────────

class StatusBar(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", height=24, **kwargs)
        self.dot_label = ctk.CTkLabel(self, text="●", font=ctk.CTkFont(size=8),
                                      text_color=COLORS["accent_green"], width=14)
        self.dot_label.pack(side="left", padx=(8, 2))
        self.status_text = ctk.CTkLabel(self, text="就绪", font=ctk.CTkFont(size=9),
                                        text_color=COLORS["text_secondary"])
        self.status_text.pack(side="left")
        self.error_detail = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=8),
                                         text_color=COLORS["text_secondary"])
        self.error_detail.pack(side="left", padx=10)

    def set_connected(self, last_ts: Optional[float] = None):
        self.dot_label.configure(text_color=COLORS["accent_green"])
        self.status_text.configure(
            text=f"已连接 · {format_time_ago(last_ts)}" if last_ts else "已连接")
        self.error_detail.configure(text="")

    def set_retrying(self, msg: str = ""):
        self.dot_label.configure(text_color=COLORS["accent_amber"])
        self.status_text.configure(text="重试中")
        self.error_detail.configure(text=msg)

    def set_error(self, msg: str = ""):
        self.dot_label.configure(text_color=COLORS["accent_red"])
        self.status_text.configure(text="连接失败")
        self.error_detail.configure(text=msg)


# ── 主窗口 ────────────────────────────────────────────────────────

class DeepSeekMonitor(ctk.CTk):
    WIDTH = 380
    HEIGHT = 340

    def __init__(self, config_mgr, api_client, balance_tracker, **kwargs):
        super().__init__(**kwargs)
        self._config_mgr = config_mgr
        self._api_client = api_client
        self._balance_tracker = balance_tracker
        self._poll_interval_ms = 60_000
        self._last_update_ts: Optional[float] = None
        self._connected_since_ts: Optional[float] = None
        self._poll_job = None
        self._polling = False

        self.title("DeepSeek Monitor")

        # 设置窗口图标
        try:
            import sys
            if getattr(sys, 'frozen', False):
                base = sys._MEIPASS  # PyInstaller 临时解压目录
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            ico_path = os.path.join(base, "icon.ico")
            if os.path.exists(ico_path):
                self.iconbitmap(default=ico_path)
        except Exception:
            pass
        self.configure(fg_color=COLORS["bg"])
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self._position_window()
        self.minsize(self.WIDTH, self.HEIGHT)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        self._build_ui()
        self.after(100, self._load_previous_task_config)
        self.after(150, self._apply_pin)
        self.after(200, self._apply_acrylic)

    def _apply_pin(self):
        """应用初始状态（不置顶）。"""
        self.attributes("-topmost", False)

    def _apply_acrylic(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            apply_dark_titlebar(hwnd)
            apply_rounded_corners(hwnd)
            apply_mica(hwnd)
        except Exception:
            pass

    def _position_window(self):
        screen_w, screen_h = get_screen_size()
        saved_x = self._config_mgr.get("window_x")
        saved_y = self._config_mgr.get("window_y")
        if saved_x is not None and saved_y is not None:
            x, y = saved_x, saved_y
        else:
            margin = 20
            x = screen_w - self.WIDTH - margin
            y = screen_h - self.HEIGHT - margin - 60
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _save_position(self):
        try:
            self._config_mgr.save_config({
                "window_x": self.winfo_x(), "window_y": self.winfo_y()})
        except Exception:
            pass

    def _build_ui(self):
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(12, 8))

        # 余额卡片
        self.balance_card = BalanceCard(content, on_refresh=self.manual_refresh)
        self.balance_card.pack(fill="x", pady=(0, 8))

        # 条形图（近一小时 token 消耗）
        bar_frame = ctk.CTkFrame(content, fg_color=COLORS["card_bg"],
                                 border_color=COLORS["card_border"],
                                 border_width=1, corner_radius=10)
        bar_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.bar_chart = BarChart(bar_frame)
        self.bar_chart.pack(fill="both", expand=True, padx=6, pady=6)

        # 按钮行
        btn_row = ctk.CTkFrame(content, fg_color="transparent")
        btn_row.pack(fill="x")

        # 新任务：Canvas 正圆 ➕ → 按钮 ＋新任务
        self.task_circle = ctk.CTkCanvas(btn_row, width=28, height=28,
                                          bg=COLORS["bg"], highlightthickness=0, bd=0)
        self.task_circle.pack(side="left", padx=(0, 4))
        self._draw_task_circle()
        self.task_circle.bind("<Button-1>", lambda e: self._on_new_task())
        self.task_circle.bind("<Enter>", self._new_task_enter)
        self.task_circle.bind("<Leave>", self._new_task_leave)
        self._task_expand_job = None
        self._leave_pending = False
        self._task_expanded = False

        # 充值：Canvas 正圆 ￥ → 胶囊 ￥ 充值
        self.recharge_circle = ctk.CTkCanvas(btn_row, width=28, height=28,
                                              bg=COLORS["bg"], highlightthickness=0, bd=0)
        self.recharge_circle.pack(side="left", padx=(4, 0))
        self._draw_recharge_circle()
        self.recharge_circle.bind("<Button-1>", lambda e: self._on_recharge())
        self.recharge_circle.bind("<Enter>", self._recharge_enter)
        self.recharge_circle.bind("<Leave>", self._recharge_leave)
        self._recharge_expand_job = None
        self._recharge_leave_pending = False
        self._low_balance_alerted = False
        self._recharge_flash_job = None
        self._last_recharge_amount = self._config_mgr.get("last_recharge_amount", 0.0)

        # 置顶切换
        self._pinned = False
        self.pin_btn = ctk.CTkButton(
            btn_row, text="📌", font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="#333333",
            text_color=COLORS["text_secondary"],
            corner_radius=8, height=28, width=32,
            command=self._toggle_pin)
        self.pin_btn.pack(side="right")
        self.pin_btn.bind("<Enter>", self._pin_enter)
        self.pin_btn.bind("<Leave>", self._pin_leave)

        # 状态栏
        self.status_bar = StatusBar(self)
        self.status_bar.pack(fill="x", side="bottom")

    # ── 轮询 ──────────────────────────────────────────────────────

    def start_polling(self):
        self._do_poll()
        self._update_time_ago()

    def _do_poll(self):
        if self._polling:
            return
        self._polling = True

        def _thread():
            try:
                api_key = self._config_mgr.get_api_key()
                if not api_key:
                    self.after(0, lambda: self.status_bar.set_error("未配置 API Key"))
                    return
                balance = self._api_client.fetch_balance(api_key)
                self._balance_tracker.record(balance)
                now_ts = time.time()
                self._last_update_ts = now_ts
                if self._connected_since_ts is None:
                    self._connected_since_ts = now_ts
                self.after(0, lambda: self._refresh_ui(balance))
            except APIClientError as e:
                self.after(0, lambda: self._on_error(e))

        threading.Thread(target=_thread, daemon=True).start()
        self._poll_job = self.after(self._poll_interval_ms, self._do_poll)

    def _refresh_ui(self, balance: BalanceData):
        self._polling = False

        session_delta = self._balance_tracker.get_session_delta()
        tokens = self._balance_tracker.estimate_tokens(session_delta or 0) if session_delta and session_delta < 0 else 0
        hourly_buckets = self._balance_tracker.get_hourly_consumption(bucket_minutes=5)

        # 近5分钟变化使用条形图最新桶的数据（与图表同步）
        # None = 没新数据，BalanceCard 保留上次显示值不变
        recent5m = None
        if hourly_buckets:
            newest = hourly_buckets[-1]
            if newest["cny"] > 0:
                recent5m = -newest["cny"]  # 负数=消耗

        # 充值/消耗浮动动画（互斥：充值优先）
        recent = self._balance_tracker.get_delta_since_last()
        if recent is not None:
            if recent > 0.001:
                # 充值
                self._last_recharge_amount = recent
                self._config_mgr.save_config({"last_recharge_amount": recent})
                self.balance_card.show_topup_animation(recent)
                self._balance_tracker.add_to_session_start(recent)
                session_delta = self._balance_tracker.get_session_delta()
            elif recent < -0.001:
                # 消耗
                self.balance_card.show_consumption_animation(recent)

        self.balance_card.update(
            total=balance.total_balance,
            session_delta=session_delta,
            session_tokens=tokens,
            recent5m_delta=recent5m,
        )
        self.bar_chart.set_data(hourly_buckets)
        self.status_bar.set_connected(self._last_update_ts)
        self.balance_card.stop_spin()
        self._check_low_balance(balance.total_balance)

    def _on_error(self, error: APIClientError):
        self._polling = False
        self.balance_card.stop_spin()
        if error.is_auth_error:
            self.status_bar.set_error(error.message)
        elif error.is_network_error:
            self.status_bar.set_retrying(error.message)
        else:
            self.status_bar.set_error(error.message)

    # ── 充值 ──────────────────────────────────────────────────────

    def _on_recharge(self):
        webbrowser.open("https://platform.deepseek.com")

    def _toggle_pin(self):
        """切换窗口置顶状态——📌 亮=置顶，暗=未置顶。"""
        self._pinned = not self._pinned
        self.attributes("-topmost", self._pinned)
        if self._pinned:
            self.pin_btn.configure(text_color="#ffffff", fg_color="#333333")
        else:
            self.pin_btn.configure(text_color=COLORS["text_secondary"], fg_color="transparent")
        if hasattr(self, '_pin_tip') and self._pin_tip:
            self._pin_tip.destroy()
            self._pin_tip = None
            self._pin_enter()
        # 刷新提示文字
        if hasattr(self, '_pin_tip') and self._pin_tip:
            self._pin_tip.destroy()
            self._pin_tip = None
            self._pin_enter()

    def _pin_enter(self, e=None):
        self._pin_want = True
        if hasattr(self, '_pin_tip') and self._pin_tip:
            return
        from tkinter import Toplevel, Label
        self._pin_tip = Toplevel(self)
        self._pin_tip.wm_overrideredirect(True)
        self._pin_tip.attributes("-topmost", True, "-alpha", 0.0)
        x = self.pin_btn.winfo_rootx() - 40
        y = self.pin_btn.winfo_rooty() - 6
        self._pin_tip.wm_geometry(f"+{x}+{y}")
        tip_text = "已置顶" if self._pinned else "置顶"
        Label(self._pin_tip, text=tip_text, font=("Microsoft YaHei UI", 7),
              fg="#f0f0f0", bg="#2a2a2a", padx=4, pady=1).pack()
        # 渐显动画
        steps, delay = 10, 1000 // 30  # 30fps
        def _fade(i):
            if i <= steps and hasattr(self, '_pin_tip') and self._pin_tip:
                self._pin_tip.attributes("-alpha", i / steps)
                self.after(delay, lambda: _fade(i + 1))
        _fade(0)

    def _pin_leave(self, e=None):
        self._pin_want = False
        self.after(80, self._pin_hide_if_gone)

    def _pin_hide_if_gone(self):
        if not getattr(self, '_pin_want', False) and hasattr(self, '_pin_tip') and self._pin_tip:
            self._pin_tip.destroy()
            self._pin_tip = None

    def _check_low_balance(self, balance: float):
        if balance < 5:
            if not self._low_balance_alerted:
                self._low_balance_alerted = True
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                from tkinter import messagebox
                messagebox.showwarning("余额过低", "余额不足 ¥5，请及时充值！")
            self._flash_recharge_btn()
        else:
            self._low_balance_alerted = False
            self._stop_recharge_flash()

    def _flash_recharge_btn(self):
        if self._recharge_flash_job:
            return
        r1, g1, b1 = 255, 149, 0   # orange
        r2, g2, b2 = 255, 204, 0   # yellow
        steps = 200
        step = [0]

        def _smooth():
            if self._low_balance_alerted:
                t = (step[0] % steps) / steps
                # cubic double-arc: 1→0→1
                def _cubic(x):
                    return 4*x*x*x if x < 0.5 else 1 - pow(-2*x+2, 3)/2
                if t < 0.5:
                    pulse = _cubic(t * 2)
                else:
                    pulse = _cubic(2 - t * 2)
                ease = 1 - pulse
                r = int(r2 + (r1 - r2) * ease)
                g = int(g2 + (g1 - g2) * ease)
                b = int(b2 + (b1 - b2) * ease)
                w = int(self.recharge_circle.cget("width"))
                self._draw_animated_circle(self.recharge_circle, w, 28, (r, g, b),
                                            "¥", "¥ 充值", "recharge", icon_size=22, label_size=18)
                step[0] += 1
                self._recharge_flash_job = self.after(25, _smooth)
            else:
                self._stop_recharge_flash()
        _smooth()

    def _stop_recharge_flash(self):
        if self._recharge_flash_job:
            self.after_cancel(self._recharge_flash_job)
            self._recharge_flash_job = None
        self._draw_recharge_circle(int(self.recharge_circle.cget("width")))

    # ── 动画圆按钮（通用） ────────────────────────────────────────

    def _draw_animated_circle(self, canvas, w, h, color, icon, label, key,
                              icon_size=30, label_size=20):
        """PIL 抗锯齿圆 → 胶囊形。"""
        from PIL import Image, ImageDraw, ImageTk, ImageFont
        r = h // 2
        canvas.configure(width=w, height=h)
        s = 2
        img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            f1 = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", icon_size)
            f2 = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", label_size)
        except Exception:
            f1 = ImageFont.load_default()
            f2 = ImageFont.load_default()
        if w <= h + 4:
            draw.ellipse([0, 0, w * s - 1, h * s - 1], fill=color)
            draw.text((w * s // 2, h * s // 2 - 1), icon, fill="#fff", font=f1, anchor="mm")
        else:
            draw.ellipse([0, 0, h * s - 1, h * s - 1], fill=color)
            draw.ellipse([(w - h) * s, 0, w * s - 1, h * s - 1], fill=color)
            draw.rectangle([r * s, 0, (w - r) * s - 1, h * s - 1], fill=color)
            draw.text((w * s // 2, h * s // 2 - 1), label, fill="#fff", font=f2, anchor="mm")
        img = img.resize((w, h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        setattr(self, f"_{key}_img", photo)
        canvas.create_image(0, 0, image=photo, anchor="nw")

    def _circle_expand(self, canvas, color, icon, label, key, base=28, target=76):
        setattr(self, f"_{key}_leave_pending", False)
        job_key = f"_{key}_expand_job"
        if getattr(self, job_key, None):
            self.after_cancel(getattr(self, job_key))
        steps, delay = 15, 13

        def _step(n):
            if getattr(self, f"_{key}_leave_pending", False):
                return
            if n <= steps:
                t = n / steps
                w = int(base + (target - base) * (1 - pow(1 - t, 3)))
                self._draw_animated_circle(canvas, w, 28, color, icon, label, key)
                setattr(self, job_key, self.after(delay, lambda: _step(n + 1)))

        _step(0)

    def _circle_collapse(self, canvas, color, icon, label, key, base=28):
        setattr(self, f"_{key}_leave_pending", True)
        job_key = f"_{key}_expand_job"
        if getattr(self, job_key, None):
            self.after_cancel(getattr(self, job_key))

        def _do():
            if not getattr(self, f"_{key}_leave_pending"):
                return
            w = int(canvas.cget("width"))
            steps, delay = 10, 14

            def _step(n):
                if not getattr(self, f"_{key}_leave_pending"):
                    return
                if n <= steps:
                    t = n / steps
                    cw = int(w + (base - w) * (1 - pow(1 - t, 3)))
                    self._draw_animated_circle(canvas, cw, 28, color, icon, label, key)
                    setattr(self, job_key, self.after(delay, lambda: _step(n + 1)))

            _step(0)

        setattr(self, job_key, self.after(100, _do))

    # ── 新任务按钮 ────────────────────────────────────────────────

    def _draw_task_circle(self, w=28):
        self._draw_animated_circle(self.task_circle, w, 28, (16, 185, 129),
                                    "＋", "＋ 新任务", "task", icon_size=30, label_size=20)

    def _new_task_enter(self, e=None):
        self.task_circle.configure(cursor="hand2")
        self._circle_expand(self.task_circle, (16, 185, 129), "＋", "＋ 新任务", "task")

    def _new_task_leave(self, e=None):
        self.task_circle.configure(cursor="")
        self._circle_collapse(self.task_circle, (16, 185, 129), "＋", "＋ 新任务", "task")

    # ── 充值按钮 ──────────────────────────────────────────────────

    def _draw_recharge_circle(self, w=28):
        self._draw_animated_circle(self.recharge_circle, w, 28, (255, 149, 0),
                                    "¥", "¥ 充值", "recharge", icon_size=22, label_size=18)

    def _recharge_enter(self, e=None):
        self.recharge_circle.configure(cursor="hand2")
        self._circle_expand(self.recharge_circle, (255, 149, 0), "¥", "¥ 充值", "recharge")

    def _recharge_leave(self, e=None):
        self.recharge_circle.configure(cursor="")
        self._circle_collapse(self.recharge_circle, (255, 149, 0), "¥", "¥ 充值", "recharge")

    # ── 新任务 ──────────────────────────────────────────────────────

    def _on_new_task(self):
        from tkinter import messagebox
        ok = messagebox.askokcancel(
            "新任务",
            "确定添加新任务吗？\n余额旧数据会清空，当前消耗将保存为\"上次任务\"。",
            parent=self,
        )
        if not ok:
            return

        # 保存当前 session 为"上次任务"
        session_delta = self._balance_tracker.get_session_delta()
        tokens = 0
        if session_delta and session_delta < 0:
            tokens = self._balance_tracker.estimate_tokens(session_delta)
        delta = session_delta if session_delta else 0.0

        self.balance_card.set_previous_task(delta, tokens)
        self._save_previous_task_config(delta, tokens)

        # 先停掉所有轮询，等当前请求完成，再清空（避免旧数据被加回来）
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self._polling = False
        self._balance_tracker.clear_records()
        self.balance_card._cached_recent5m = None

        # 清空条形图 + 重新拉数据
        self.bar_chart.set_data([])
        self._do_poll()

    def _save_previous_task_config(self, delta: float, tokens: int):
        self._config_mgr.save_config({
            "prev_task_delta": delta,
            "prev_task_tokens": tokens,
        })

    def _load_previous_task_config(self):
        delta = self._config_mgr.get("prev_task_delta")
        tokens = self._config_mgr.get("prev_task_tokens", 0)
        if delta is not None and delta != 0:
            self.balance_card.set_previous_task(delta, tokens)

    def manual_refresh(self):
        self.balance_card.spin_icon()  # 手动刷新显示占位符
        if self._last_recharge_amount and self._last_recharge_amount > 0.001:
            self.balance_card.show_topup_animation(self._last_recharge_amount)
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self._polling = False
        self._do_poll()
    def _update_time_ago(self):
        if self._connected_since_ts:
            ago = format_time_ago(self._connected_since_ts)
            self.status_bar.status_text.configure(text=f"已连接 · {ago}")
        self.after(1000, self._update_time_ago)

    def hide_window(self):
        self._save_position()
        self.withdraw()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def toggle_visibility(self):
        if self.state() == "withdrawn":
            self.show_window()
        else:
            self.hide_window()

    def destroy(self):
        self._save_position()
        if self._poll_job:
            self.after_cancel(self._poll_job)
        super().destroy()
