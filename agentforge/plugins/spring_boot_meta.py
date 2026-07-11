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


def guess_entity_name(text: str) -> str:
    patterns = (
        r"(\w+)Controller",
        r"(\w+)Service",
        r"(\w+)Mapper",
        r"(\w+)Entity",
        r"(\w+)\s*模块",
        r"(\w+)模块",
        r"(\w+)实体",
        r"生成\s*(\w+)",
        r"创建\s*(\w+)",
    )
    skip = {"crud", "rest", "api", "demo", "user"}
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1)
            if name.lower() not in skip:
                return name[:1].upper() + name[1:]
    return "User"


def sort_domains(domains: list[str]) -> list[str]:
    order_index = {d: i for i, d in enumerate(DOMAIN_EXECUTION_ORDER)}
    return sorted(domains, key=lambda d: order_index.get(d, 999))
