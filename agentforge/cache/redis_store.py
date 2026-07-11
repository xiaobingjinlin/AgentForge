"""Redis 缓存封装。"""

from __future__ import annotations

from typing import Any

import redis

from agentforge.cache.connection import get_db, get_host, get_password, get_port

KEY_PREFIX = "agentforge:"


class RedisStore:
    """AgentForge Redis 缓存封装。"""

    def __init__(
        self,
        pool: redis.ConnectionPool | None = None,
        client: redis.Redis | None = None,
    ) -> None:
        self._pool = pool
        self._client = client
        self._owned_pool: redis.ConnectionPool | None = None

    def _get_client(self) -> redis.Redis:
        if self._client is not None:
            return self._client
        pool = self._pool
        if pool is None:
            try:
                from agentforge.core.pools import PoolManager

                pool = PoolManager.redis_pool()
            except RuntimeError:
                if self._owned_pool is None:
                    self._owned_pool = redis.ConnectionPool(
                        host=get_host(),
                        port=get_port(),
                        password=get_password(),
                        db=get_db(),
                        decode_responses=True,
                        max_connections=5,
                    )
                pool = self._owned_pool
        return redis.Redis(connection_pool=pool)

    def close(self) -> None:
        if self._owned_pool is not None:
            self._owned_pool.disconnect()
            self._owned_pool = None
        self._client = None

    def __enter__(self) -> RedisStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _key(self, key: str) -> str:
        return f"{KEY_PREFIX}{key}"

    def ping(self) -> dict[str, Any]:
        client = self._get_client()
        if not client.ping():
            raise RuntimeError("Redis PING 失败")
        info = client.info("server")
        return {
            "host": get_host(),
            "port": get_port(),
            "db": get_db(),
            "redis_version": info.get("redis_version", "unknown"),
        }

    def set_value(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        client = self._get_client()
        full_key = self._key(key)
        if ttl_seconds:
            client.setex(full_key, ttl_seconds, value)
        else:
            client.set(full_key, value)

    def get_value(self, key: str) -> str | None:
        client = self._get_client()
        return client.get(self._key(key))

    def delete(self, key: str) -> int:
        client = self._get_client()
        return int(client.delete(self._key(key)))
