"""端到端 CRUD 模块验证：路由、生成、RAG 命中率、初稿覆盖率。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.graph import run_agent_pipeline
from agentforge.plugins import init_plugins
from agentforge.rag.retriever import RagRetriever


EXPECTED_DOMAINS = ["entity", "mapper", "service", "controller"]
EXPECTED_FILES = [
    "entity/Order.java",
    "mapper/OrderMapper.java",
    "service/OrderService",
    "controller/OrderController.java",
]


def main() -> None:
    print("=" * 60)
    print("端到端 CRUD 模块验证 (dry-run)")
    print("=" * 60)

    try:
        init_plugins()
        message = "生成 Order 模块完整 CRUD：Entity、Mapper、Service、Controller"

        state = run_agent_pipeline(
            session_id="e2e-test",
            project_id="e2e-order",
            user_message=message,
            framework_version="4.0",
            dry_run=True,
        )

        domains = state.get("route_domains", [])
        if not all(d in domains for d in EXPECTED_DOMAINS):
            raise RuntimeError(f"路由域不完整: {domains}")
        print(f"✓ 路由域: {domains}")

        results = state.get("domain_results", [])
        if len(results) < 4:
            raise RuntimeError(f"SubGraph 数量不足: {len(results)}")

        paths = [r.file_path for r in results]
        coverage_hits = 0
        for needle in EXPECTED_FILES:
            if any(needle in p for p in paths):
                coverage_hits += 1
        coverage = coverage_hits / len(EXPECTED_FILES)
        print(f"✓ 初稿覆盖率: {coverage:.0%} ({coverage_hits}/{len(EXPECTED_FILES)})")
        if coverage < 0.75:
            raise RuntimeError("初稿覆盖率低于 75%")

        retriever = RagRetriever(use_cache=False)
        rag_hits = 0
        for domain in EXPECTED_DOMAINS:
            hits = retriever.retrieve(
                f"{message} {domain}",
                domain=domain,
                framework_version="4.0",
                top_k=3,
                rerank_top_n=1,
            )
            if hits:
                rag_hits += 1
        rag_rate = rag_hits / len(EXPECTED_DOMAINS)
        print(f"✓ RAG 命中率: {rag_rate:.0%} ({rag_hits}/{len(EXPECTED_DOMAINS)} 域)")
        if rag_rate < 0.75:
            raise RuntimeError("RAG 命中率低于 75%")

        stages_count = sum(len(r.stages or []) for r in results)
        print(f"✓ 三阶段记录: {stages_count} 条 stage 元数据")
        print(f"✓ 示例路径: {paths[0]}")

        print("=" * 60)
        print("端到端 CRUD 验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
