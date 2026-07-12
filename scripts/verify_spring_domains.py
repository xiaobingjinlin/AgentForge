"""验证 Spring Boot 技术域子 Agent 与协作编排。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.domains.spring_boot import (
    DOMAIN_AGENTS,
    DOMAIN_EXECUTION_ORDER,
    get_domain_agent,
    guess_entity_name,
    sort_domains,
)
from agentforge.agents.graph import run_agent_pipeline
from agentforge.plugins import init_plugins


def main() -> None:
    print("=" * 60)
    print("Spring Boot 技术域 SubAgent 验证")
    print("=" * 60)

    try:
        init_plugins()

        if len(DOMAIN_AGENTS) < 5:
            raise RuntimeError("子 Agent 数量不足")
        print(f"✓ 注册子 Agent: {', '.join(DOMAIN_AGENTS)}")

        entity = guess_entity_name("生成 OrderController CRUD")
        if entity != "Order":
            raise RuntimeError(f"实体名推断错误: {entity}")
        print(f"✓ 实体名推断: Order")

        purchase = guess_entity_name("生成采购系统 Mapper Service Controller")
        if purchase != "Purchase":
            raise RuntimeError(f"采购系统实体名错误: {purchase}")
        print(f"✓ 实体名推断: 采购系统 → {purchase}")

        ordered = sort_domains(["controller", "entity", "service", "mapper"])
        if ordered != ["entity", "mapper", "service", "controller"]:
            raise RuntimeError(f"执行顺序错误: {ordered}")
        print(f"✓ 协作顺序: {' → '.join(ordered)}")

        controller = get_domain_agent("controller")
        from agentforge.plugins import get_framework

        plugin = get_framework("spring-boot")
        h = plugin.build_handoff("controller", "生成 OrderController CRUD")
        path = controller.target_file(h)
        if "OrderController.java" not in path:
            raise RuntimeError(f"Controller 路径错误: {path}")
        print(f"✓ Controller 目标文件: {path}")

        state = run_agent_pipeline(
            session_id="domain-test",
            project_id="proj-order-001",
            user_message="生成 Order 模块完整 CRUD：Entity、Mapper、Service、Controller",
            dry_run=True,
        )
        domains = state.get("route_domains", [])
        if ordered != [d for d in ordered if d in domains]:
            raise RuntimeError(f"流水线域顺序异常: {domains}")
        results = state.get("domain_results", [])
        if len(results) < 4:
            raise RuntimeError(f"SubGraph 数量不足: {len(results)}")

        paths = [r.file_path for r in results]
        if not any("entity/Order.java" in p for p in paths):
            raise RuntimeError(f"缺少 entity 落盘路径: {paths}")
        print(f"✓ 流水线执行: {[r.agent for r in results]}")
        print(f"✓ 落盘路径示例: {paths[0]}")

        print("=" * 60)
        print("Spring Boot 技术域验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
