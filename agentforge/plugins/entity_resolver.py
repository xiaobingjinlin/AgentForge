"""业务实体名解析：中文需求 → 英文 PascalCase 类名前缀。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from agentforge.plugins.spring_boot_meta import (
    CHINESE_ENTITY_ALIASES,
    guess_entity_name,
    normalize_entity_name,
)
from agentforge.utils.llm_util import CHAT_MODELS, LLMUtil

_CHINESE_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"([\u4e00-\u9fff]{2,16})系统"),
    re.compile(r"([\u4e00-\u9fff]{2,16})模块"),
    re.compile(r"做一个\s*([\u4e00-\u9fff]{2,12}(?:管理)?)系统"),
    re.compile(r"(?:要|请|帮我)?生成\s*([\u4e00-\u9fff]{2,16})"),
    re.compile(r"(?:开发|实现)\s*([\u4e00-\u9fff]{2,16})"),
    re.compile(r"([\u4e00-\u9fff]{2,16})管理"),
)
_ENGLISH_CLASS = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


@dataclass(frozen=True)
class EntityResolution:
    """实体英文名解析结果。"""

    english_name: str
    source_phrase: str
    method: str  # rule | alias | llm

    @property
    def display_label(self) -> str:
        if self.source_phrase and re.search(r"[\u4e00-\u9fff]", self.source_phrase):
            return f"「{self.source_phrase}」→ `{self.english_name}`"
        return f"`{self.english_name}`"


def extract_chinese_business_phrase(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None

    for phrase, _ in CHINESE_ENTITY_ALIASES:
        if phrase in text:
            return phrase

    for pattern in _CHINESE_PHRASE_PATTERNS:
        match = pattern.search(text)
        if match:
            phrase = match.group(1).strip()
            if phrase:
                return phrase
    return None


def resolve_entity_name(
    user_message: str,
    *,
    llm: LLMUtil | None = None,
    use_llm: bool = True,
) -> EntityResolution:
    """先解析/翻译业务实体英文名为 PascalCase，再供各域生成代码使用。"""
    text = user_message.strip()
    source_phrase = extract_chinese_business_phrase(text) or text[:40]

    rule_guess = normalize_entity_name(guess_entity_name(text))
    if _is_confident_rule_match(text, rule_guess):
        return EntityResolution(
            english_name=rule_guess,
            source_phrase=source_phrase,
            method="rule",
        )

    if use_llm and llm and re.search(r"[\u4e00-\u9fff]", text):
        translated = _translate_with_llm(source_phrase, llm=llm)
        if translated:
            return EntityResolution(
                english_name=translated,
                source_phrase=source_phrase,
                method="llm",
            )

    return EntityResolution(
        english_name=rule_guess,
        source_phrase=source_phrase,
        method="rule",
    )


def entity_name_constraints(resolution: EntityResolution, domain: str) -> list[str]:
    """生成 Handoff 约束：强调先翻译再编码。"""
    from agentforge.plugins.spring_boot_meta import java_class_name

    entity = resolution.english_name
    lines = [
        f"业务实体英文名: {entity}",
        f"命名解析: {resolution.display_label}（生成代码前已完成中英文映射）",
        (
            f"Java 类名必须为 PascalCase 英文，例如 "
            f"{java_class_name(entity, 'Mapper')}、{java_class_name(entity, 'Service')}、"
            f"{java_class_name(entity, 'Controller')}；禁止中文类名"
        ),
        f"仅关注 {domain} 层代码",
        "参考上游域产出保持命名一致",
        "不要输出与任务无关的解释",
    ]
    return lines


def _is_confident_rule_match(text: str, guessed: str) -> bool:
    if guessed == "BizModule":
        return False
    if guessed != "User":
        return True
    if not re.search(r"[\u4e00-\u9fff]", text):
        return True
    return False


def _translate_with_llm(phrase: str, *, llm: LLMUtil) -> str | None:
    prompt = (
        f"中文业务描述: {phrase}\n"
        "请输出对应的英文 Java 实体类名前缀（PascalCase，单个标识符）。\n"
        "要求:\n"
        "- 只输出一个英文单词或驼峰组合，如 Purchase、OrderItem、Employee\n"
        "- 不要后缀 Mapper/Service/Controller/Entity\n"
        "- 不要解释，不要标点，不要中文"
    )
    try:
        raw = llm.chat(
            CHAT_MODELS["router"],
            prompt,
            system="你是业务术语翻译器，将中文业务模块名译为英文 PascalCase 类名前缀。",
            max_tokens=32,
        )
        candidate = raw.strip().split()[0] if raw.strip() else ""
        candidate = re.sub(r"[^A-Za-z0-9]", "", candidate)
        if not _ENGLISH_CLASS.match(candidate):
            return None
        normalized = candidate[0].upper() + candidate[1:]
        logger.info("实体名 LLM 翻译: {} → {}", phrase, normalized)
        return normalized
    except Exception as exc:
        logger.warning("实体名 LLM 翻译失败: {}", exc)
        return None
