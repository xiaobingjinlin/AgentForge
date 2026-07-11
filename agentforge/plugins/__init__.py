"""框架插件注册与初始化。"""

from __future__ import annotations

from agentforge.core.registry import PluginRegistry
from agentforge.plugins.base import FrameworkPlugin
from agentforge.plugins.spring_boot import SpringBootPlugin

# 预留：future python / go / vue 插件在此 register
framework_registry: PluginRegistry[FrameworkPlugin] = PluginRegistry("framework")


def init_plugins() -> None:
    """注册内置框架插件。重复调用安全。"""
    if framework_registry.list_names():
        return
    framework_registry.register("spring-boot", SpringBootPlugin())


def get_framework(name: str) -> FrameworkPlugin:
    return framework_registry.get(name)
