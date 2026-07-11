"""Spring Boot 各技术域独立子 Agent。"""

from __future__ import annotations

from agentforge.agents.domains.base import DomainAgentSpec
from agentforge.agents.handoff import DomainResult, handoff_to_prompt
from agentforge.plugins.base import HandoffPacket
from agentforge.plugins.spring_boot_meta import DOMAIN_EXECUTION_ORDER, guess_entity_name, sort_domains

_BASE_PKG = "com.example.demo"
_JAVA_ROOT = "src/main/java/com/example/demo"

__all__ = [
    "DOMAIN_AGENTS",
    "DOMAIN_EXECUTION_ORDER",
    "get_domain_agent",
    "guess_entity_name",
    "sort_domains",
]


def _upstream_context(upstream: dict[str, DomainResult], *, max_each: int = 400) -> str:
    if not upstream:
        return "（无上游依赖）"
    lines: list[str] = []
    for domain, result in upstream.items():
        preview = result.code[:max_each]
        if len(result.code) > max_each:
            preview += "\n... [truncated]"
        lines.append(f"[{domain}] {result.summary}\n{preview}")
    return "\n\n".join(lines)


class _BaseSpringDomainAgent:
    domain: str
    agent_name: str
    execution_order: int
    class_suffix: str

    @property
    def spec(self) -> DomainAgentSpec:
        return DomainAgentSpec(
            domain=self.domain,
            agent_name=self.agent_name,
            execution_order=self.execution_order,
            model_key="coder",
        )

    def _entity(self, handoff: HandoffPacket) -> str:
        return handoff.payload.get("entity_name", "User")

    def target_file(self, handoff: HandoffPacket) -> str:
        entity = self._entity(handoff)
        class_name = f"{entity}{self.class_suffix}"
        if self.domain == "config":
            return "src/main/resources/application-custom.yml"
        return f"{_JAVA_ROOT}/{self.domain}/{class_name}.java"

    def dry_run_code(self, handoff: HandoffPacket) -> str:
        entity = self._entity(handoff)
        if self.domain == "config":
            return f"# [{self.domain}] custom config for {entity}\napp:\n  feature:\n    enabled: true"
        return (
            f"package {_BASE_PKG}.{self.domain};\n\n"
            f"public class {entity}{self.class_suffix} {{\n"
            f"    // dry-run {self.domain}\n"
            f"}}"
        )

    def build_user_prompt(
        self,
        handoff: HandoffPacket,
        upstream: dict[str, DomainResult],
        *,
        rag_context: str = "",
    ) -> str:
        base = handoff_to_prompt(handoff)
        upstream_block = _upstream_context(upstream)
        rag_block = rag_context or "（未检索知识库）"
        return (
            f"{base}\n\n"
            f"实体名: {self._entity(handoff)}\n"
            f"目标文件: {self.target_file(handoff)}\n"
            f"上游域产出（协作上下文）:\n{upstream_block}\n"
            f"知识库参考片段:\n{rag_block}\n"
            f"请生成符合 Spring Boot 4.0 规范的代码，类名与包路径保持一致。"
        )


class EntityDomainAgent(_BaseSpringDomainAgent):
    domain = "entity"
    agent_name = "entity-agent"
    execution_order = 10
    class_suffix = ""

    def system_prompt(self, framework_version: str) -> str:
        return (
            f"你是 Spring Boot {framework_version} 实体建模专家。"
            "生成 JPA/MyBatis 实体类，含 id、核心字段、getter/setter 或 Lombok。"
            "只输出 Java 代码。"
        )

    def target_file(self, handoff: HandoffPacket) -> str:
        entity = self._entity(handoff)
        return f"{_JAVA_ROOT}/entity/{entity}.java"


class MapperDomainAgent(_BaseSpringDomainAgent):
    domain = "mapper"
    agent_name = "mapper-agent"
    execution_order = 20
    class_suffix = "Mapper"

    def system_prompt(self, framework_version: str) -> str:
        return (
            f"你是 Spring Boot {framework_version} 数据访问专家。"
            "生成 MyBatis Mapper 接口与基础 CRUD 方法，参考上游 entity 字段。"
            "只输出 Java 代码。"
        )


class ServiceDomainAgent(_BaseSpringDomainAgent):
    domain = "service"
    agent_name = "service-agent"
    execution_order = 30
    class_suffix = "Service"

    def system_prompt(self, framework_version: str) -> str:
        return (
            f"你是 Spring Boot {framework_version} 业务层专家。"
            "生成 Service 接口与实现，封装业务逻辑，依赖 Mapper 层。"
            "只输出 Java 代码。"
        )


class ControllerDomainAgent(_BaseSpringDomainAgent):
    domain = "controller"
    agent_name = "controller-agent"
    execution_order = 40
    class_suffix = "Controller"

    def system_prompt(self, framework_version: str) -> str:
        return (
            f"你是 Spring Boot {framework_version} REST 专家。"
            "生成 @RestController，提供 CRUD API，调用 Service 层。"
            "只输出 Java 代码。"
        )


class ConfigDomainAgent(_BaseSpringDomainAgent):
    domain = "config"
    agent_name = "config-agent"
    execution_order = 50
    class_suffix = "Config"

    def system_prompt(self, framework_version: str) -> str:
        return (
            f"你是 Spring Boot {framework_version} 配置专家。"
            "生成 @Configuration 或 application 配置片段。"
            "config 域可输出 YAML 或 Java 配置类。"
        )

    def build_user_prompt(
        self,
        handoff: HandoffPacket,
        upstream: dict[str, DomainResult],
        *,
        rag_context: str = "",
    ) -> str:
        base = handoff_to_prompt(handoff)
        rag_block = rag_context or "（未检索知识库）"
        return (
            f"{base}\n\n"
            f"模块: {self._entity(handoff)}\n"
            f"为已生成的各层提供必要配置（如数据源、MyBatis 扫描）。\n"
            f"上游摘要:\n{_upstream_context(upstream, max_each=300)}\n"
            f"知识库参考片段:\n{rag_block}"
        )


DOMAIN_AGENTS: dict[str, _BaseSpringDomainAgent] = {
    "entity": EntityDomainAgent(),
    "mapper": MapperDomainAgent(),
    "service": ServiceDomainAgent(),
    "controller": ControllerDomainAgent(),
    "config": ConfigDomainAgent(),
}


def get_domain_agent(domain: str) -> _BaseSpringDomainAgent:
    if domain not in DOMAIN_AGENTS:
        raise KeyError(f"未知技术域: {domain}")
    return DOMAIN_AGENTS[domain]
