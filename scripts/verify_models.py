"""验证 Qwen 模型连通性。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.utils.llm_util import LLMUtil, print_verify_report


def main() -> None:
    util = LLMUtil()
    results = util.verify_all()
    failed = print_verify_report(results)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
