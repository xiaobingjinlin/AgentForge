"""可插拔模块注册中心。"""

from __future__ import annotations

from typing import Generic, TypeVar

from loguru import logger

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    """通用插件注册表，按名称注册与解析。"""

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._plugins: dict[str, T] = {}

    def register(self, name: str, plugin: T, *, overwrite: bool = False) -> None:
        key = name.strip().lower()
        if key in self._plugins and not overwrite:
            raise ValueError(f"{self._kind} 插件已存在: {name}")
        self._plugins[key] = plugin
        logger.debug("注册 {} 插件: {}", self._kind, key)

    def get(self, name: str) -> T:
        key = name.strip().lower()
        if key not in self._plugins:
            available = ", ".join(sorted(self._plugins)) or "(无)"
            raise KeyError(f"未找到 {self._kind} 插件: {name}，可用: {available}")
        return self._plugins[key]

    def list_names(self) -> list[str]:
        return sorted(self._plugins)

    def items(self) -> list[tuple[str, T]]:
        return [(name, self._plugins[name]) for name in self.list_names()]
