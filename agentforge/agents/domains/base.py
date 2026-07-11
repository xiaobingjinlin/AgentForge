"""Spring Boot 技术域子 Agent 接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from agentforge.plugins.base import HandoffPacket

if TYPE_CHECKING:
    from agentforge.agents.handoff import DomainResult


@dataclass(frozen=True)
class DomainAgentSpec:
    domain: str
    agent_name: str
    execution_order: int
    model_key: str


class DomainAgent(Protocol):
    spec: DomainAgentSpec

    def target_file(self, handoff: HandoffPacket) -> str:
        ...

    def system_prompt(self, framework_version: str) -> str:
        ...

    def build_user_prompt(
        self,
        handoff: HandoffPacket,
        upstream: dict[str, DomainResult],
        *,
        rag_context: str = "",
    ) -> str:
        ...

    def dry_run_code(self, handoff: HandoffPacket) -> str:
        ...
