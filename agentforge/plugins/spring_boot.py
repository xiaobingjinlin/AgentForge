"""Spring Boot 框架插件（MVP）。"""

from __future__ import annotations

from pathlib import Path

from agentforge.core.config import PROJECT_ROOT
from agentforge.plugins.base import HandoffPacket
from agentforge.plugins.entity_resolver import (
    EntityResolution,
    entity_name_constraints,
    resolve_entity_name,
)
from agentforge.plugins.spring_boot_meta import (
    DOMAIN_EXECUTION_ORDER,
    DOMAIN_KEYWORDS,
    sort_domains,
)


class SpringBootPlugin:
    name = "spring-boot"
    display_name = "Spring Boot"
    language = "java"
    default_version = "4.0"

    def template_dir(self, version: str | None = None) -> Path:
        ver = version or self.default_version
        return PROJECT_ROOT / "templates" / "spring-boot" / ver / "base"

    def domains(self) -> list[str]:
        return list(DOMAIN_KEYWORDS)

    def execution_order(self) -> list[str]:
        return DOMAIN_EXECUTION_ORDER

    def sort_domains(self, domains: list[str]) -> list[str]:
        return sort_domains(domains)

    def system_prompt(self, version: str | None = None) -> str:
        ver = version or self.default_version
        return (
            f"你是 AgentForge 的 Spring Boot {ver} 后端开发助手。"
            "请用简洁专业的中文回答，给出可直接落地的 Java 代码，"
            "遵循 Entity → Mapper → Service → Controller 分层协作。"
        )

    def detect_domains(self, user_message: str) -> list[str]:
        text = user_message.lower()
        matched = [
            domain
            for domain, keywords in DOMAIN_KEYWORDS.items()
            if any(k in text for k in keywords)
        ]
        if matched:
            return self.sort_domains(matched)
        return []

    def build_handoff(
        self,
        domain: str,
        user_message: str,
        *,
        entity_resolution: EntityResolution | None = None,
    ) -> HandoffPacket:
        resolution = entity_resolution or resolve_entity_name(user_message, use_llm=False)
        entity_name = resolution.english_name
        class_prefix = entity_name
        return HandoffPacket(
            source="router",
            target=f"{domain}-agent",
            task_summary=user_message[:500],
            relevant_files=[f"src/main/java/com/example/demo/{domain}/"],
            constraints=entity_name_constraints(resolution, domain),
            payload={
                "domain": domain,
                "entity_name": entity_name,
                "entity_source_phrase": resolution.source_phrase,
                "entity_name_method": resolution.method,
                "class_prefix": class_prefix,
                "framework_version": self.default_version,
            },
        )
