"""余额追踪：历史记录、delta 计算、token 估算"""

import json
import os
import time
from typing import Optional

from api_client import BalanceData


# ── 定价常量（deepseek-v4-pro）────────────────────────────────────

CNY_PER_USD = 7.25
INPUT_PRICE_PER_1M = 0.435       # 输入价格（USD/百万token）
OUTPUT_PRICE_PER_1M = 0.87       # 输出价格（USD/百万token）
INPUT_OUTPUT_RATIO = 0.75        # 假设输入占比 75%

# 混合价格 = 0.75 * 0.435 + 0.25 * 0.87 = 0.54375 USD/百万token
BLENDED_PRICE_PER_1M = INPUT_OUTPUT_RATIO * INPUT_PRICE_PER_1M + (1 - INPUT_OUTPUT_RATIO) * OUTPUT_PRICE_PER_1M

MAX_HISTORY = 1440               # 24 小时 × 60 次/小时


class BalanceTracker:
    """追踪余额变化，计算预估用量。"""

    def __init__(self, history_path: str):
        self.history_path = history_path
        self.records: list[dict] = []          # [{ts, total, granted, topped_up}, ...]
        self.session_start_ts = time.time()
        self.session_start_total: Optional[float] = None
        self._load()

    # ── 记录余额 ──────────────────────────────────────────────────

    def record(self, balance: BalanceData) -> dict:
        """记录一条余额快照，返回本次记录的信息。"""
        ts = time.time()
        entry = {
            "ts": ts,
            "total": balance.total_balance,
            "granted": balance.granted_balance,
            "topped_up": balance.topped_up_balance,
        }

        # 会话初始余额
        if self.session_start_total is None:
            self.session_start_total = balance.total_balance

        # 避免重复记录（同一秒内不重复）
        if self.records and abs(self.records[-1]["ts"] - ts) < 1:
            # 更新最后一条
            self.records[-1] = entry
        else:
            self.records.append(entry)

        # 裁剪历史
        if len(self.records) > MAX_HISTORY:
            self.records = self.records[-MAX_HISTORY:]

        self._save()
        return entry

    # ── 计算变化 ──────────────────────────────────────────────────

    def get_delta_since_last(self) -> Optional[float]:
        """自上次记录以来的余额变化（负数=消耗）。"""
        if len(self.records) < 2:
            return None
        return self.records[-1]["total"] - self.records[-2]["total"]

    def get_session_delta(self) -> Optional[float]:
        """本次会话的总余额变化。"""
        if not self.records or self.session_start_total is None:
            return None
        return self.records[-1]["total"] - self.session_start_total

    def reset_session(self):
        """重置会话：下次 record() 会重新记录起始余额。"""
        self.session_start_total = None
        self.session_start_ts = time.time()
        self._save()

    def clear_records(self):
        """清空所有历史记录（新任务时调用）。"""
        self.records.clear()
        self.session_start_total = None
        self.session_start_ts = time.time()
        self._save()

    def add_to_session_start(self, amount: float):
        """充值后上调起点，充值金额不计入消耗。"""
        if self.session_start_total is not None:
            self.session_start_total += amount
            self._save()

    # ── Token 估算 ────────────────────────────────────────────────

    def estimate_tokens(self, delta_cny: float) -> int:
        """
        根据 CNY 余额变化估算消耗的 token 数。

        tokens = delta_cny / CNY_USD_RATE / BLENDED_PRICE_PER_1M * 1_000_000
        """
        if delta_cny >= 0:
            return 0
        # 消耗 = 绝对值
        cny_spent = abs(delta_cny)
        tokens = cny_spent / CNY_PER_USD / BLENDED_PRICE_PER_1M * 1_000_000
        return int(tokens)

    def get_hourly_consumption(self, bucket_minutes: int = 5) -> list[dict]:
        """
        获取最近一小时的 token 消耗，按时间分桶。
        桶边界对齐时钟整点（如 10:00, 10:05, 10:10...），避免漂移。

        Returns:
            [{label: "10:00", tokens: 1234, cny: 0.01}, ...]
        """
        now = time.time()
        bucket_secs = bucket_minutes * 60

        # 对齐到下一个整点边界，包含当前进行中的桶
        latest_boundary = ((int(now) // bucket_secs) + 1) * bucket_secs
        cutoff = latest_boundary - 3600
        recent = [r for r in self.records if r["ts"] >= cutoff]

        num_buckets = 60 // bucket_minutes
        buckets = []
        for i in range(num_buckets):
            bucket_end = latest_boundary - i * bucket_secs
            bucket_start = bucket_end - bucket_secs

            bucket_records = [r for r in recent
                            if bucket_start <= r["ts"] < bucket_end]

            tokens = 0
            cny = 0.0
            if len(bucket_records) >= 2:
                delta = bucket_records[0]["total"] - bucket_records[-1]["total"]
                if delta > 0:
                    cny = delta
                    tokens = self.estimate_tokens(-delta)

            # 标签：显示时间段（如 10:05）
            lt = time.localtime(bucket_start)
            label = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
            buckets.append({
                "label": label,
                "tokens": tokens,
                "cny": cny,
            })

        # buckets 已按最旧→最新排列（i=0是最旧的桶），无需反转

        # 反转使时间从左到右递增
        buckets.reverse()
        return buckets

    # ── 持久化 ────────────────────────────────────────────────────

    def _save(self):
        """保存到 JSON 文件。"""
        try:
            os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump({
                    "records": self.records,
                    "session_start_ts": self.session_start_ts,
                    "session_start_total": self.session_start_total,
                }, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def _load(self):
        """从 JSON 文件加载历史。"""
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.records = data.get("records", [])
                self.session_start_ts = data.get("session_start_ts", time.time())
                self.session_start_total = data.get("session_start_total")
                # 裁剪
                if len(self.records) > MAX_HISTORY:
                    self.records = self.records[-MAX_HISTORY:]
        except (json.JSONDecodeError, OSError, KeyError):
            self.records = []
