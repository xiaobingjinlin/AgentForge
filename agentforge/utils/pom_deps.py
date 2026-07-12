"""根据编译错误为沙盒 pom.xml 补齐 Spring Boot / MyBatis 依赖。"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from loguru import logger

_NS = "http://maven.apache.org/POM/4.0.0"
ET.register_namespace("", _NS)

# artifactId -> (groupId, version or None 表示省略 version 由 BOM 管理)
_POM_DEPENDENCY_CATALOG: dict[str, tuple[str, str | None]] = {
    "spring-boot-starter-jdbc": ("org.springframework.boot", None),
    "mybatis-spring-boot-starter": ("org.mybatis.spring.boot", "4.0.1"),
}

# 缺失包名片段 -> 需添加的 artifactId
_PACKAGE_TO_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "org.springframework.transaction": ("spring-boot-starter-jdbc",),
    "org.springframework.jdbc": ("spring-boot-starter-jdbc",),
    "org.mybatis": ("mybatis-spring-boot-starter", "spring-boot-starter-jdbc"),
    "org.apache.ibatis": ("mybatis-spring-boot-starter",),
}


def infer_missing_artifacts(compile_message: str) -> list[str]:
    if not compile_message:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for line in compile_message.splitlines():
        match = re.search(r"程序包([\w.]+)不存在", line)
        if not match:
            match = re.search(
                r"package\s+([\w.]+)\s+does not exist",
                line,
                re.I,
            )
        if not match:
            continue
        package_name = match.group(1)
        for prefix, artifacts in _PACKAGE_TO_ARTIFACTS.items():
            if package_name == prefix or package_name.startswith(prefix + "."):
                for artifact in artifacts:
                    if artifact not in seen:
                        seen.add(artifact)
                        found.append(artifact)
    return found


def ensure_pom_dependencies(pom_path: Path, artifact_ids: list[str]) -> list[str]:
    """向 pom.xml 注入缺失依赖，返回实际新增的 artifactId。"""
    if not artifact_ids or not pom_path.is_file():
        return []

    tree = ET.parse(pom_path)
    root = tree.getroot()
    deps_el = root.find(f"{{{_NS}}}dependencies")
    if deps_el is None:
        deps_el = ET.SubElement(root, f"{{{_NS}}}dependencies")

    existing = {
        (dep.findtext(f"{{{_NS}}}groupId"), dep.findtext(f"{{{_NS}}}artifactId"))
        for dep in deps_el.findall(f"{{{_NS}}}dependency")
    }

    added: list[str] = []
    for artifact_id in artifact_ids:
        group_id, version = _POM_DEPENDENCY_CATALOG.get(artifact_id, (None, None))
        if not group_id:
            continue
        if (group_id, artifact_id) in existing:
            continue

        dep_el = ET.SubElement(deps_el, f"{{{_NS}}}dependency")
        ET.SubElement(dep_el, f"{{{_NS}}}groupId").text = group_id
        ET.SubElement(dep_el, f"{{{_NS}}}artifactId").text = artifact_id
        if version:
            ET.SubElement(dep_el, f"{{{_NS}}}version").text = version
        added.append(artifact_id)
        existing.add((group_id, artifact_id))

    if not added:
        return []

    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")

    tree.write(pom_path, encoding="UTF-8", xml_declaration=True)
    logger.info("pom.xml 已补充依赖: {}", ", ".join(added))
    return added


def patch_pom_for_compile_errors(project_dir: Path, compile_message: str) -> list[str]:
    artifacts = infer_missing_artifacts(compile_message)
    if not artifacts:
        return []
    pom_path = project_dir / "pom.xml"
    return ensure_pom_dependencies(pom_path, artifacts)
