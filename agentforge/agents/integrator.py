"""结果整合 Agent：合并各域产出。"""

from __future__ import annotations

from collections.abc import Iterator

from agentforge.agents.handoff import DomainResult, build_integrate_prompt
from agentforge.utils.llm_util import CHAT_MODELS, LLMUtil


class IntegratorAgent:
    """第三层：整合各 SubGraph 结果，流式输出最终答复。"""

    def __init__(self, llm: LLMUtil | None = None) -> None:
        self.llm = llm or LLMUtil()

    def prepare(
        self,
        user_message: str,
        route_domains: list[str],
        results: list[DomainResult],
    ) -> tuple[str, str]:
        integrate_prompt = build_integrate_prompt(user_message, route_domains, results)
        system = (
            "你是 AgentForge 整合 Agent。"
            "请基于各域 Agent 的产出，生成结构清晰、可落地的最终方案。"
        )
        return system, integrate_prompt

    def stream(
        self,
        user_message: str,
        route_domains: list[str],
        results: list[DomainResult],
    ) -> Iterator[str]:
        system, prompt = self.prepare(user_message, route_domains, results)
        yield from self.llm.stream_chat(
            CHAT_MODELS["router"],
            prompt,
            system=system,
            max_tokens=2048,
        )
