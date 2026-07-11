"""验证非 Spring Boot 生态能力层拒绝策略。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.capability_router import CapabilityRouter
from agentforge.agents.orchestrator import AgentOrchestrator
from agentforge.db.meta_store import MetaStore
from agentforge.services.project_service import ProjectService
from agentforge.templates.capability_policy import CapabilityPolicy, CapabilityRejectedError


def main() -> None:
    print("=" * 60)
    print("能力层生态拒绝策略验证")
    print("=" * 60)

    router = CapabilityRouter()
    policy = CapabilityPolicy(registry=router.registry)
    meta = MetaStore()

    try:
        meta.init_schema()

        # 1. Policy 单元校验
        reason = policy.check("react")
        if not reason or "Spring Boot" not in reason:
            raise RuntimeError(f"react 应被拒绝: {reason}")
        print("✓ blocklist: react")

        if policy.check("redis") is not None:
            raise RuntimeError("redis 应在 allowlist 中")
        print("✓ allowlist: redis")

        if policy.check("springdoc") is not None:
            raise RuntimeError("已注册 springdoc 应放行")
        print("✓ registry: springdoc")

        # 2. Router collect_to_enable
        reg, gen, rej = router.collect_to_enable("给项目加上 react", current_stack=["base"])
        if not rej or reg or gen:
            raise RuntimeError(f"加 react 应拒绝: reg={reg}, gen={gen}, rej={rej}")
        print("✓ collect_to_enable: 拒绝 react")

        reg, gen, rej = router.collect_to_enable("启用 redis 缓存", current_stack=["base"])
        if rej or "redis" not in gen:
            raise RuntimeError(f"redis 应进入造层队列: reg={reg}, gen={gen}, rej={rej}")
        print("✓ collect_to_enable: 放行 redis")

        hits = router.scan_non_ecosystem("项目需要 Vue 前端")
        if not hits:
            raise RuntimeError("应识别 Vue 非生态提及")
        print("✓ scan_non_ecosystem: Vue")

        # 3. ProjectService API 层拒绝
        project_id = meta.create_project("policy-test", framework_version="4.0")
        service = ProjectService(meta=meta)
        try:
            service.enable_capability(project_id, "django")
            raise RuntimeError("enable django 应抛 CapabilityRejectedError")
        except CapabilityRejectedError:
            print("✓ enable_capability: 拒绝 django")

        # 4. 编排器对话拒绝（不走 codegen）
        session_id = meta.create_session(project_id, "policy")
        orchestrator = AgentOrchestrator(meta_store=meta, project_service=service)
        events = list(orchestrator.stream(session_id, "给项目加上 react 前端"))

        if not any(e["type"] == "token" for e in events):
            raise RuntimeError("拒绝应返回说明文本")
        done = [e for e in events if e["type"] == "done"]
        if not done or not done[0]["data"].get("capability_rejected"):
            raise RuntimeError(f"done 应标记 capability_rejected: {events}")

        stack = meta.get_project(project_id)["metadata"]["template_stack"]
        if stack != ["base"]:
            raise RuntimeError(f"拒绝后栈不应变化: {stack}")
        print("✓ orchestrator: 对话拒绝 react，栈未变")

        # 5. springdoc 仍可正常启用
        events_ok = list(orchestrator.stream(session_id, "启用 springdoc"))
        if "capability_enabled" not in [e["type"] for e in events_ok]:
            raise RuntimeError("springdoc 应正常启用")
        print("✓ orchestrator: springdoc 仍可用")

        meta.delete_project(project_id)
        service.composer.sandbox.destroy(project_id)
        print("✓ 测试数据已清理")

        print("=" * 60)
        print("生态拒绝策略验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        meta.close()


if __name__ == "__main__":
    main()
