"""验证项目上下文持久化（生成历史 + 文件结构）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.graph import run_agent_pipeline
from agentforge.db.meta_store import MetaStore
from agentforge.plugins import init_plugins
from agentforge.sandbox.manager import SandboxManager


def main() -> None:
    print("=" * 60)
    print("项目上下文持久化验证")
    print("=" * 60)

    meta = MetaStore()
    try:
        meta.init_schema()
        init_plugins()

        project_id = meta.create_project(
            "ctx-test",
            framework_version="4.0",
            root_path=str(Path("sandbox").resolve()),
        )
        session_id = meta.create_session(project_id, "持久化测试")

        state = run_agent_pipeline(
            session_id=session_id,
            project_id=project_id,
            user_message="生成 Order 模块 CRUD",
            dry_run=True,
        )
        results = state.get("domain_results", [])
        for result in results:
            meta.add_generation_record(
                session_id=session_id,
                project_id=project_id,
                stage="domain",
                file_path=result.file_path,
                content=result.code,
                metadata={"domain": result.domain},
            )
            if result.stages:
                for stage in result.stages:
                    meta.add_generation_record(
                        session_id=session_id,
                        project_id=project_id,
                        stage=stage.get("stage", "unknown"),
                        file_path=result.file_path,
                        metadata=stage,
                    )

        sandbox = SandboxManager()
        sandbox.create(project_id)
        for result in results:
            sandbox.write_text(project_id, result.file_path, result.code)
        files = sandbox.list_files(project_id)
        meta.save_project_structure(project_id, files)

        project = meta.get_project(project_id)
        if not project or not project.get("metadata", {}).get("file_tree"):
            raise RuntimeError("项目结构未持久化")

        records = meta.list_generation_records(project_id=project_id, session_id=session_id)
        if len(records) < len(results):
            raise RuntimeError(f"生成历史不足: {len(records)}")

        messages = meta.list_messages(session_id)
        print(f"✓ 项目: {project_id[:8]}...")
        print(f"✓ 文件结构: {len(project['metadata']['file_tree'])} 个文件")
        print(f"✓ 生成记录: {len(records)} 条")
        print(f"✓ 会话消息: {len(messages)} 条")

        meta.delete_project(project_id)
        sandbox.destroy(project_id)
        print("✓ 测试数据已清理")

        print("=" * 60)
        print("上下文持久化验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        meta.close()


if __name__ == "__main__":
    main()
