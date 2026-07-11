"""验证项目骨架：插件注册 + LangGraph 流水线。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.graph import run_agent_pipeline
from agentforge.plugins import framework_registry, init_plugins


def main() -> None:
    print("=" * 60)
    print("AgentForge 项目骨架验证")
    print("=" * 60)

    try:
        init_plugins()
        names = framework_registry.list_names()
        if "spring-boot" not in names:
            raise RuntimeError(f"缺少 spring-boot 插件: {names}")
        print(f"✓ 框架插件注册: {', '.join(names)}")

        plugin = framework_registry.get("spring-boot")
        template = plugin.template_dir()
        if not template.exists():
            raise RuntimeError(f"模板不存在: {template}")
        print(f"✓ Spring Boot 模板: {template}")
        print(f"✓ 技术域: {', '.join(plugin.domains())}")

        state = run_agent_pipeline(
            session_id="skeleton-test",
            project_id="proj-test",
            user_message="生成 UserController 的 CRUD 接口",
            tech_stack="spring-boot",
            framework_version="4.0",
            dry_run=True,
        )
        domains = state.get("route_domains", [])
        if "controller" not in domains:
            raise RuntimeError(f"路由失败: {domains}")
        print(f"✓ LangGraph 路由: {domains}")
        print(f"✓ Handoff 数量: {len(state.get('handoffs', []))}")
        print(f"✓ SubGraph 产出: {len(state.get('domain_results', []))}")
        print(f"✓ 整合 Prompt 长度: {len(state.get('final_prompt', ''))}")

        print("=" * 60)
        print("项目骨架验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
