"""LangGraph 状态与 Handoff 定义。"""

from __future__ import annotations

from typing import Any, TypedDict

from agentforge.agents.handoff import DomainResult
from agentforge.plugins.base import HandoffPacket


class AgentState(TypedDict, total=False):
    session_id: str
    project_id: str
    tech_stack: str
    framework_version: str
    user_message: str
    route_domains: list[str]
    handoffs: list[HandoffPacket]
    domain_results: list[DomainResult]
    domain_outputs: dict[str, str]
    system_prompt: str
    final_prompt: str
    template_stack: list[str]
    metadata: dict[str, Any]
