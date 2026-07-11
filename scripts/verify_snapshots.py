"""验证文档快照与按版本检索。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.db.meta_store import MetaStore
from agentforge.rag.retriever import RagRetriever
from agentforge.rag.snapshots import DocSnapshotService


def main() -> None:
    print("=" * 60)
    print("文档快照与版本兼容验证")
    print("=" * 60)

    meta = MetaStore()
    service = DocSnapshotService(meta=meta)
    try:
        meta.init_schema()
        versions = service.list_versions("spring-boot")
        names = [v["version"] for v in versions]
        for expected in ("2.7", "3.2", "4.0"):
            if expected not in names:
                raise RuntimeError(f"缺少版本快照目录: {expected}")
        print(f"✓ 快照版本: {', '.join(names)}")

        for ver in ("3.2", "4.0"):
            service.register_snapshot("spring-boot", ver)
        print("✓ 快照注册入库")

        result = service.index_version("spring-boot", "3.2", include_templates=False)
        if result["chunks_indexed"] < 1:
            raise RuntimeError("3.2 版本索引失败")
        print(f"✓ 3.2 索引: {result['chunks_indexed']} chunks")

        retriever = RagRetriever(use_cache=False)
        hits = retriever.retrieve(
            "Spring Boot 3.2 RestController CRUD",
            domain="controller",
            framework_version="3.2",
            top_k=4,
            rerank_top_n=2,
        )
        if not hits:
            raise RuntimeError("3.2 域内检索无结果")
        print(f"✓ 3.2 检索命中: {hits[0].source_path}")

        print("=" * 60)
        print("版本兼容验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        meta.close()


if __name__ == "__main__":
    main()
