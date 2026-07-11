"""Redis 连接配置。"""

from __future__ import annotations

import os


def get_host() -> str:
    return os.getenv("REDIS_HOST", "localhost")


def get_port() -> int:
    return int(os.getenv("REDIS_PORT", "6379"))


def get_password() -> str | None:
    value = os.getenv("REDIS_PASSWORD", "")
    return value or None


def get_db() -> int:
    return int(os.getenv("REDIS_DB", "0"))
