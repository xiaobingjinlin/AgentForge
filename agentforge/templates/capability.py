"""能力层清单解析与注册。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agentforge.core.config import PROJECT_ROOT

CAPABILITIES_ROOT = PROJECT_ROOT / "templates" / "spring-boot"
BASE_LAYER_ID = "base"


@dataclass(frozen=True)
class PomDependency:
    group_id: str
    artifact_id: str
    version: str | None = None


@dataclass(frozen=True)
class CapabilityManifest:
    id: str
    name: str
    framework_version: str
    description: str = ""
    requires: list[str] = field(default_factory=lambda: [BASE_LAYER_ID])
    conflicts: list[str] = field(default_factory=list)
    pom_dependencies: list[PomDependency] = field(default_factory=list)
    application_yml: str = ""
    verify_command: str = "mvn -q -DskipTests compile"
    root_dir: Path = field(default_factory=Path)

    @property
    def overlay_dir(self) -> Path:
        return self.root_dir / "overlay"


class CapabilityRegistry:
    """扫描 templates/spring-boot/{version}/capabilities/ 下的能力层。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or CAPABILITIES_ROOT

    def capabilities_dir(self, framework_version: str) -> Path:
        return self.root / framework_version / "capabilities"

    def resolve_dir(self, capability_id: str, framework_version: str = "4.0") -> Path:
        cap_dir = self.capabilities_dir(framework_version)
        official = cap_dir / capability_id
        if official.is_dir() and (official / "manifest.json").exists():
            return official
        generated = cap_dir / "_generated" / capability_id
        if generated.is_dir() and (generated / "manifest.json").exists():
            return generated
        raise FileNotFoundError(f"能力层不存在: {capability_id} (version={framework_version})")

    def exists(self, capability_id: str, framework_version: str = "4.0") -> bool:
        try:
            self.resolve_dir(capability_id, framework_version)
            return True
        except FileNotFoundError:
            return False

    def list_ids(self, framework_version: str = "4.0") -> list[str]:
        cap_dir = self.capabilities_dir(framework_version)
        if not cap_dir.exists():
            return []
        ids: list[str] = []
        for child in sorted(cap_dir.iterdir()):
            if child.name.startswith("_"):
                if child.name == "_generated":
                    for gen in sorted(child.iterdir()):
                        if gen.is_dir() and (gen / "manifest.json").exists():
                            ids.append(gen.name)
                continue
            if child.is_dir() and (child / "manifest.json").exists():
                ids.append(child.name)
        return ids

    def load(self, capability_id: str, framework_version: str = "4.0") -> CapabilityManifest:
        data = self.load_raw(capability_id, framework_version)
        cap_dir = self.resolve_dir(capability_id, framework_version)
        return self._manifest_from_data(data, cap_dir, capability_id, framework_version)

    def load_from_dir(self, layer_dir: Path) -> CapabilityManifest:
        manifest_path = layer_dir / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        cap_id = data.get("id", layer_dir.name)
        fw = data.get("framework_version", "4.0")
        return self._manifest_from_data(data, layer_dir, cap_id, fw)

    def _manifest_from_data(
        self,
        data: dict,
        cap_dir: Path,
        capability_id: str,
        framework_version: str,
    ) -> CapabilityManifest:
        deps = [
            PomDependency(
                group_id=item["groupId"],
                artifact_id=item["artifactId"],
                version=item.get("version"),
            )
            for item in data.get("pom", {}).get("dependencies", [])
        ]
        verify = data.get("verify", {})
        return CapabilityManifest(
            id=data.get("id", capability_id),
            name=data.get("name", capability_id),
            description=data.get("description", ""),
            framework_version=data.get("framework_version", framework_version),
            requires=data.get("requires", [BASE_LAYER_ID]),
            conflicts=data.get("conflicts", []),
            pom_dependencies=deps,
            application_yml=data.get("application_yml", ""),
            verify_command=verify.get("command", "mvn -q -DskipTests compile"),
            root_dir=cap_dir,
        )

    def load_raw(self, capability_id: str, framework_version: str = "4.0") -> dict:
        cap_dir = self.resolve_dir(capability_id, framework_version)
        manifest_path = cap_dir / "manifest.json"
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def describe_all(self, framework_version: str = "4.0") -> list[dict[str, str]]:
        items = []
        for cap_id in self.list_ids(framework_version):
            manifest = self.load(cap_id, framework_version)
            items.append({
                "id": manifest.id,
                "name": manifest.name,
                "description": manifest.description,
                "requires": manifest.requires,
            })
        return items


def resolve_stack(
    stack: list[str] | None,
    *,
    framework_version: str = "4.0",
    registry: CapabilityRegistry | None = None,
) -> list[str]:
    """解析并排序能力栈：base 在前，其余按依赖拓扑 + 声明顺序。"""
    reg = registry or CapabilityRegistry()
    raw = stack or [BASE_LAYER_ID]
    normalized: list[str] = []
    for item in raw:
        key = item if item != BASE_LAYER_ID else BASE_LAYER_ID
        if key not in normalized:
            normalized.append(key)

    if BASE_LAYER_ID not in normalized:
        normalized.insert(0, BASE_LAYER_ID)

    ordered: list[str] = [BASE_LAYER_ID]
    pending = [c for c in normalized if c != BASE_LAYER_ID]

    while pending:
        progress = False
        for cap_id in list(pending):
            manifest = reg.load(cap_id, framework_version)
            if all(req in ordered for req in manifest.requires):
                ordered.append(cap_id)
                pending.remove(cap_id)
                progress = True
        if not progress:
            raise ValueError(f"能力栈依赖无法解析: {pending}")

    return ordered
