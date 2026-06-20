"""DeepSeek API 客户端：余额查询"""

import time
from dataclasses import dataclass
from typing import Optional

import requests


# ── 数据模型 ─────────────────────────────────────────────────────

@dataclass
class BalanceData:
    """余额数据结构。"""
    is_available: bool
    total_balance: float       # 总余额
    granted_balance: float     # 赠送余额（可能过期）
    topped_up_balance: float   # 充值余额（永不过期）
    currency: str              # CNY / USD


class APIClientError(Exception):
    """统一的 API 错误包装。"""

    def __init__(self, message: str, is_auth_error: bool = False,
                 is_network_error: bool = False, status_code: int = 0):
        super().__init__(message)
        self.message = message
        self.is_auth_error = is_auth_error
        self.is_network_error = is_network_error
        self.status_code = status_code


# ── API 客户端 ───────────────────────────────────────────────────

class APIClient:
    """DeepSeek 平台 API 客户端。"""

    BALANCE_URL = "https://api.deepseek.com/user/balance"
    TIMEOUT = 10           # 请求超时（秒）
    MAX_RETRIES = 2        # 最大重试次数
    RETRY_DELAY = 2        # 重试间隔（秒）

    def fetch_balance(self, api_key: str) -> BalanceData:
        """
        查询账户余额。

        Args:
            api_key: DeepSeek API Key (sk-...)

        Returns:
            BalanceData: 余额信息

        Raises:
            APIClientError: 所有错误统一包装
        """
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        last_error: Optional[Exception] = None

        for attempt in range(1 + self.MAX_RETRIES):
            try:
                resp = requests.get(
                    self.BALANCE_URL,
                    headers=headers,
                    timeout=self.TIMEOUT,
                )

                # 成功
                if resp.status_code == 200:
                    return self._parse_response(resp.json())

                # 认证错误 — 不重试
                if resp.status_code == 401:
                    raise APIClientError(
                        "API Key 无效，请检查后重新配置",
                        is_auth_error=True,
                        status_code=401,
                    )

                # 余额不足
                if resp.status_code == 402:
                    raise APIClientError(
                        "账户余额不足，请充值",
                        status_code=402,
                    )

                # 频率限制 — 重试
                if resp.status_code == 429:
                    last_error = APIClientError(
                        "请求过于频繁，稍后重试",
                        status_code=429,
                    )
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_DELAY * 2)
                    continue

                # 服务器错误 — 重试
                if resp.status_code >= 500:
                    last_error = APIClientError(
                        f"DeepSeek 服务器错误 ({resp.status_code})",
                        status_code=resp.status_code,
                    )
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_DELAY)
                    continue

                # 其他错误
                raise APIClientError(
                    f"API 请求失败 ({resp.status_code}): {resp.text[:200]}",
                    status_code=resp.status_code,
                )

            except requests.exceptions.Timeout:
                last_error = APIClientError(
                    "网络连接超时",
                    is_network_error=True,
                )
            except requests.exceptions.ConnectionError:
                last_error = APIClientError(
                    "无法连接 DeepSeek 服务器",
                    is_network_error=True,
                )
            except APIClientError:
                raise
            except Exception as e:
                last_error = APIClientError(
                    f"未知错误: {str(e)}",
                    is_network_error=True,
                )

            if attempt < self.MAX_RETRIES:
                time.sleep(self.RETRY_DELAY)

        # 重试耗尽
        if isinstance(last_error, APIClientError):
            raise last_error
        raise APIClientError(str(last_error) if last_error else "未知错误",
                            is_network_error=True)

    def _parse_response(self, data: dict) -> BalanceData:
        """解析 API 返回的余额数据。"""
        infos = data.get("balance_infos", [])
        if not infos:
            raise APIClientError("API 返回数据格式异常：缺少 balance_infos")

        info = infos[0]
        return BalanceData(
            is_available=data.get("is_available", True),
            total_balance=float(info.get("total_balance", "0")),
            granted_balance=float(info.get("granted_balance", "0")),
            topped_up_balance=float(info.get("topped_up_balance", "0")),
            currency=info.get("currency", "CNY"),
        )
