"""Spring Boot 域元数据（无 agents 依赖，避免循环导入）。"""

from __future__ import annotations

import re

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "entity": ("entity", "model", "实体", "dto", "vo", "表"),
    "mapper": ("mapper", "mybatis", "dao", "repository", "数据库"),
    "service": ("service", "业务", "逻辑"),
    "controller": ("controller", "rest", "api", "接口", "请求", "crud"),
    "config": ("config", "配置", "yaml", "properties"),
}

DOMAIN_EXECUTION_ORDER: list[str] = [
    "entity",
    "mapper",
    "service",
    "controller",
    "config",
]

# 中文业务词 → Java PascalCase 实体名（长词优先匹配）
CHINESE_ENTITY_ALIASES: tuple[tuple[str, str], ...] = (
    ("采购系统", "Purchase"),
    ("采购管理", "Purchase"),
    ("订单系统", "Order"),
    ("用户管理", "User"),
    ("商品管理", "Product"),
    ("供应商", "Supplier"),
    ("采购", "Purchase"),
    ("订单", "Order"),
    ("用户", "User"),
    ("商品", "Product"),
    ("库存", "Inventory"),
    ("仓库", "Warehouse"),
    ("合同", "Contract"),
    ("审批", "Approval"),
    ("财务", "Finance"),
    ("人事", "Employee"),
    ("客户", "Customer"),
    ("支付", "Payment"),
    ("发票", "Invoice"),
    ("物流", "Logistics"),
    ("考勤", "Attendance"),
    ("考勤管理", "Attendance"),
)

JAVA_ENTITY_SUFFIXES: tuple[str, ...] = ("系统", "模块", "管理", "平台", "中心", "服务")

ENGLISH_NAME_SKIP: frozenset[str] = frozenset({
    "crud", "rest", "api", "demo", "the", "a", "an", "module", "system",
})

_ENGLISH_CLASS = r"([A-Za-z][A-Za-z0-9]*)"


def normalize_entity_name(raw: str) -> str:
    """规范为 Java PascalCase 英文类名前缀。"""
    name = raw.strip()
    if not name:
        return "User"

    for phrase, english in CHINESE_ENTITY_ALIASES:
        if phrase == name or phrase in name:
            return english

    if re.fullmatch(_ENGLISH_CLASS, name):
        normalized = name[0].upper() + name[1:]
        if normalized.lower() not in ENGLISH_NAME_SKIP:
            return normalized

    stripped = name
    for suffix in JAVA_ENTITY_SUFFIXES:
        if stripped.endswith(suffix) and len(stripped) > len(suffix):
            stripped = stripped[: -len(suffix)]
            break
    if stripped != name:
        return normalize_entity_name(stripped)

    if re.search(r"[\u4e00-\u9fff]", name):
        return "BizModule"

    return "User"


def guess_entity_name(text: str) -> str:
    english_patterns = (
        rf"{_ENGLISH_CLASS}Controller",
        rf"{_ENGLISH_CLASS}ServiceImpl",
        rf"{_ENGLISH_CLASS}Service",
        rf"{_ENGLISH_CLASS}Mapper",
        rf"{_ENGLISH_CLASS}Entity",
        rf"{_ENGLISH_CLASS}\s*模块",
        rf"{_ENGLISH_CLASS}模块",
        rf"生成\s*{_ENGLISH_CLASS}",
        rf"创建\s*{_ENGLISH_CLASS}",
    )
    for pattern in english_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = normalize_entity_name(match.group(1))
            if candidate not in ("User", "BizModule") or match.group(1).lower() not in ENGLISH_NAME_SKIP:
                return candidate

    chinese_patterns = (
        r"([\u4e00-\u9fff]{2,12})系统",
        r"([\u4e00-\u9fff]{2,12})模块",
        r"生成\s*([\u4e00-\u9fff]{2,12})",
        r"创建\s*([\u4e00-\u9fff]{2,12})",
        r"实现\s*([\u4e00-\u9fff]{2,12})",
    )
    for pattern in chinese_patterns:
        match = re.search(pattern, text)
        if match:
            return normalize_entity_name(match.group(1))

    for phrase, english in CHINESE_ENTITY_ALIASES:
        if phrase in text:
            return english

    return "User"


def java_class_name(entity: str, suffix: str = "") -> str:
    """实体前缀 + 层后缀，如 Purchase + Mapper → PurchaseMapper。"""
    base = normalize_entity_name(entity)
    return f"{base}{suffix}"


def sort_domains(domains: list[str]) -> list[str]:
    order_index = {d: i for i, d in enumerate(DOMAIN_EXECUTION_ORDER)}
    return sorted(domains, key=lambda d: order_index.get(d, 999))
