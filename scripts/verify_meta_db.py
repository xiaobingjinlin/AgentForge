"""验证 AgentForge 关系型数据库是否可用。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.db.meta_store import MetaStore


def main() -> None:
    print("=" * 60)
    print("AgentForge 关系型库连通性验证")
    print("=" * 60)

    store = MetaStore()
    project_id = None
    try:
        info = store.ping()
        print(f"✓ 数据库连接成功: {info['database']}")
        print(f"  └─ {info['pg_version']}")

        store.init_schema()
        print("✓ 关系表结构初始化成功")

        project_id = store.create_project(
            "verify-demo",
            framework_version="3.2",
            root_path="/tmp/demo",
        )
        session_id = store.create_session(project_id, title="验证会话")
        msg_id = store.add_message(session_id, "user", "生成 UserController")
        print(f"✓ 数据写入成功: project={project_id[:8]}..., message_id={msg_id}")

        count = store.count_projects()
        print(f"✓ 当前项目数: {count}")

        print("=" * 60)
        print("全部检查通过，关系型库可用")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        if project_id:
            store.delete_project(project_id)
            print(f"✓ 测试数据清理完成")
        store.close()


if __name__ == "__main__":
    main()
