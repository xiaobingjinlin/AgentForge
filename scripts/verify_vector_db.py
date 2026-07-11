"""验证 AgentForge PostgreSQL/pgvector 向量库是否可用。"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.core.constants import EMBEDDING_DIM
from agentforge.db.vector_store import VectorStore


def _fake_embedding(seed: float) -> list[float]:
    """生成确定性测试向量，无需真实 Embedding 服务。"""
    values = []
    for i in range(EMBEDDING_DIM):
        values.append(math.sin(seed + i * 0.01))
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def main() -> None:
    print("=" * 60)
    print("AgentForge 向量库连通性验证")
    print("=" * 60)

    store = VectorStore()
    try:
        info = store.ping()
        print(f"✓ 数据库连接成功: {info['database']}")
        print(f"  └─ {info['pg_version']}")
        print(f"  └─ pgvector {info['pgvector_version']}, dim={info['embedding_dim']}")

        store.init_schema()
        print("✓ 向量表结构初始化成功")

        doc_id = "verify-demo"
        store.delete_by_doc_id(doc_id)

        emb_a = _fake_embedding(1.0)
        emb_b = _fake_embedding(1.05)
        emb_q = _fake_embedding(1.02)

        id_a = store.upsert_chunk(
            doc_id=doc_id,
            chunk_index=0,
            content="使用 @RestController 定义 Spring Boot REST 接口",
            embedding=emb_a,
            domain="spring-boot",
            framework_version="3.2",
            source_path="docs/controller.md",
        )
        id_b = store.upsert_chunk(
            doc_id=doc_id,
            chunk_index=1,
            content="Redis 是内存键值数据库",
            embedding=emb_b,
            domain="spring-boot",
            framework_version="3.2",
            source_path="docs/redis.md",
        )
        print(f"✓ 向量写入成功: id={id_a}, id={id_b}")

        results = store.search(emb_q, top_k=2, domain="spring-boot")
        if len(results) < 2:
            raise RuntimeError("向量检索返回结果不足")

        top = results[0]
        print(f"✓ 向量检索成功: 命中 {len(results)} 条")
        print(f"  └─ top1: [{top.similarity:.4f}] {top.content[:40]}...")

        total = store.count_chunks()
        print(f"✓ 当前库内 chunk 总数: {total}")

        deleted = store.delete_by_doc_id(doc_id)
        print(f"✓ 测试数据清理完成: 删除 {deleted} 条")

        print("=" * 60)
        print("全部检查通过，向量库可用")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        store.close()


if __name__ == "__main__":
    main()
