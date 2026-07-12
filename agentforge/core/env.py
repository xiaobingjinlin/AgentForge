"""项目根目录 .env 加载（存在时优先于系统环境变量）。"""

from __future__ import annotations

from pathlib import Path

_LOADED = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_project_env(*, force: bool = False) -> bool:
    """若项目根目录存在 `.env`，加载并覆盖同名系统环境变量。"""
    global _LOADED
    if _LOADED and not force:
        return False

    env_path = _project_root() / ".env"
    if not env_path.is_file():
        _LOADED = True
        return False

    from dotenv import load_dotenv

    load_dotenv(env_path, override=True)
    _LOADED = True
    return True
