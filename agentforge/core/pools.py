"""全局连接池管理。"""

from __future__ import annotations

import psycopg
import redis
from psycopg_pool import ConnectionPool

from agentforge.db.connection import META_DATABASE, VECTOR_DATABASE, build_dsn
from agentforge.db.pgvector_util import configure_vector_connection

DEFAULT_POOL_MIN = 1
DEFAULT_POOL_MAX = 10


def _configure_meta_conn(conn: psycopg.Connection) -> None:
    conn.autocommit = True


class PoolManager:
    """应用级连接池，在 FastAPI lifespan 中初始化和关闭。"""

    _vector_pool: ConnectionPool | None = None
    _meta_pool: ConnectionPool | None = None
    _redis_pool: redis.ConnectionPool | None = None

    @classmethod
    def init(
        cls,
        *,
        min_size: int = DEFAULT_POOL_MIN,
        max_size: int = DEFAULT_POOL_MAX,
    ) -> None:
        if cls._vector_pool is None:
            cls._vector_pool = ConnectionPool(
                conninfo=build_dsn(VECTOR_DATABASE),
                min_size=min_size,
                max_size=max_size,
                configure=_configure_vector_connection,
                open=True,
            )
        if cls._meta_pool is None:
            cls._meta_pool = ConnectionPool(
                conninfo=build_dsn(META_DATABASE),
                min_size=min_size,
                max_size=max_size,
                configure=_configure_meta_conn,
                open=True,
            )
        if cls._redis_pool is None:
            from agentforge.cache.connection import get_db, get_host, get_password, get_port

            cls._redis_pool = redis.ConnectionPool(
                host=get_host(),
                port=get_port(),
                password=get_password(),
                db=get_db(),
                decode_responses=True,
                max_connections=max_size,
            )

    @classmethod
    def close(cls) -> None:
        if cls._vector_pool is not None:
            cls._vector_pool.close()
            cls._vector_pool = None
        if cls._meta_pool is not None:
            cls._meta_pool.close()
            cls._meta_pool = None
        if cls._redis_pool is not None:
            cls._redis_pool.disconnect()
            cls._redis_pool = None

    @classmethod
    def vector_pool(cls) -> ConnectionPool:
        if cls._vector_pool is None:
            raise RuntimeError("连接池未初始化，请先调用 PoolManager.init()")
        return cls._vector_pool

    @classmethod
    def meta_pool(cls) -> ConnectionPool:
        if cls._meta_pool is None:
            raise RuntimeError("连接池未初始化，请先调用 PoolManager.init()")
        return cls._meta_pool

    @classmethod
    def redis_pool(cls) -> redis.ConnectionPool:
        if cls._redis_pool is None:
            raise RuntimeError("连接池未初始化，请先调用 PoolManager.init()")
        return cls._redis_pool
