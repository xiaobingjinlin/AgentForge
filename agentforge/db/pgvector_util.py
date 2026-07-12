"""pgvector 扩展初始化与连接配置。"""

from __future__ import annotations

import psycopg

PGVECTOR_INSTALL_HINT = (
    "PostgreSQL 未安装 pgvector 扩展。Ubuntu/Debian 示例：\n"
    "  sudo apt install postgresql-14-pgvector   # 版本号与 PG 主版本一致\n"
    "  sudo systemctl restart postgresql\n"
    "安装后重新执行：.venv/bin/python scripts/init_databases.py"
)


def ensure_vector_extension(conn: psycopg.Connection) -> None:
    """在目标库启用 vector 扩展（需数据库已存在）。"""
    with conn.cursor() as cur:
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except psycopg.Error as exc:
            message = str(exc).lower()
            if "extension" in message and "vector" in message:
                raise RuntimeError(PGVECTOR_INSTALL_HINT) from exc
            raise


def configure_vector_connection(conn: psycopg.Connection) -> None:
    """连接池回调：先建扩展，再注册 vector 类型。"""
    conn.autocommit = True
    ensure_vector_extension(conn)
    from pgvector.psycopg import register_vector

    register_vector(conn)
