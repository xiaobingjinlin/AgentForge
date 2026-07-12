"""Handoff 上下文构建与 Token 控制。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentforge.plugins.base import HandoffPacket

MAX_TASK_SUMMARY = 500
MAX_DOMAIN_OUTPUT = 1200
MAX_INTEGRATE_INPUT = 4000


@dataclass
class DomainResult:
    domain: str
    agent: str
    summary: str
    code: str
    file_path: str = ""
    stages: list[dict[str, str]] | None = None

    def to_compact(self, *, max_code: int = MAX_DOMAIN_OUTPUT) -> str:
        code = self.code if len(self.code) <= max_code else self.code[:max_code] + "\n... [truncated]"
        path = f" ({self.file_path})" if self.file_path else ""
        return f"### {self.domain}{path} [{self.agent}]\n摘要: {self.summary}\n```\n{code}\n```"


def handoff_to_prompt(handoff: HandoffPacket) -> str:
    """将 Handoff 转为子 Agent 专用 Prompt（不含全量会话历史）。"""
    files = "\n".join(f"- {p}" for p in handoff.relevant_files) or "- (无)"
    rules = "\n".join(f"- {c}" for c in handoff.constraints) or "- (无)"
    summary = handoff.task_summary[:MAX_TASK_SUMMARY]
    return (
        f"【Handoff from {handoff.source} → {handoff.target}】\n"
        f"任务摘要: {summary}\n"
        f"相关路径:\n{files}\n"
        f"约束:\n{rules}\n"
        f"请仅完成本域代码，直接输出 Java 代码，不要多余解释。"
    )


def build_brief_codegen_summary(
    results: list[DomainResult],
    *,
    template_stack: list[str] | None = None,
    verify: object | None = None,
    entity_label: str | None = None,
) -> str:
    """代码生成完成后的简要说明（不重复贴代码）。"""
    if not results:
        return "未生成代码文件。"

    entity = entity_label or _infer_entity_label(results)
    lines = [f"已为 **{entity}** 生成 {len(results)} 个文件：", ""]
    for result in results:
        lines.append(f"- `{result.file_path}`")
    lines.append("")
    if template_stack:
        lines.append(f"能力栈：`{' + '.join(template_stack)}`")
        lines.append("")
    if verify is not None and hasattr(verify, "summary_lines"):
        lines.extend(verify.summary_lines())
        lines.append("")
    lines.append("代码可在右侧预览，或点击「一键落盘」导出。")
    return "\n".join(lines)


def _infer_entity_label(results: list[DomainResult]) -> str:
    for result in results:
        match = re.search(r"/([A-Z][A-Za-z0-9]*)(?:Mapper|Service|Controller)?\.java$", result.file_path)
        if match:
            return match.group(1)
    return "业务模块"


def build_integrate_prompt(
    user_message: str,
    route_domains: list[str],
    results: list[DomainResult],
) -> str:
    """整合层输入：仅包含各域压缩结果，控制上下文规模。"""
    blocks = [r.to_compact() for r in results]
    body = "\n\n".join(blocks)
    if len(body) > MAX_INTEGRATE_INPUT:
        body = body[:MAX_INTEGRATE_INPUT] + "\n... [truncated]"
    return (
        f"用户原始需求:\n{user_message}\n\n"
        f"已执行技术域: {', '.join(route_domains)}\n\n"
        f"各域 Agent 产出:\n{body}\n\n"
        "请整合为完整、可落地的 Spring Boot 方案。"
        "保留关键代码，用简洁中文说明文件应放在哪一层。"
    )
