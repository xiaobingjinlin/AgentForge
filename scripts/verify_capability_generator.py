"""验证 Phase 3：LLM 造层（fixture 模式，无需真实 LLM）。"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.agents.capability_router import CapabilityRouter
from agentforge.db.meta_store import MetaStore
from agentforge.services.project_service import ProjectService
from agentforge.templates.capability import CapabilityRegistry
from agentforge.templates.capability_generator import CapabilityGenerator

REDIS_SPEC = {
    "id": "redis",
    "name": "Redis Cache",
    "description": "Spring Data Redis 最小集成",
    "framework_version": "4.0",
    "requires": ["base"],
    "keywords": ["redis", "缓存", "cache"],
    "pom": {
        "dependencies": [
            {
                "groupId": "org.springframework.boot",
                "artifactId": "spring-boot-starter-data-redis",
            }
        ]
    },
    "application_yml": (
        "spring:\n  data:\n    redis:\n      host: localhost\n      port: 6379\n"
    ),
    "files": [],
    "verify": {"command": "mvn -q -DskipTests compile"},
}


def _redis_generated_path(registry: CapabilityRegistry) -> Path:
    return registry.capabilities_dir("4.0") / "_generated" / "redis"


def main() -> None:
    print("=" * 60)
    print("Phase 3 LLM 造层验证 (fixture)")
    print("=" * 60)

    registry = CapabilityRegistry()
    router = CapabilityRouter(registry=registry)
    meta = MetaStore()
    redis_path = _redis_generated_path(registry)

    try:
        meta.init_schema()

        # 清理历史 redis 造层
        if redis_path.exists():
            shutil.rmtree(redis_path)

        missing = router.infer_missing("给项目加上 redis 缓存", current_stack=["base"])
        if missing != ["redis"]:
            raise RuntimeError(f"应推断缺失 redis: {missing}")
        print("✓ 推断缺失能力: redis")

        registered, to_gen, rejected = router.collect_to_enable(
            "启用 redis", framework_version="4.0", current_stack=["base"]
        )
        if to_gen != ["redis"] or registered or rejected:
            raise RuntimeError(f"collect_to_enable 异常: {registered}, {to_gen}, {rejected}")
        print("✓ collect_to_enable: 需生成 redis")

        generator = CapabilityGenerator(registry=registry, use_rag=False)
        if generator.exists("redis"):
            raise RuntimeError("生成前 redis 不应存在")

        gen = generator.generate_and_promote(
            "redis",
            "给项目加上 redis 缓存",
            run_verify=False,
            spec=REDIS_SPEC,
        )
        if not redis_path.exists():
            raise RuntimeError("晋升目录不存在")
        if not registry.exists("redis"):
            raise RuntimeError("Registry 未识别 _generated/redis")
        print(f"✓ LLM 造层晋升: {gen.path} ({gen.files_written} files)")

        pom = (redis_path / "overlay").exists() or (redis_path / "manifest.json").exists()
        manifest = registry.load("redis")
        dep_ids = [d.artifact_id for d in manifest.pom_dependencies]
        if "spring-boot-starter-data-redis" not in dep_ids:
            raise RuntimeError("manifest 依赖错误")
        print("✓ manifest 依赖正确")

        project_id = meta.create_project("phase3-redis", framework_version="4.0")
        service = ProjectService(meta=meta, registry=registry)
        result = service.ensure_capability(
            project_id,
            "redis",
            "加 redis",
            run_verify=False,
            spec=None,
        )
        stack = result.get("template_stack", [])
        if "redis" not in stack:
            raise RuntimeError(f"项目栈未含 redis: {stack}")
        print(f"✓ 项目启用: {stack}")

        # 二次 ensure 应直接启用（不重复造层）
        again = service.ensure_capability(project_id, "redis", "加 redis", run_verify=False)
        if again.get("generated"):
            raise RuntimeError("已存在能力不应再次 generated")
        print("✓ 造层复用（不重复生成）")

        meta.delete_project(project_id)
        service.composer.sandbox.destroy(project_id)
        shutil.rmtree(redis_path, ignore_errors=True)
        print("✓ 测试数据已清理")

        print("=" * 60)
        print("Phase 3 造层验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        shutil.rmtree(redis_path, ignore_errors=True)
        raise SystemExit(1) from exc
    finally:
        meta.close()


if __name__ == "__main__":
    main()
