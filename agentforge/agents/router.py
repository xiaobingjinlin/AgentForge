"""路由分发 Agent：分析任务并生成 Handoff。"""

from __future__ import annotations

import json
import re

from loguru import logger

from agentforge.plugins import get_framework
from agentforge.plugins.base import HandoffPacket
from agentforge.utils.llm_util import CHAT_MODELS, LLMUtil


class RouterAgent:
    """第一层：路由分发，将任务拆解到技术域。"""

    def __init__(self, llm: LLMUtil | None = None) -> None:
        self.llm = llm or LLMUtil()

    def route(
        self,
        user_message: str,
        *,
        tech_stack: str = "spring-boot",
        framework_version: str = "4.0",
        use_llm: bool = True,
    ) -> tuple[list[str], list[HandoffPacket], str]:
        plugin = get_framework(tech_stack)
        plugin = get_framework(tech_stack)
        domains = self._route_domains(user_message, plugin, use_llm=use_llm)
        handoffs = [plugin.build_handoff(d, user_message) for d in domains]
        system_prompt = plugin.system_prompt(framework_version)
        logger.info("路由结果: domains={}", domains)
        return domains, handoffs, system_prompt

    def _route_domains(
        self,
        user_message: str,
        plugin: object,
        *,
        use_llm: bool,
    ) -> list[str]:
        fallback = plugin.detect_domains(user_message)  # type: ignore[union-attr]
        available = plugin.domains()  # type: ignore[union-attr]
        if not use_llm:
            return fallback

        prompt = (
            f"用户需求: {user_message}\n"
            f"可选技术域: {', '.join(available)}\n"
            '请返回 JSON，格式: {"domains": ["controller", "service"]}\n'
            "只选必要域，按依赖顺序排列（如 entity → mapper → service → controller）。"
        )
        try:
            raw = self.llm.chat(
                CHAT_MODELS["router"],
                prompt,
                system="你是后端任务路由器，只输出 JSON。",
                max_tokens=256,
            )
            parsed = self._parse_domains_json(raw, available)
            return parsed or fallback
        except Exception as exc:
            logger.warning("LLM 路由失败，回退关键词: {}", exc)
            return fallback

    @staticmethod
    def _parse_domains_json(raw: str, available: list[str]) -> list[str]:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group())
        domains = data.get("domains", [])
        valid = [d for d in domains if d in available]
        return valid
