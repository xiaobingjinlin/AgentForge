"""验证 FastAPI 服务与连接池。"""

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_URL = "http://127.0.0.1:8000/api"


def main() -> None:
    print("=" * 60)
    print("AgentForge API 连通性验证")
    print("=" * 60)

    try:
        with httpx.Client(timeout=30.0) as client:
            health = client.get(f"{BASE_URL}/health")
            health.raise_for_status()
            print(f"✓ 健康检查: {health.json()}")

            project = client.post(
                f"{BASE_URL}/projects",
                json={"name": "verify-api", "tech_stack": "spring-boot"},
            )
            project.raise_for_status()
            project_id = project.json()["id"]
            print(f"✓ 创建项目: {project_id[:8]}...")

            session = client.post(
                f"{BASE_URL}/projects/{project_id}/sessions",
                json={"title": "verify"},
            )
            session.raise_for_status()
            session_id = session.json()["id"]
            print(f"✓ 创建会话: {session_id[:8]}...")

            with client.stream(
                "POST",
                f"{BASE_URL}/sessions/{session_id}/chat",
                json={"message": "回复 OK"},
            ) as response:
                response.raise_for_status()
                body = "".join(response.iter_text())
                if "event:" not in body:
                    raise RuntimeError("SSE 无输出")
                print(f"✓ SSE 流式响应: 收到 {body.count('event:')} 个事件")

            messages = client.get(f"{BASE_URL}/sessions/{session_id}/messages")
            messages.raise_for_status()
            data = messages.json()
            if len(data) < 2:
                raise RuntimeError("消息未持久化")
            print(f"✓ 消息持久化: {len(data)} 条")

        print("=" * 60)
        print("全部检查通过，API 可用")
        print("=" * 60)
    except httpx.ConnectError:
        print("✗ 无法连接 API，请先启动: bash scripts/run_api.sh")
        raise SystemExit(1)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
