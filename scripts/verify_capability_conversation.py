"""验证对话驱动能力层叠加（Phase 2）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.capability_router import CapabilityRouter
from agentforge.agents.orchestrator import AgentOrchestrator
from agentforge.db.meta_store import MetaStore
from agentforge.services.project_service import ProjectService


def main() -> None:
    print("=" * 60)
    print("对话驱动能力层验证 (Phase 2)")
    print("=" * 60)

    router = CapabilityRouter()
    meta = MetaStore()

    try:
        meta.init_schema()

        # 1. 意图识别
        caps = router.detect("给项目加上 springdoc Swagger", current_stack=["base"])
        if caps != ["springdoc"]:
            raise RuntimeError(f"springdoc 识别失败: {caps}")
        print("✓ 识别: 给项目加上 springdoc")

        if router.is_capability_only("给项目加上 springdoc", caps):
            print("✓ 纯能力叠加意图")
        else:
            raise RuntimeError("应识别为纯能力叠加")

        combined = router.detect(
            "加 springdoc 并生成 Order 模块 CRUD",
            current_stack=["base"],
        )
        if combined != ["springdoc"]:
            raise RuntimeError(f"组合消息能力识别失败: {combined}")
        if not router.has_codegen_intent("加 springdoc 并生成 Order 模块 CRUD"):
            raise RuntimeError("组合消息应含代码生成意图")
        print("✓ 组合消息: 能力 + CRUD")

        noop = router.detect("生成 UserController CRUD", current_stack=["base"])
        if noop:
            raise RuntimeError(f"纯 CRUD 不应触发能力层: {noop}")
        print("✓ 纯 CRUD 不触发能力叠加")

        # 2. 编排器事件流（纯能力对话，不调用 LLM pipeline）
        project_id = meta.create_project("phase2-test", framework_version="4.0")
        session_id = meta.create_session(project_id, "phase2")

        orchestrator = AgentOrchestrator(meta_store=meta, project_service=ProjectService(meta=meta))
        events = list(orchestrator.stream(session_id, "请给项目启用 springdoc 接口文档"))

        types = [e["type"] for e in events]
        if "capability_enabled" not in types:
            raise RuntimeError(f"缺少 capability_enabled 事件: {types}")
        if "token" not in types:
            raise RuntimeError("纯能力对话应返回说明文本")

        cap_events = [e for e in events if e["type"] == "capability_enabled"]
        if cap_events[0]["data"].get("capability_id") != "springdoc":
            raise RuntimeError("capability_enabled 数据错误")

        stack = meta.get_project(project_id)["metadata"]["template_stack"]
        if stack != ["base", "springdoc"]:
            raise RuntimeError(f"项目栈未更新: {stack}")
        print(f"✓ 对话自动叠加: template_stack={stack}")

        # 幂等：再次对话应友好提示已启用
        events2 = list(orchestrator.stream(session_id, "再加 springdoc"))
        if not any(e["type"] == "token" for e in events2):
            raise RuntimeError("重复启用应返回说明文本")
        print("✓ 重复启用幂等")

        meta.delete_project(project_id)
        ProjectService(meta=meta).composer.sandbox.destroy(project_id)
        print("✓ 测试数据已清理")

        print("=" * 60)
        print("Phase 2 对话驱动验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        meta.close()


if __name__ == "__main__":
    main()
