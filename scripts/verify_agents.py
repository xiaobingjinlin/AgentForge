"""验证三层多智能体架构（dry-run，不调用 LLM）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.graph import run_agent_pipeline
from agentforge.agents.handoff import handoff_to_prompt
from agentforge.agents.subgraphs.domain import build_domain_subgraph
from agentforge.plugins import init_plugins


def main() -> None:
    print("=" * 60)
    print("AgentForge 三层多智能体验证 (dry-run)")
    print("=" * 60)

    try:
        init_plugins()

        subgraph = build_domain_subgraph()
        if subgraph is None:
            raise RuntimeError("领域 SubGraph 编译失败")
        print("✓ 领域 SubGraph 编译成功")

        state = run_agent_pipeline(
            session_id="agent-test",
            project_id="proj-test",
            user_message="生成 User 模块：Entity、Mapper、Service、Controller",
            tech_stack="spring-boot",
            framework_version="4.0",
            dry_run=True,
        )

        domains = state.get("route_domains", [])
        expected = {"entity", "mapper", "service", "controller"}
        if not expected.intersection(domains):
            raise RuntimeError(f"路由域不符合预期: {domains}")
        print(f"✓ 路由分发: {domains}")

        handoffs = state.get("handoffs", [])
        if len(handoffs) != len(domains):
            raise RuntimeError("Handoff 数量与域不匹配")
        prompt = handoff_to_prompt(handoffs[0])
        if "Handoff" not in prompt or len(prompt) < 50:
            raise RuntimeError("Handoff Prompt 构建失败")
        print(f"✓ Handoff 结构化传递: {len(handoffs)} 个包")

        results = state.get("domain_results", [])
        if len(results) != len(domains):
            raise RuntimeError("SubGraph 产出数量不匹配")
        print(f"✓ 领域 SubGraph 执行: {[r.domain for r in results]}")

        final_prompt = state.get("final_prompt", "")
        if "各域 Agent 产出" not in final_prompt:
            raise RuntimeError("整合 Prompt 构建失败")
        print(f"✓ 结果整合 Prompt 长度: {len(final_prompt)}")

        print("=" * 60)
        print("三层架构验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
