"""应用配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppConfig:
    project_root: Path = PROJECT_ROOT
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    default_tech_stack: str = "spring-boot"
    default_framework_version: str = "4.0"

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            api_host=os.getenv("API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("API_PORT", "8000")),
            default_tech_stack=os.getenv("DEFAULT_TECH_STACK", "spring-boot"),
            default_framework_version=os.getenv("DEFAULT_FRAMEWORK_VERSION", "4.0"),
        )


def get_config() -> AppConfig:
    return AppConfig.from_env()
