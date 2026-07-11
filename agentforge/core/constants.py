"""全局常量（无业务模块依赖）。"""

from __future__ import annotations

import os

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "2048"))
