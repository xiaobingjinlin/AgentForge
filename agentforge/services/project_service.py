"""项目沙盒文件与上下文服务。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from agentforge.db.meta_store import MetaStore
from agentforge.sandbox.manager import SandboxManager
from agentforge.templates.capability import CapabilityRegistry
from agentforge.templates.capability_generator import CapabilityGenerator
from agentforge.templates.capability_policy import CapabilityPolicy, CapabilityRejectedError
from agentforge.templates.composer import TemplateComposer
from agentforge.utils.llm_util import LLMUtil


class ProjectService:
    def __init__(
        self,
        meta: MetaStore | None = None,
        sandbox: SandboxManager | None = None,
        composer: TemplateComposer | None = None,
        registry: CapabilityRegistry | None = None,
        policy: CapabilityPolicy | None = None,
    ) -> None:
        self.meta = meta or MetaStore()
        self.sandbox = sandbox or SandboxManager()
        self.registry = registry or CapabilityRegistry()
        self.policy = policy or CapabilityPolicy(registry=self.registry)
        self.composer = composer or TemplateComposer(sandbox=self.sandbox, registry=self.registry)

    def get_template_stack(self, project_id: str) -> list[str]:
        project = self.meta.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        stack = project.get("metadata", {}).get("template_stack")
        return list(stack) if isinstance(stack, list) else ["base"]

    def list_available_capabilities(self, framework_version: str = "4.0") -> list[dict[str, str]]:
        return self.registry.describe_all(framework_version)

    def enable_capability(
        self,
        project_id: str,
        capability_id: str,
        *,
        verify: bool = False,
    ) -> dict[str, object]:
        project = self.meta.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")

        framework_version = project.get("framework_version") or "4.0"
        self.policy.assert_allowed(capability_id, framework_version=framework_version)
        current_stack = self.get_template_stack(project_id)
        if capability_id in current_stack:
            return {
                "capability_id": capability_id,
                "template_stack": current_stack,
                "already_enabled": True,
            }

        new_stack = self.composer.apply_capability(
            project_id,
            capability_id,
            framework_version=framework_version,
            current_stack=current_stack,
        )
        self.meta.update_project_metadata(project_id, {"template_stack": new_stack})
        files = self.sandbox.list_files(project_id)
        self.meta.save_project_structure(project_id, files)

        result: dict[str, object] = {
            "capability_id": capability_id,
            "template_stack": new_stack,
            "sandbox_files": files,
            "already_enabled": False,
        }
        if verify:
            run_result = self.composer.verify_stack(
                project_id,
                new_stack,
                framework_version=framework_version,
            )
            result["verify"] = run_result
        return result

    def ensure_capability(
        self,
        project_id: str,
        capability_id: str,
        user_message: str,
        *,
        llm: LLMUtil | None = None,
        run_verify: bool = True,
        spec: dict | None = None,
    ) -> dict[str, object]:
        """已存在则启用；不存在则 LLM 生成后启用。"""
        project = self.meta.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")

        framework_version = project.get("framework_version") or "4.0"
        self.policy.assert_allowed(capability_id, framework_version=framework_version)
        generated = False
        generation_info: dict[str, object] = {}

        if not self.registry.exists(capability_id, framework_version):
            generator = CapabilityGenerator(
                llm=llm,
                registry=self.registry,
                composer=self.composer,
            )
            gen_result = generator.generate_and_promote(
                capability_id,
                user_message,
                framework_version=framework_version,
                run_verify=run_verify,
                spec=spec,
            )
            generated = gen_result.source != "registry"
            generation_info = {
                "generated": generated,
                "path": gen_result.path,
                "files_written": gen_result.files_written,
                "verified": gen_result.verified,
                "verify_detail": gen_result.verify_detail,
            }

        enable_result = self.enable_capability(project_id, capability_id)
        return {**enable_result, **generation_info}

    def get_context(self, project_id: str) -> dict[str, Any]:
        project = self.meta.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        files = self.sandbox.list_files(project_id)
        records = self.meta.list_generation_records(project_id=project_id, limit=20)
        return {
            "project": project,
            "sandbox_files": files,
            "recent_generations": records,
            "template_stack": self.get_template_stack(project_id),
            "available_capabilities": self.list_available_capabilities(
                project.get("framework_version") or "4.0"
            ),
        }

    def list_files(self, project_id: str) -> list[str]:
        return self.sandbox.list_files(project_id)

    def read_file(self, project_id: str, relative_path: str) -> str:
        return self.sandbox.read_text(project_id, relative_path)

    def export_to_local(self, project_id: str) -> dict[str, Any]:
        """将沙盒内容同步到项目 root_path 或返回沙盒路径。"""
        project = self.meta.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")

        src = self.sandbox.project_dir(project_id)
        if not src.exists() or not any(src.iterdir()):
            raise ValueError("沙盒为空，请先生成代码")

        root_path = project.get("root_path")
        if root_path:
            dest = Path(root_path).expanduser().resolve()
            dest.mkdir(parents=True, exist_ok=True)
            copied = 0
            for file_path in src.rglob("*"):
                if file_path.is_file():
                    rel = file_path.relative_to(src)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, target)
                    copied += 1
            logger.info("项目 {} 已落盘至 {}", project_id, dest)
            return {
                "mode": "local",
                "target_path": str(dest),
                "files_copied": copied,
            }

        return {
            "mode": "sandbox",
            "target_path": str(src),
            "files_copied": len(self.sandbox.list_files(project_id)),
            "hint": "可在创建项目时设置 root_path 以启用一键落盘",
        }
