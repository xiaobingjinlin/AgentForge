"""沙盒目录管理：隔离 Agent 文件读写与命令执行。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from loguru import logger

from agentforge.core.jdk import command_env_for_build, needs_build_env, probe_java_version

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SANDBOX_ROOT = PROJECT_ROOT / "sandbox"

# 允许在沙盒内执行的命令前缀（安全白名单）
ALLOWED_COMMANDS = (
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "find",
    "tree",
    "mvn",
    "java",
    "gradle",
    "./mvnw",
    "./gradlew",
)

DEFAULT_TIMEOUT = 120


class SandboxError(Exception):
    pass


class SandboxManager:
    """为每个项目维护独立沙盒目录，所有操作限制在目录内。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or os.getenv("SANDBOX_ROOT", str(DEFAULT_SANDBOX_ROOT)))
        self.root.mkdir(parents=True, exist_ok=True)
        logger.debug("沙盒根目录: {}", self.root)

    def project_dir(self, project_id: str) -> Path:
        safe_id = self._safe_name(project_id)
        return self.root / safe_id

    def create(self, project_id: str, *, clean: bool = False) -> Path:
        path = self.project_dir(project_id)
        if clean and path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        logger.info("沙盒已创建: {}", path)
        return path

    def destroy(self, project_id: str) -> None:
        path = self.project_dir(project_id)
        if path.exists():
            shutil.rmtree(path)
            logger.info("沙盒已销毁: {}", path)

    def resolve(self, project_id: str, relative_path: str = ".") -> Path:
        base = self.project_dir(project_id).resolve()
        target = (base / relative_path).resolve()
        if base != target and base not in target.parents:
            raise SandboxError(f"路径越界: {relative_path}")
        return target

    def write_text(self, project_id: str, relative_path: str, content: str) -> str:
        target = self.resolve(project_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.bind(project_id=project_id).info("写入文件: {}", relative_path)
        return str(target)

    def read_text(self, project_id: str, relative_path: str) -> str:
        target = self.resolve(project_id, relative_path)
        if not target.is_file():
            raise SandboxError(f"文件不存在: {relative_path}")
        return target.read_text(encoding="utf-8")

    def list_files(self, project_id: str, relative_path: str = ".") -> list[str]:
        target = self.resolve(project_id, relative_path)
        if not target.exists():
            return []
        if target.is_file():
            return [relative_path]
        return sorted(
            str(p.relative_to(self.project_dir(project_id)))
            for p in target.rglob("*")
            if p.is_file()
        )

    def run_command(
        self,
        project_id: str,
        command: str,
        *,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict[str, str | int]:
        cmd = command.strip()
        if not self._is_allowed(cmd):
            raise SandboxError(f"命令不在白名单: {cmd}")

        cwd = self.project_dir(project_id)
        cwd.mkdir(parents=True, exist_ok=True)
        env = command_env_for_build() if needs_build_env(cmd) else None
        if env and env.get("JAVA_HOME"):
            logger.bind(project_id=project_id).info(
                "执行命令: {} (JAVA_HOME={})",
                cmd,
                env["JAVA_HOME"],
            )
        else:
            logger.bind(project_id=project_id).info("执行命令: {}", cmd)

        completed = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return {
            "command": cmd,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    @staticmethod
    def _safe_name(project_id: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", project_id)
        return cleaned or "default"

    @staticmethod
    def _is_allowed(command: str) -> bool:
        first = command.split()[0] if command else ""
        return any(command == allowed or first == allowed for allowed in ALLOWED_COMMANDS)
