"""验证 LangChain 沙盒工具。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.sandbox import SandboxManager, build_sandbox_tools

PROJECT_ID = "verify-sandbox"


def main() -> None:
    print("=" * 60)
    print("AgentForge 沙盒验证")
    print("=" * 60)

    manager = SandboxManager()
    try:
        manager.create(PROJECT_ID, clean=True)
        print(f"✓ 沙盒创建: {manager.project_dir(PROJECT_ID)}")

        tools = build_sandbox_tools(manager, PROJECT_ID)
        tool_map = {t.name: t for t in tools}
        print(f"✓ LangChain 工具: {', '.join(tool_map)}")

        write_out = tool_map["sandbox_write_file"].invoke(
            {"relative_path": "hello.txt", "content": "sandbox ok"}
        )
        print(f"✓ 写入文件: {write_out}")

        read_out = tool_map["sandbox_read_file"].invoke({"relative_path": "hello.txt"})
        if read_out != "sandbox ok":
            raise RuntimeError(f"读取内容不一致: {read_out!r}")
        print("✓ 读取文件成功")

        list_out = tool_map["sandbox_list_files"].invoke({"relative_path": "."})
        print(f"✓ 列出文件:\n{list_out}")

        run_out = tool_map["sandbox_run_command"].invoke({"command": "ls"})
        print(f"✓ 执行命令:\n{run_out}")

        try:
            tool_map["sandbox_run_command"].invoke({"command": "rm -rf /"})
            raise RuntimeError("危险命令应被拒绝")
        except Exception:
            print("✓ 命令白名单拦截生效")

        print("=" * 60)
        print("全部检查通过，沙盒可用")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        manager.destroy(PROJECT_ID)
        print("✓ 测试沙盒已清理")


if __name__ == "__main__":
    main()
