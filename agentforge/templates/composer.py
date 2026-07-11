"""模板组合：base + 能力层 overlay 合并到沙盒。"""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from agentforge.core.config import PROJECT_ROOT
from agentforge.sandbox.manager import SandboxManager
from agentforge.templates.capability import (
    BASE_LAYER_ID,
    CapabilityManifest,
    CapabilityRegistry,
    resolve_stack,
)

BASE_TEMPLATE = PROJECT_ROOT / "templates" / "spring-boot" / "4.0" / "base"


def _base_dir(framework_version: str) -> Path:
    path = PROJECT_ROOT / "templates" / "spring-boot" / framework_version / "base"
    if not path.exists():
        raise FileNotFoundError(f"基础模板不存在: {path}")
    return path


def _pom_contains_dependency(pom_content: str, artifact_id: str) -> bool:
    return f"<artifactId>{artifact_id}</artifactId>" in pom_content


def merge_pom_dependencies(pom_path: Path, manifest: CapabilityManifest) -> None:
    content = pom_path.read_text(encoding="utf-8")
    if "</dependencies>" not in content:
        raise ValueError(f"无效的 pom.xml: {pom_path}")

    inserts: list[str] = []
    for dep in manifest.pom_dependencies:
        if _pom_contains_dependency(content, dep.artifact_id):
            continue
        version_line = f"\n            <version>{dep.version}</version>" if dep.version else ""
        inserts.append(
            f"""        <dependency>
            <groupId>{dep.group_id}</groupId>
            <artifactId>{dep.artifact_id}</artifactId>{version_line}
        </dependency>"""
        )

    if not inserts:
        return

    block = "\n".join(inserts) + "\n    "
    updated = content.replace("    </dependencies>", block + "</dependencies>", 1)
    pom_path.write_text(updated, encoding="utf-8")
    logger.debug("pom 已合并能力层 {} 依赖", manifest.id)


def merge_application_yml(app_path: Path, manifest: CapabilityManifest) -> None:
    snippet = manifest.application_yml.strip()
    if not snippet:
        return
    existing = app_path.read_text(encoding="utf-8") if app_path.exists() else ""
    marker = f"# capability:{manifest.id}"
    if marker in existing:
        return
    merged = existing.rstrip() + f"\n\n{marker}\n{snippet}\n"
    app_path.parent.mkdir(parents=True, exist_ok=True)
    app_path.write_text(merged, encoding="utf-8")


def apply_capability_layer(target_dir: Path, manifest: CapabilityManifest) -> None:
    """将能力层 overlay 与 pom/yml 合并到目标目录。"""
    pom_path = target_dir / "pom.xml"
    if pom_path.exists():
        merge_pom_dependencies(pom_path, manifest)

    app_path = target_dir / "src" / "main" / "resources" / "application.yml"
    merge_application_yml(app_path, manifest)

    overlay = manifest.overlay_dir
    if overlay.exists():
        for src_file in overlay.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(overlay)
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
        logger.info("能力层 {} overlay 已应用 ({} 个文件)", manifest.id, len(list(overlay.rglob("*"))))


class TemplateComposer:
    """将 base + 能力栈组合并写入沙盒。"""

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        sandbox: SandboxManager | None = None,
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        self.sandbox = sandbox or SandboxManager()

    def compose_to_sandbox(
        self,
        project_id: str,
        stack: list[str] | None = None,
        *,
        framework_version: str = "4.0",
        clean: bool = True,
    ) -> Path:
        ordered = resolve_stack(stack, framework_version=framework_version, registry=self.registry)
        target = self.sandbox.create(project_id, clean=clean)
        shutil.copytree(_base_dir(framework_version), target, dirs_exist_ok=True)

        for cap_id in ordered:
            if cap_id == BASE_LAYER_ID:
                continue
            manifest = self.registry.load(cap_id, framework_version)
            apply_capability_layer(target, manifest)

        logger.bind(project_id=project_id).info("模板栈已组合: {}", ordered)
        return target

    def apply_capability(
        self,
        project_id: str,
        capability_id: str,
        *,
        framework_version: str = "4.0",
        current_stack: list[str] | None = None,
    ) -> list[str]:
        """向已有项目叠加单层能力，返回新栈。"""
        stack = list(current_stack or [BASE_LAYER_ID])
        if capability_id in stack:
            return stack

        manifest = self.registry.load(capability_id, framework_version)
        for conflict in manifest.conflicts:
            if conflict in stack:
                raise ValueError(f"能力 {capability_id} 与 {conflict} 冲突")

        target = self.sandbox.project_dir(project_id)
        if not target.exists() or not (target / "pom.xml").exists():
            new_stack = resolve_stack(stack + [capability_id], framework_version=framework_version)
            self.compose_to_sandbox(project_id, new_stack, framework_version=framework_version, clean=True)
            return new_stack

        apply_capability_layer(target, manifest)
        new_stack = resolve_stack(stack + [capability_id], framework_version=framework_version)
        logger.bind(project_id=project_id).info("已叠加能力层: {}", capability_id)
        return new_stack

    def verify_stack(
        self,
        project_id: str,
        stack: list[str],
        *,
        framework_version: str = "4.0",
    ) -> dict[str, str | int]:
        """对栈中最后一层（或指定能力）执行 manifest 验证命令。"""
        ordered = resolve_stack(stack, framework_version=framework_version, registry=self.registry)
        last_cap = ordered[-1] if ordered else BASE_LAYER_ID
        if last_cap == BASE_LAYER_ID:
            command = "mvn -q -DskipTests compile"
        else:
            command = self.registry.load(last_cap, framework_version).verify_command
        return self.sandbox.run_command(project_id, command)
