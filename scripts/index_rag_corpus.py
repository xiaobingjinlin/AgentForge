"""将 Spring Boot 知识库分块入库（pgvector）。"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.db.vector_store import VectorStore
from agentforge.rag.indexer import CorpusIndexer


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentForge RAG 知识库入库")
    parser.add_argument("--version", default="4.0", help="Spring Boot 版本目录")
    parser.add_argument("--no-templates", action="store_true", help="不索引 templates 示例代码")
    args = parser.parse_args()

    print("=" * 60)
    print("AgentForge RAG 知识库入库")
    print("=" * 60)

    store = VectorStore()
    try:
        store.init_schema()
        indexer = CorpusIndexer(store=store)
        stats = indexer.index_spring_boot(
            framework_version=args.version,
            include_templates=not args.no_templates,
        )
        total = store.count_chunks()
        print(f"✓ 扫描文件: {stats.files_scanned}")
        print(f"✓ 写入 chunk: {stats.chunks_indexed}")
        print(f"✓ 库内总量: {total}")
        if stats.chunks_skipped:
            print(f"⚠ 跳过文件: {stats.chunks_skipped}")
        print("=" * 60)
        print("入库完成")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 入库失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        store.close()


if __name__ == "__main__":
    main()
