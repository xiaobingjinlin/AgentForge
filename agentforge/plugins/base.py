"""可插拔技术栈框架接口。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class HandoffPacket:
    """子 Agent 之间传递的结构化上下文（控制 Token 规模）。"""

    source: str
    target: str
    task_summary: str
    relevant_files: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    payload: dict[str, str] = field(default_factory=dict)


class FrameworkPlugin(Protocol):
    """技术栈插件：模板、领域划分、Prompt、沙盒策略。"""

    @property
    def name(self) -> str:
        """技术栈标识，如 spring-boot。"""

    @property
    def display_name(self) -> str:
        """展示名称。"""

    @property
    def language(self) -> str:
        """主语言：java / python / go / typescript。"""

    @property
    def default_version(self) -> str:
        """默认框架版本。"""

    def template_dir(self, version: str | None = None) -> Path:
        """只读模板目录。"""

    def domains(self) -> list[str]:
        """可路由的技术域列表。"""

    def system_prompt(self, version: str | None = None) -> str:
        """主 Agent 系统提示词。"""

    def detect_domains(self, user_message: str) -> list[str]:
        """根据用户输入粗分技术域（骨架阶段可用规则）。"""

    def build_handoff(self, domain: str, user_message: str) -> HandoffPacket:
        """为子 Agent 构建 Handoff 包。"""
