"""对话意图识别：自动检测并启用 Spring Boot 能力层。"""

from __future__ import annotations

import re

from agentforge.plugins.spring_boot_meta import DOMAIN_KEYWORDS
from agentforge.templates.capability import BASE_LAYER_ID, CapabilityRegistry, resolve_stack
from agentforge.templates.capability_policy import CapabilityPolicy

# 启用能力层的动词/意图
ENABLE_VERBS: tuple[str, ...] = (
    "加",
    "加上",
    "添加",
    "启用",
    "接入",
    "集成",
    "引入",
    "打开",
    "配置",
    "安装",
    "需要",
    "想要",
    "要用",
    "使用",
    "支持",
    "add",
    "enable",
    "integrate",
    "install",
)

# 内置关键词（manifest 未声明 keywords 时的兜底）
DEFAULT_CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "springdoc": (
        "springdoc",
        "swagger",
        "openapi",
        "open api",
        "接口文档",
        "api文档",
        "api 文档",
        "swagger-ui",
    ),
}

# 未入库能力的技术词推断（Registry 无匹配时触发 LLM 造层）
INFER_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bredis\b", "redis"),
    (r"redis缓存", "redis"),
    (r"\bmybatis\b", "mybatis"),
    (r"\bkafka\b", "kafka"),
    (r"\brabbitmq\b", "rabbitmq"),
    (r"\bjwt\b", "jwt"),
    (r"\blombok\b", "lombok"),
    (r"postgresql", "postgresql"),
    (r"\bmysql\b", "mysql"),
)


