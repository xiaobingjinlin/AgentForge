"""Agent 编排入口：三层架构 + SSE 流式输出 + 上下文持久化。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, TypedDict

from loguru import logger

from agentforge.agents.capability_router import CapabilityRouter
from agentforge.agents.graph import run_agent_pipeline
from agentforge.agents.handoff import DomainResult, build_brief_codegen_summary
from agentforge.core.constants import MAX_VERIFY_REPAIR_ROUNDS
from agentforge.core.jdk import probe_java_version
from agentforge.plugins.entity_resolver import resolve_entity_name
from agentforge.db.meta_store import MetaStore
from agentforge.sandbox.manager import SandboxManager
from agentforge.services.project_service import ProjectService
from agentforge.templates.capability_policy import CapabilityPolicy
from agentforge.utils.maven_output import display_maven_message
from agentforge.utils.llm_util import CHAT_MODELS, LLMUtil


class StreamEvent(TypedDict):
    type: str
    data: dict[str, Any]


class AgentOrchestrator:
    """路由 → SubGraph 执行 → 整合 三层编排。"""

    def __init__(
        self,
        meta_store: MetaStore | None = None,
        llm: LLMUtil | None = None,
        project_service: ProjectService | None = None,
        capability_router: CapabilityRouter | None = None,
    ) -> None:
        self.meta = meta_store or MetaStore()
        self.llm = llm or LLMUtil()
        self.projects = project_service or ProjectService(meta=self.meta)
        self.capability_router = capability_router or CapabilityRouter()
        self.sandbox = SandboxManager()

    def stream(self, session_id: str, message: str) -> Iterator[StreamEvent]:
        log = logger.bind(session_id=session_id)
        session = self.meta.get_session(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")

        project_id = session["project_id"]
        project = self.meta.get_project(project_id) or {}
        framework_version = project.get("framework_version") or "4.0"
        tech_stack = project.get("tech_stack") or "spring-boot"
        template_stack = self.projects.get_template_stack(project_id)

        yield StreamEvent(
            type="status",
            data={
                "stage": "capabilities",
                "message": "分析能力层叠加意图...",
                "framework_version": framework_version,
                "template_stack": template_stack,
            },
        )

        detected, to_generate, rejected = self.capability_router.collect_to_enable(
            message,
            framework_version=framework_version,
            current_stack=template_stack,
        )
        message_hits = self.capability_router.scan_non_ecosystem(message)
        has_enable_intent = self.capability_router._has_enable_intent(message)

        if rejected or (message_hits and has_enable_intent and not detected and not to_generate):
            summary = CapabilityPolicy.build_rejection_message(rejected, message_hits)
            yield StreamEvent(
                type="status",
                data={
                    "stage": "capabilities",
                    "message": "非 Spring Boot 生态能力已拒绝",
                    "rejected": [cap for cap, _ in rejected],
                    "message_hits": [label for label, _ in message_hits],
                },
            )
            yield StreamEvent(type="token", data={"content": summary})
            yield StreamEvent(
                type="done",
                data={
                    "domains": [],
                    "sandbox_files": self.sandbox.list_files(project_id),
                    "framework_version": framework_version,
                    "template_stack": template_stack,
                    "capability_rejected": True,
                    "rejected_capabilities": [cap for cap, _ in rejected],
                },
            )
            return

        enabled_results: list[dict[str, object]] = []
        generated_results: list[dict[str, object]] = []
        all_enabled_ids = detected + to_generate

        if all_enabled_ids:
            yield StreamEvent(
                type="status",
                data={
                    "stage": "capabilities",
                    "message": f"检测到能力层: {', '.join(all_enabled_ids)}",
                    "detected": detected,
                    "to_generate": to_generate,
                },
            )

            for cap_id in detected:
                try:
                    result = self.projects.enable_capability(project_id, cap_id)
                    enabled_results.append(result)
                    manifest = self.projects.registry.load(cap_id, framework_version)
                    yield StreamEvent(
                        type="capability_enabled",
                        data={
                            "capability_id": cap_id,
                            "name": manifest.name,
                            "template_stack": result.get("template_stack", []),
                            "already_enabled": result.get("already_enabled", False),
                            "generated": False,
                        },
                    )
                except Exception as exc:
                    log.warning("启用能力层 {} 失败: {}", cap_id, exc)
                    yield StreamEvent(type="error", data={"message": f"启用 {cap_id} 失败: {exc}"})
                    return

            for cap_id in to_generate:
                try:
                    yield StreamEvent(
                        type="capability_generating",
                        data={
                            "capability_id": cap_id,
                            "message": f"Registry 无 {cap_id}，LLM 生成能力层...",
                        },
                    )
                    result = self.projects.ensure_capability(
                        project_id,
                        cap_id,
                        message,
                        llm=self.llm,
                        run_verify=True,
                    )
                    enabled_results.append(result)
                    if result.get("generated"):
                        generated_results.append(result)
                    manifest = self.projects.registry.load(cap_id, framework_version)
                    yield StreamEvent(
                        type="capability_generated",
                        data={
                            "capability_id": cap_id,
                            "name": manifest.name,
                            "path": result.get("path"),
                            "verified": result.get("verified"),
                            "template_stack": result.get("template_stack", []),
                        },
                    )
                    yield StreamEvent(
                        type="capability_enabled",
                        data={
                            "capability_id": cap_id,
                            "name": manifest.name,
                            "template_stack": result.get("template_stack", []),
                            "already_enabled": result.get("already_enabled", False),
                            "generated": True,
                        },
                    )
                except Exception as exc:
                    log.exception("LLM 造层 {} 失败", cap_id)
                    yield StreamEvent(type="error", data={"message": f"生成 {cap_id} 失败: {exc}"})
                    return

            template_stack = self.projects.get_template_stack(project_id)
            log.info("能力栈已更新: {}", template_stack)

        elif (
            self.capability_router._has_enable_intent(message)
            and not self.capability_router.has_codegen_intent(message)
        ):
            mentioned = self.capability_router.match_mentioned(
                message, framework_version=framework_version
            )
            if mentioned and all(cap in template_stack for cap in mentioned):
                summary = (
                    f"以下能力层已在项目中：{', '.join(mentioned)}\n\n"
                    f"当前能力栈：`{' + '.join(template_stack)}`"
                )
                yield StreamEvent(type="token", data={"content": summary})
                yield StreamEvent(
                    type="done",
                    data={
                        "domains": [],
                        "sandbox_files": self.sandbox.list_files(project_id),
                        "framework_version": framework_version,
                        "template_stack": template_stack,
                        "capability_only": True,
                    },
                )
                return

        if self.capability_router.is_capability_only(message, all_enabled_ids):
            summary = self.capability_router.build_summary(
                enabled_results,
                template_stack=template_stack,
            )
            if generated_results:
                summary += "\n\n" + self.capability_router.build_generation_summary(generated_results)
            yield StreamEvent(
                type="status",
                data={
                    "stage": "capabilities",
                    "message": "能力层叠加完成",
                    "template_stack": template_stack,
                },
            )
            yield StreamEvent(type="token", data={"content": summary})
            yield StreamEvent(
                type="done",
                data={
                    "domains": [],
                    "sandbox_files": self.sandbox.list_files(project_id),
                    "framework_version": framework_version,
                    "template_stack": template_stack,
                    "capability_only": True,
                },
            )
            return

        if self.capability_router.is_casual_chat(message):
            yield StreamEvent(
                type="status",
                data={
                    "stage": "chat",
                    "message": "日常对话",
                    "template_stack": template_stack,
                },
            )
            system = self.capability_router.build_casual_system_prompt(
                framework_version=framework_version,
                template_stack=template_stack,
            )
            try:
                for token in self.llm.stream_chat(
                    CHAT_MODELS["router"],
                    message,
                    system=system,
                    max_tokens=1024,
                ):
                    yield StreamEvent(type="token", data={"content": token})
            except Exception as exc:
                log.exception("日常对话失败")
                yield StreamEvent(type="error", data={"message": str(exc)})
                return

            yield StreamEvent(
                type="done",
                data={
                    "domains": [],
                    "sandbox_files": self.sandbox.list_files(project_id),
                    "framework_version": framework_version,
                    "template_stack": template_stack,
                    "chat_only": True,
                },
            )
            return

        yield StreamEvent(
            type="status",
            data={
                "stage": "routing",
                "message": "路由 Agent 分析任务...",
                "framework_version": framework_version,
                "template_stack": template_stack,
            },
        )

        entity_resolution = resolve_entity_name(message, llm=self.llm, use_llm=True)
        yield StreamEvent(
            type="entity_resolved",
            data={
                "english_name": entity_resolution.english_name,
                "source_phrase": entity_resolution.source_phrase,
                "display_label": entity_resolution.display_label,
                "method": entity_resolution.method,
                "message": f"业务实体命名：{entity_resolution.display_label}",
            },
        )

        state = run_agent_pipeline(
            session_id=session_id,
            project_id=project_id,
            user_message=message,
            tech_stack=tech_stack,
            framework_version=framework_version,
            template_stack=list(template_stack),
            llm=self.llm,
            dry_run=False,
        )

        domains = state.get("route_domains", [])
        handoffs = state.get("handoffs", [])
        yield StreamEvent(
            type="status",
            data={
                "stage": "routing",
                "message": f"已路由至: {', '.join(domains)}",
                "domains": domains,
                "framework_version": framework_version,
                "template_stack": template_stack,
                "handoffs": [
                    {"source": h.source, "target": h.target, "domain": h.payload.get("domain")}
                    for h in handoffs
                ],
            },
        )

        results = state.get("domain_results", [])
        yield StreamEvent(
            type="status",
            data={
                "stage": "executing",
                "message": f"已完成 {len(results)} 个领域 SubGraph",
                "domains_done": [r.domain for r in results],
            },
        )

        for result in results:
            self._persist_domain_result(session_id, project_id, result)
            yield StreamEvent(
                type="domain_result",
                data={
                    "domain": result.domain,
                    "agent": result.agent,
                    "summary": result.summary,
                    "file_path": result.file_path,
                    "code_preview": result.code[:800],
                    "stages": result.stages,
                },
            )

        files = self.sandbox.list_files(project_id)
        if files:
            self.meta.save_project_structure(project_id, files)

        verify_result = None
        if results:
            yield StreamEvent(
                type="status",
                data={"stage": "verifying", "message": "整体验证沙盒工程..."},
            )
            from agentforge.sandbox.project_verifier import ProjectVerifier

            verify_result, results = ProjectVerifier(self.sandbox).verify_and_repair(
                project_id,
                results,
                llm=self.llm,
                user_message=message,
                max_repair_rounds=MAX_VERIFY_REPAIR_ROUNDS,
            )
            for result in results:
                if result.file_path in (verify_result.repaired_files or []):
                    self._persist_domain_result(session_id, project_id, result)
            yield StreamEvent(
                type="project_verified",
                data={
                    "ok": verify_result.ok,
                    "compile_skipped": verify_result.compile_skipped,
                    "static_issues": [
                        {"path": item.path, "issues": item.issues}
                        for item in verify_result.static_issues
                    ],
                    "compile_message": display_maven_message(
                        verify_result.compile_message,
                        max_chars=500,
                    ),
                    "repaired_files": verify_result.repaired_files,
                    "repair_rounds": verify_result.repair_rounds,
                    "stuck": verify_result.stuck,
                    "stopped_reason": verify_result.stopped_reason[:300],
                    "java_version": probe_java_version(),
                },
            )
            files = self.sandbox.list_files(project_id)
            if files:
                self.meta.save_project_structure(project_id, files)

        yield StreamEvent(type="status", data={"stage": "integrating", "message": "生成完成摘要..."})

        meta_entity = (state.get("metadata") or {}).get("entity_resolution") or {}
        entity_label = meta_entity.get("display_label") or entity_resolution.display_label

        summary = build_brief_codegen_summary(
            results,
            template_stack=template_stack,
            verify=verify_result,
            entity_label=entity_label,
        )
        yield StreamEvent(type="token", data={"content": summary})

        yield StreamEvent(
            type="done",
            data={
                "domains": domains,
                "sandbox_files": files,
                "framework_version": framework_version,
                "template_stack": template_stack,
                "capabilities_enabled": [r.get("capability_id") for r in enabled_results],
                "capabilities_generated": [r.get("capability_id") for r in generated_results],
                "verify_ok": verify_result.ok if verify_result else None,
                "entity_name": entity_resolution.english_name,
                "entity_label": entity_resolution.display_label,
            },
        )

    def _persist_domain_result(
        self,
        session_id: str,
        project_id: str,
        result: Any,
    ) -> None:
        self.meta.add_generation_record(
            session_id=session_id,
            project_id=project_id,
            stage="domain",
            file_path=result.file_path,
            content=result.code[:4000],
            metadata={"domain": result.domain, "agent": result.agent, "summary": result.summary},
        )
        if result.stages:
            for stage in result.stages:
                self.meta.add_generation_record(
                    session_id=session_id,
                    project_id=project_id,
                    stage=stage.get("stage", "unknown"),
                    file_path=result.file_path,
                    metadata=stage,
                )
