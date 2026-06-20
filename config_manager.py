"""配置管理：API Key 自动发现 + 配置文件读写"""

import json
import os
from typing import Optional


class ConfigManager:
    """管理 API Key 发现、配置文件读写。"""

    def __init__(self, config_path: str, claude_settings_path: str):
        self.config_path = config_path
        self.claude_settings_path = claude_settings_path
        self._config = {}
        self._load_config()

    # ── API Key 自动发现 ──────────────────────────────────────────

    def get_api_key(self) -> Optional[str]:
        """
        按优先级查找 API Key：
        1. config.json 手动配置的 api_key
        2. Claude settings.json 中的 ANTHROPIC_AUTH_TOKEN
        3. 环境变量 DEEPSEEK_API_KEY
        4. 环境变量 ANTHROPIC_AUTH_TOKEN
        """
        # 1. 手动配置
        key = self._config.get("api_key", "").strip()
        if key:
            return key

        # 2. Claude settings.json
        key = self._read_from_claude_settings()
        if key:
            return key

        # 3. 环境变量
        for var in ("DEEPSEEK_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            key = os.environ.get(var, "").strip()
            if key:
                return key

        return None

    def _read_from_claude_settings(self) -> Optional[str]:
        """从 Claude Code 的 settings.json 中提取 API Key。"""
        try:
            if not os.path.exists(self.claude_settings_path):
                return None
            with open(self.claude_settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # settings.json 中的 env 字段是扁平 key: "env.ANTHROPIC_AUTH_TOKEN"
            for key, value in data.items():
                if key == "env" and isinstance(value, dict):
                    token = value.get("ANTHROPIC_AUTH_TOKEN", "")
                    if token and token.startswith("sk-"):
                        return token
            return None
        except (json.JSONDecodeError, OSError):
            return None

    # ── 配置读写 ──────────────────────────────────────────────────

    def _load_config(self):
        """加载本地配置文件。"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._config = {}

    def save_config(self, updates: dict):
        """合并更新并保存配置。"""
        self._config.update(updates)
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def set_api_key(self, key: str):
        """手动设置 API Key 并持久化。"""
        self.save_config({"api_key": key})
