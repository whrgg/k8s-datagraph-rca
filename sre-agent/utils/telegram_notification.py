"""Telegram 通知：在配置了凭证时将日志与消息推送到 Telegram。"""

import logging
import os
from logging import Handler
from typing import Optional

import requests


class TelegramNotification:
    """在配置了 TELEGRAM_TOKEN 与 TELEGRAM_CHAT_ID 时发送 Telegram 消息。"""

    def __init__(self, chat_id: Optional[str] = None, token: Optional[str] = None) -> None:
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        self.logger = logging.getLogger(__name__)

    @property
    def enabled(self) -> bool:
        """当 token 与 chat_id 均可用时返回 True。"""
        return bool(self.chat_id and self.token)

    def _ensure_configured(self) -> None:
        if not self.enabled:
            raise RuntimeError(
                "TelegramNotification 需要环境变量 TELEGRAM_CHAT_ID 与 TELEGRAM_TOKEN。"
            )

    def send_telegram_message(self, message: str) -> None:
        """向配置的聊天发送文本消息。"""
        self._ensure_configured()

        # Telegram 消息长度上限为 4096 个字符。
        truncated_message = message if len(message) <= 4096 else f"{message[:4050]}…"

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": truncated_message,
        }
        try:
            response = requests.post(url, data=data, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.logger.error("发送 Telegram 消息失败：%s", exc)

    def create_log_handler(self, level: int = logging.ERROR) -> Handler:
        """返回将日志记录转发到 Telegram 的 Handler。"""
        self._ensure_configured()

        class _TelegramLogHandler(logging.Handler):
            def __init__(self, notifier: "TelegramNotification", handler_level: int) -> None:
                super().__init__(handler_level)
                self._notifier = notifier

            def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
                try:
                    msg = self.format(record)
                    self._notifier.send_telegram_message(
                        f"🚨 {record.levelname} | {record.name}\n{msg}"
                    )
                except Exception:  # pragma: no cover - 防御性处理
                    self.handleError(record)

        return _TelegramLogHandler(self, level)
