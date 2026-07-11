"""模板复制与能力栈组合。"""

from __future__ import annotations

import shutil
from pathlib import Path

from agentforge.core.config import PROJECT_ROOT
from agentforge.templates.composer import TemplateComposer

DEFAULT_TEMPLATE = PROJECT_ROOT / "templates" / "spring-boot" / "4.0" / "base"
DEFAULT_STACK = ["base"]


def copy_template_to_sandbox(
    project_id: str,
    *,
    template_dir: Path | None = None,
    sandbox_manager: object | None = None,
    stack: list[str] | None = None,
    framework_version: str = "4.0",
    clean: bool = True,
) -> Path:
    """将模板组合写入沙盒；未指定 stack 时仅复制 base。"""
    if stack and (len(stack) > 1 or (len(stack) == 1 and stack[0] != "base")):
        composer = TemplateComposer(sandbox=sandbox_manager)  # type: ignore[arg-type]
        return composer.compose_to_sandbox(
            project_id,
            stack,
            framework_version=framework_version,
            clean=clean,
        )

    from agentforge.sandbox.manager import SandboxManager

    template = Path(template_dir or DEFAULT_TEMPLATE)
    if not template.exists():
        raise FileNotFoundError(f"模板不存在: {template}")

    manager = sandbox_manager or SandboxManager()
    target = manager.create(project_id, clean=clean)
    shutil.copytree(template, target, dirs_exist_ok=True)
    return target


def compose_template_to_sandbox(
    project_id: str,
    stack: list[str] | None = None,
    *,
    framework_version: str = "4.0",
    clean: bool = True,
) -> Path:
    """按能力栈组合模板到沙盒。"""
    composer = TemplateComposer()
    return composer.compose_to_sandbox(
        project_id,
        stack or DEFAULT_STACK,
        framework_version=framework_version,
        clean=clean,
    )
