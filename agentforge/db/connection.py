"""PostgreSQL 连接配置。"""

from __future__ import annotations

import os
from urllib.parse import quote_plus

VECTOR_DATABASE = "agentforge"
META_DATABASE = "agentforge_meta"


def get_user() -> str:
    return os.getenv("POSTGRESQL_USER", os.getenv("PGUSER", "postgres"))


def get_password() -> str:
    return os.getenv("POSTGRESQL_PASSWORD", os.getenv("PGPASSWORD", ""))


def build_dsn(database: str) -> str:
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    user = get_user()
    password = get_password()

    if password:
        encoded = quote_plus(password)
        return f"postgresql://{user}:{encoded}@{host}:{port}/{database}"
    return f"postgresql://{user}@{host}:{port}/{database}"


def build_admin_dsn(database: str = "postgres") -> str:
    """连接管理库（用于建库等运维操作）。"""
    return build_dsn(database)
