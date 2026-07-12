"""JDK 运行时配置：沙盒 Maven 编译使用指定 JAVA_HOME。"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from loguru import logger

_JAVA_HOME_KEYS = ("AGENTFORGE_JAVA_HOME", "JAVA_HOME", "JDK21_HOME")
_BUILD_COMMAND_PREFIXES = ("mvn", "./mvnw", "java", "./gradlew", "gradle")
_JAVA_VERSION_RE = re.compile(r'version "([^"]+)"')


def resolve_java_home() -> str | None:
    """解析用于 Maven/Java 命令的 JAVA_HOME。"""
    for key in _JAVA_HOME_KEYS:
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not path.is_dir():
            logger.warning("环境变量 {} 指向无效目录: {}", key, raw)
            continue
        java_bin = path / "bin" / "java"
        if not java_bin.is_file() and not (path / "bin").is_dir():
            logger.warning("环境变量 {} 缺少 bin/java: {}", key, path)
            continue
        return str(path.resolve())
    return None


def command_env_for_build(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """为 mvn/java 等构建命令注入 JAVA_HOME 与 PATH。"""
    env = dict(base_env or os.environ)
    java_home = resolve_java_home()
    if not java_home:
        return env

    env["JAVA_HOME"] = java_home
    java_bin = str(Path(java_home) / "bin")
    env["PATH"] = f"{java_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def needs_build_env(command: str) -> bool:
    first = command.strip().split()[0] if command.strip() else ""
    return any(first == prefix or command.strip().startswith(prefix) for prefix in _BUILD_COMMAND_PREFIXES)


def probe_java_version(*, env: dict[str, str] | None = None) -> str | None:
    run_env = command_env_for_build(env)
    java_cmd = "java"
    java_home = run_env.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "java"
        if candidate.is_file():
            java_cmd = str(candidate)

    try:
        completed = subprocess.run(
            [java_cmd, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            env=run_env,
        )
    except Exception as exc:
        logger.warning("探测 Java 版本失败: {}", exc)
        return None

    output = (completed.stderr or completed.stdout or "").strip()
    match = _JAVA_VERSION_RE.search(output)
    return match.group(1) if match else output.splitlines()[0] if output else None


def java_runtime_info() -> dict[str, str | None]:
    java_home = resolve_java_home()
    version = probe_java_version()
    return {
        "java_home": java_home,
        "java_version": version,
        "configured_by": _configured_by_key(),
    }


def log_java_runtime() -> None:
    info = java_runtime_info()
    if info["java_home"]:
        logger.info(
            "沙盒构建 Java 运行时: {} ({})",
            info["java_version"] or "unknown",
            info["java_home"],
        )
    else:
        version = info["java_version"]
        logger.warning(
            "未配置 JAVA_HOME/AGENTFORGE_JAVA_HOME，Maven 将使用系统默认 Java{}",
            f" ({version})" if version else "",
        )


def _configured_by_key() -> str | None:
    for key in _JAVA_HOME_KEYS:
        if os.getenv(key, "").strip():
            return key
    return None
