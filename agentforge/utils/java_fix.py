"""Java 源码确定性修复与 Maven 错误解析。"""

from __future__ import annotations

import re

from agentforge.utils.code_text import strip_code_fences

_JAVA_CLASS_DECL = re.compile(
    r"\b((?:public\s+)?(?:class|interface|enum)\s+)([A-Za-z_][\w$]*)"
)
_JAVA_CLASS_DECL_ANY = re.compile(
    r"\b((?:public\s+)?(?:class|interface|enum)\s+)([^\s{]+)"
)
_MAVEN_FILE_ERROR = re.compile(
    r"([^:\s]+\.java):\[(\d+),(\d+)\]\s*(.+)$"
)
_SRC_JAVA = "src/main/java/"


def infer_package_from_path(file_path: str) -> str | None:
    normalized = file_path.replace("\\", "/")
    if _SRC_JAVA not in normalized:
        return None
    rel = normalized.split(_SRC_JAVA, 1)[1]
    parts = rel.split("/")
    if len(parts) < 2:
        return None
    return ".".join(parts[:-1])


def java_path_suffix(file_path: str) -> str:
    normalized = file_path.replace("\\", "/")
    if _SRC_JAVA in normalized:
        return normalized.split(_SRC_JAVA, 1)[1]
    return normalized.lstrip("/")


def paths_refer_to_same_java(left: str, right: str) -> bool:
    return java_path_suffix(left) == java_path_suffix(right)


def remove_markdown_fences(code: str) -> str:
    cleaned = strip_code_fences(code)
    lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


def ensure_package_declaration(code: str, file_path: str) -> str:
    package = infer_package_from_path(file_path)
    if not package or f"package {package}" in code:
        return code
    body = code.lstrip()
    if body.startswith("package "):
        return code
    return f"package {package};\n\n{body}"


def ensure_class_name_matches_file(code: str, file_path: str) -> str:
    filename = file_path.rsplit("/", 1)[-1].removesuffix(".java")
    match = _JAVA_CLASS_DECL.search(code)
    if match and match.group(2) == filename:
        return code

    any_match = _JAVA_CLASS_DECL_ANY.search(code)
    if not any_match:
        return code
    current_name = any_match.group(2)
    if current_name == filename:
        return code
    return (
        code[: any_match.start(2)]
        + filename
        + code[any_match.end(2) :]
    )


def apply_deterministic_java_fixes(code: str, file_path: str) -> str:
    if not file_path.endswith(".java"):
        return code
    fixed = remove_markdown_fences(code)
    fixed = ensure_package_declaration(fixed, file_path)
    fixed = ensure_class_name_matches_file(fixed, file_path)
    return fixed


def parse_maven_errors(message: str) -> dict[str, list[str]]:
    """解析 Maven 输出，按 Java 文件聚合错误行。"""
    errors: dict[str, list[str]] = {}
    for line in message.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _MAVEN_FILE_ERROR.search(stripped)
        if not match:
            continue
        raw_path, row, col, detail = match.groups()
        rel_path = _normalize_maven_java_path(raw_path)
        errors.setdefault(rel_path, []).append(f"line {row},{col}: {detail.strip()}")
    return errors


def _normalize_maven_java_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if _SRC_JAVA in normalized:
        return _SRC_JAVA + normalized.split(_SRC_JAVA, 1)[1]
    return normalized
