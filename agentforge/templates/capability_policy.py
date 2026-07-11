"""Spring Boot 能力层生态校验：拒绝非本生态技术栈。"""

from __future__ import annotations

import re

from agentforge.templates.capability import CapabilityRegistry

# 允许 LLM 造层 / 推断的 Spring Boot 生态能力（可扩展）
SPRING_BOOT_ECO_ALLOWLIST: frozenset[str] = frozenset({
    "springdoc",
    "mybatis",
    "redis",
    "kafka",
    "rabbitmq",
    "jwt",
    "lombok",
    "postgresql",
    "mysql",
    "mongodb",
    "elasticsearch",
    "flyway",
    "liquibase",
    "security",
    "oauth2",
    "graphql",
    "quartz",
    "mail",
    "websocket",
    "actuator",
    "validation",
    "mapstruct",
    "druid",
    "h2",
    "jpa",
    "hibernate",
    "thymeleaf",
    "freemarker",
    "minio",
    "oss",
    "nacos",
    "sentinel",
    "seata",
    "shardingsphere",
    "caffeine",
    "ehcache",
})

# 明确不属于 Spring Boot 后端工程能力层
NON_SPRING_BOOT_BLOCKLIST: frozenset[str] = frozenset({
    "react",
    "vue",
    "vuejs",
    "angular",
    "nextjs",
    "nuxt",
    "svelte",
    "django",
    "flask",
    "fastapi",
    "laravel",
    "rails",
    "ruby",
    "golang",
    "rust",
    "python",
    "node",
    "nodejs",
    "express",
    "nestjs",
    "kotlin-android",
    "android",
    "ios",
    "swift",
    "flutter",
    "uniapp",
    "小程序",
    "tensorflow",
    "pytorch",
    "kubernetes",
    "k8s",
    "docker",
    "terraform",
    "ansible",
    "php",
    "wordpress",
})

# 消息级非生态技术词（配合「加/启用」意图时直接拒绝）
NON_ECOSYSTEM_MESSAGE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\breact\b", "React 前端"),
    (r"\bvue\b", "Vue 前端"),
    (r"\bangular\b", "Angular 前端"),
    (r"\bnext\.?js\b", "Next.js 前端"),
    (r"\bnuxt\b", "Nuxt 前端"),
    (r"\bdjango\b", "Django"),
    (r"\bflask\b", "Flask"),
    (r"\bfastapi\b", "FastAPI"),
    (r"\blaravel\b", "Laravel"),
    (r"\brails\b", "Ruby on Rails"),
    (r"\bgolang\b|\bgo语言\b", "Go 语言生态"),
    (r"\brust\b", "Rust 生态"),
    (r"\bnode\.?js\b|\bnodejs\b", "Node.js"),
    (r"\bflutter\b", "Flutter"),
    (r"小程序", "微信小程序/小程序"),
    (r"\bandroid\b", "Android"),
    (r"\bios\b", "iOS"),
    (r"\bkubernetes\b|\bk8s\b", "Kubernetes"),
)


class CapabilityRejectedError(ValueError):
    """能力层请求被生态策略拒绝。"""


class CapabilityPolicy:
    """仅允许 Spring Boot 生态内的能力叠加。"""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or CapabilityRegistry()

    def is_allowed(
        self,
        capability_id: str,
        *,
        framework_version: str = "4.0",
    ) -> bool:
        return self.check(capability_id, framework_version=framework_version) is None

    def check(
        self,
        capability_id: str,
        *,
        framework_version: str = "4.0",
    ) -> str | None:
        cap_id = capability_id.lower().strip()
        if not cap_id or cap_id == "base":
            return "无效能力层标识"

        # 已入库（官方或 _generated）视为已审核通过
        if self.registry.exists(cap_id, framework_version):
            return None

        if cap_id in NON_SPRING_BOOT_BLOCKLIST:
            return (
                f"「{cap_id}」不属于 Spring Boot 后端能力层。"
                "当前项目仅支持 Spring Boot 生态（如 springdoc、mybatis、redis、kafka 等）。"
            )

        if cap_id in SPRING_BOOT_ECO_ALLOWLIST:
            return None

        return (
            f"「{cap_id}」未在 Spring Boot 生态允许列表中，无法自动造层。"
            "请使用已支持的技术（如 redis、mybatis、springdoc），"
            "或由管理员手工添加官方能力层后再启用。"
        )

    def assert_allowed(
        self,
        capability_id: str,
        *,
        framework_version: str = "4.0",
    ) -> None:
        reason = self.check(capability_id, framework_version=framework_version)
        if reason:
            raise CapabilityRejectedError(reason)

    def scan_message(
        self,
        message: str,
        *,
        has_enable_intent: bool,
    ) -> list[tuple[str, str]]:
        """扫描消息中的非生态技术提及。返回 [(标签, 原因), ...]。"""
        if not has_enable_intent:
            return []

        lowered = message.lower()
        hits: list[tuple[str, str]] = []
        for pattern, label in NON_ECOSYSTEM_MESSAGE_PATTERNS:
            if re.search(pattern, lowered, re.IGNORECASE):
                hits.append((
                    label,
                    f"检测到非 Spring Boot 生态技术「{label}」，无法作为能力层叠加。",
                ))
        return hits

    def partition(
        self,
        capability_ids: list[str],
        *,
        framework_version: str = "4.0",
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """拆分为 (允许, [(id, 原因), ...]拒绝)。"""
        allowed: list[str] = []
        rejected: list[tuple[str, str]] = []
        for cap_id in capability_ids:
            reason = self.check(cap_id, framework_version=framework_version)
            if reason:
                rejected.append((cap_id, reason))
            else:
                allowed.append(cap_id)
        return allowed, rejected

    @staticmethod
    def build_rejection_message(
        rejected_caps: list[tuple[str, str]],
        message_hits: list[tuple[str, str]],
    ) -> str:
        lines = [
            "无法叠加请求的能力层：当前 AgentForge 项目仅支持 **Spring Boot 后端生态**。",
            "",
        ]
        seen: set[str] = set()
        for cap_id, reason in rejected_caps:
            if reason not in seen:
                lines.append(f"- {reason}")
                seen.add(reason)
        for _label, reason in message_hits:
            if reason not in seen:
                lines.append(f"- {reason}")
                seen.add(reason)
        lines.extend([
            "",
            "可尝试的 Spring Boot 能力示例：",
            "- `springdoc`（Swagger 文档）",
            "- `mybatis` / `jpa`（数据访问）",
            "- `redis`（缓存）",
            "- `kafka` / `rabbitmq`（消息队列）",
            "",
            "前端框架（React/Vue）、其他语言后端（Django/Go）请使用对应技术栈项目，不在本模板范围内。",
        ])
        return "\n".join(lines)
