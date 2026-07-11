"""验证三阶段代码生成流水线（dry-run）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.codegen import (
    MAX_IMPLEMENT_CHARS,
    MAX_SINGLE_TOOL_OUTPUT_CHARS,
    enforce_output_limit,
)
from agentforge.agents.codegen.pipeline import PhasedCodegenPipeline
from agentforge.agents.domains.spring_boot import get_domain_agent
from agentforge.agents.subgraphs.domain import run_domain_subgraph
from agentforge.plugins import get_framework, init_plugins


class _FakeLLM:
    pass


def main() -> None:
    print("=" * 60)
    print("三阶段代码生成验证 (dry-run)")
    print("=" * 60)

    try:
        init_plugins()
        plugin = get_framework("spring-boot")
        handoff = plugin.build_handoff("service", "生成 OrderService CRUD")

        long_text = "x" * 5000
        trimmed, truncated = enforce_output_limit(long_text, max_chars=1000)
        if not truncated or len(trimmed) > 1100:
            raise RuntimeError("输出限制未生效")
        print(f"✓ 输出限制: {MAX_SINGLE_TOOL_OUTPUT_CHARS} chars 上限")

        agent = get_domain_agent("service")
        pipeline = PhasedCodegenPipeline(llm=_FakeLLM())
        code, stages = pipeline.run(
            agent,
            handoff,
            framework_version="4.0",
            upstream={},
            dry_run=True,
        )
        if not code or not stages:
            raise RuntimeError("dry-run 流水线失败")
        print(f"✓ 流水线阶段: {[s.stage for s in stages]}")

        result = run_domain_subgraph(
            handoff,
            project_id="codegen-test",
            framework_version="4.0",
            dry_run=True,
            write_sandbox=False,
        )
        if not result.code or "service" not in result.domain:
            raise RuntimeError("SubGraph 集成失败")
        print(f"✓ SubGraph 集成: {result.file_path}")
        print(f"✓ 实现阶段上限: {MAX_IMPLEMENT_CHARS} chars")

        print("=" * 60)
        print("三阶段代码生成验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
