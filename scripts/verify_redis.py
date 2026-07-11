"""验证本地 Redis 是否可用。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.cache.redis_store import RedisStore


def main() -> None:
    print("=" * 60)
    print("AgentForge Redis 连通性验证")
    print("=" * 60)

    store = RedisStore()
    test_key = "verify:ping"
    try:
        info = store.ping()
        print(f"✓ Redis 连接成功: {info['host']}:{info['port']}/{info['db']}")
        print(f"  └─ redis {info['redis_version']}")

        store.set_value(test_key, "ok", ttl_seconds=60)
        value = store.get_value(test_key)
        if value != "ok":
            raise RuntimeError(f"读写不一致: {value!r}")

        print("✓ 缓存读写成功")
        print("=" * 60)
        print("全部检查通过，Redis 可用")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        store.delete(test_key)
        store.close()


if __name__ == "__main__":
    main()
