"""LangChain 沙盒工具封装，供 Agent / LangGraph 调用。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from agentforge.sandbox.manager import SandboxManager


class WriteFileInput(BaseModel):
    relative_path: str = Field(description="沙盒内相对路径，如 src/main/java/App.java")
    content: str = Field(description="文件内容")


class ReadFileInput(BaseModel):
    relative_path: str = Field(description="沙盒内相对路径")


class ListFilesInput(BaseModel):
    relative_path: str = Field(default=".", description="沙盒内相对目录，默认根目录")


class RunCommandInput(BaseModel):
    command: str = Field(description="要在沙盒内执行的 shell 命令，受白名单限制")


def build_sandbox_tools(manager: SandboxManager, project_id: str) -> list[StructuredTool]:
    """为指定项目构建一组 LangChain 沙盒工具。"""

    def write_file(relative_path: str, content: str) -> str:
        path = manager.write_text(project_id, relative_path, content)
        return f"已写入: {path}"

    def read_file(relative_path: str) -> str:
        return manager.read_text(project_id, relative_path)

    def list_files(relative_path: str = ".") -> str:
        files = manager.list_files(project_id, relative_path)
        return "\n".join(files) if files else "(空)"

    def run_command(command: str) -> str:
        result = manager.run_command(project_id, command)
        stdout = result["stdout"] or ""
        stderr = result["stderr"] or ""
        return (
            f"exit_code={result['exit_code']}\n"
            f"--- stdout ---\n{stdout}\n"
            f"--- stderr ---\n{stderr}"
        ).strip()

    return [
        StructuredTool.from_function(
            func=write_file,
            name="sandbox_write_file",
            description="在沙盒内写入或覆盖文件",
            args_schema=WriteFileInput,
        ),
        StructuredTool.from_function(
            func=read_file,
            name="sandbox_read_file",
            description="读取沙盒内文件内容",
            args_schema=ReadFileInput,
        ),
        StructuredTool.from_function(
            func=list_files,
            name="sandbox_list_files",
            description="列出沙盒目录下的文件",
            args_schema=ListFilesInput,
        ),
        StructuredTool.from_function(
            func=run_command,
            name="sandbox_run_command",
            description="在沙盒目录内执行受白名单限制的命令（如 mvn compile）",
            args_schema=RunCommandInput,
        ),
    ]