class CapabilityRouter:
    """从用户消息识别要叠加的 Spring Boot 能力层。"""

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        policy: CapabilityPolicy | None = None,
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        self.policy = policy or CapabilityPolicy(registry=self.registry)

    def keyword_map(self, framework_version: str = "4.0") -> dict[str, tuple[str, ...]]:
        mapping: dict[str, set[str]] = {}
        for cap_id in self.registry.list_ids(framework_version):
            manifest = self.registry.load(cap_id, framework_version)
            words: set[str] = {cap_id, manifest.name.lower()}
            raw = self.registry.load_raw(cap_id, framework_version)
            for kw in raw.get("keywords", []):
                words.add(str(kw).lower())
            for kw in DEFAULT_CAPABILITY_KEYWORDS.get(cap_id, ()):
                words.add(kw.lower())
            mapping[cap_id] = words
        return {k: tuple(sorted(v)) for k, v in mapping.items()}

    def detect(
        self,
        message: str,
        *,
        framework_version: str = "4.0",
        current_stack: list[str] | None = None,
    ) -> list[str]:
        """返回待启用的能力 id 列表（已启用、无启用意图的不返回）。"""
        text = message.strip()
        if not text:
            return []

        if not self._has_enable_intent(text):
            return []

        stack = list(current_stack or [BASE_LAYER_ID])
        keywords = self.keyword_map(framework_version)
        matched: list[str] = []

        lowered = text.lower()
        for cap_id, words in keywords.items():
            if cap_id in stack:
                continue
            if any(_keyword_hit(lowered, word) for word in words):
                matched.append(cap_id)

        if not matched:
            return []

        candidate_stack = stack + matched
        try:
            ordered = resolve_stack(
                candidate_stack,
                framework_version=framework_version,
                registry=self.registry,
            )
        except ValueError:
            return matched

        return [cap for cap in ordered if cap not in stack and cap != BASE_LAYER_ID]

    def infer_missing(
        self,
        message: str,
        *,
        framework_version: str = "4.0",
        current_stack: list[str] | None = None,
    ) -> list[str]:
        """识别 Registry 中尚不存在、需 LLM 生成的新能力层。"""
        text = message.strip()
        if not text or not self._has_enable_intent(text):
            return []

        stack = list(current_stack or [BASE_LAYER_ID])
        existing = set(self.registry.list_ids(framework_version))
        lowered = text.lower()
        missing: list[str] = []

        for pattern, cap_id in INFER_PATTERNS:
            if cap_id in stack or cap_id in existing:
                continue
            if re.search(pattern, lowered):
                missing.append(cap_id)

        verb_match = re.search(
            r"(?:加|加上|添加|启用|接入|集成|引入|安装|使用|支持)\s*([a-zA-Z][\w-]{1,24})",
            text,
            re.IGNORECASE,
        )
        if verb_match:
            cap_id = _normalize_cap_id(verb_match.group(1))
            if (
                cap_id
                and cap_id != BASE_LAYER_ID
                and cap_id not in stack
                and cap_id not in existing
                and cap_id not in missing
            ):
                missing.append(cap_id)

        return missing

    def collect_to_enable(
        self,
        message: str,
        *,
        framework_version: str = "4.0",
        current_stack: list[str] | None = None,
    ) -> tuple[list[str], list[str], list[tuple[str, str]]]:
        """返回 (已注册待启用, 需生成后启用, [(id, 拒绝原因), ...])。"""
        stack = list(current_stack or [BASE_LAYER_ID])
        registered = self.detect(message, framework_version=framework_version, current_stack=stack)
        missing = self.infer_missing(message, framework_version=framework_version, current_stack=stack)
        missing = [m for m in missing if m not in registered]

        allowed_reg, rej_reg = self.policy.partition(registered, framework_version=framework_version)
        allowed_gen, rej_gen = self.policy.partition(missing, framework_version=framework_version)
        rejected = rej_reg + rej_gen
        return allowed_reg, allowed_gen, rejected

    def scan_non_ecosystem(
        self,
        message: str,
    ) -> list[tuple[str, str]]:
        """消息中的非 Spring Boot 生态技术提及（需配合启用意图）。"""
        return self.policy.scan_message(
            message,
            has_enable_intent=self._has_enable_intent(message),
        )

    def match_mentioned(
        self,
        message: str,
        *,
        framework_version: str = "4.0",
    ) -> list[str]:
        """消息中出现的所有能力 id（不论是否已启用）。"""
        lowered = message.lower()
        keywords = self.keyword_map(framework_version)
        matched: list[str] = []
        for cap_id, words in keywords.items():
            if any(_keyword_hit(lowered, word) for word in words):
                matched.append(cap_id)
        return matched

    def is_capability_only(
        self,
        message: str,
        detected: list[str],
    ) -> bool:
        """仅叠加能力、无业务代码生成意图。"""
        if not detected:
            return False
        return not self.has_codegen_intent(message)

    @staticmethod
    def has_codegen_intent(message: str) -> bool:
        lowered = message.lower()
        strong_hints = ("生成", "创建", "编写", "实现", "开发", "crud", "模块", "落盘", "generate", "create")
        if any(hint in lowered for hint in strong_hints):
            return True
        if re.search(r"(\w+)\s*模块", message, re.IGNORECASE):
            return True
        if re.search(r"(\w+)(Controller|Service|Mapper|Entity)", message, re.IGNORECASE):
            return True

        skip_contexts = ("接口文档", "api文档", "api 文档", "swagger", "openapi", "springdoc")
        if any(ctx in lowered for ctx in skip_contexts):
            return False

        for keywords in DOMAIN_KEYWORDS.values():
            for kw in keywords:
                if kw in lowered:
                    return True
        return False

    @staticmethod
    def build_summary(
        enabled: list[dict[str, object]],
        *,
        template_stack: list[str],
    ) -> str:
        if not enabled:
            return "未检测到需要启用的能力层。"

        lines = ["已为项目叠加以下能力层：", ""]
        for item in enabled:
            cap_id = str(item.get("capability_id", ""))
            name = cap_id
            if item.get("already_enabled"):
                lines.append(f"- **{cap_id}**：已在项目中启用")
            else:
                lines.append(f"- **{cap_id}**：已启用并写入沙盒")
        lines.append("")
        lines.append(f"当前能力栈：`{' + '.join(template_stack)}`")

        if "springdoc" in template_stack:
            lines.append("")
            lines.append("SpringDoc 已就绪，启动应用后可访问：")
            lines.append("- Swagger UI：`http://localhost:8080/swagger-ui.html`")
            lines.append("- OpenAPI JSON：`http://localhost:8080/v3/api-docs`")

        lines.append("")
        lines.append("如需继续生成业务模块（如 Order CRUD），请直接描述需求。")
        return "\n".join(lines)

    @staticmethod
    def build_generation_summary(results: list[dict[str, object]]) -> str:
        lines = ["已通过 LLM 生成并入库以下能力层：", ""]
        for item in results:
            cap_id = str(item.get("capability_id", ""))
            path = item.get("path", "")
            lines.append(f"- **{cap_id}** → `{path}`")
        lines.append("")
        lines.append("后续对话可直接复用，无需再次生成。")
        return "\n".join(lines)

    @staticmethod
    def _has_enable_intent(message: str) -> bool:
        lowered = message.lower()
        return any(verb in lowered for verb in ENABLE_VERBS)


def _keyword_hit(text: str, keyword: str) -> bool:
    keyword = keyword.lower().strip()
    if not keyword:
        return False
    if " " in keyword or "-" in keyword:
        return keyword in text
    if re.search(rf"\b{re.escape(keyword)}\b", text):
        return True
    return keyword in text


def _normalize_cap_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]", "-", raw.lower()).strip("-")
    skip = {"项目", "项目", "the", "a", "an", "spring", "boot", "能力", "层"}
    if cleaned in skip or len(cleaned) < 2:
        return ""
    return cleaned
