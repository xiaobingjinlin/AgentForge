"""验证 RAG 知识库：入库、域内检索、rerank。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.db.vector_store import VectorStore
from agentforge.core.constants import EMBEDDING_DIM
from agentforge.rag.indexer import CorpusIndexer
from agentforge.rag.retriever import RagRetriever


def _ensure_schema(store: VectorStore) -> None:
    try:
        store.init_schema()
    except Exception:
        migrate_sql = Path(__file__).resolve().parents[1] / "sql" / "migrate_rag_embedding_dim.sql"
        if migrate_sql.exists():
            with open(migrate_sql, encoding="utf-8") as f:
                sql = f.read()
            with store._get_pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
        else:
            raise


def main() -> None:
    print("=" * 60)
    print("AgentForge RAG 知识库验证")
    print("=" * 60)

    store = VectorStore()
    try:
        info = store.ping()
        print(f"✓ 向量库连接: {info['database']} (dim={EMBEDDING_DIM})")

        _ensure_schema(store)

        if store.count_chunks() < 5:
            print("… 知识库为空，开始入库…")
            stats = CorpusIndexer(store=store).index_spring_boot(framework_version="4.0")
            print(f"✓ 入库 chunk: {stats.chunks_indexed}")
        else:
            print(f"✓ 已有 chunk: {store.count_chunks()}")

        retriever = RagRetriever(store=store, use_cache=False)
        query = "Spring Boot 如何创建 REST Controller CRUD 接口"
        hits = retriever.retrieve(
            query,
            domain="controller",
            framework_version="4.0",
            top_k=6,
            rerank_top_n=2,
        )
        if not hits:
            raise RuntimeError("检索无结果")

        top = hits[0]
        print(f"✓ 域内检索+rerank: {len(hits)} 条")
        print(f"  └─ top1: {top.source_path}")
        print(f"  └─ preview: {top.content[:80].replace(chr(10), ' ')}...")

        controller_hits = [h for h in hits if h.domain == "controller" or "controller" in (h.source_path or "")]
        if not controller_hits and "RestController" not in top.content and "Controller" not in top.content:
            raise RuntimeError("top1 与 controller 域相关性不足")

        context = retriever.format_context(hits)
        if len(context) < 50:
            raise RuntimeError("RAG 上下文格式化失败")
        print(f"✓ 上下文拼接长度: {len(context)}")

        print("=" * 60)
        print("RAG 知识库验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        store.close()


if __name__ == "__main__":
    main()
