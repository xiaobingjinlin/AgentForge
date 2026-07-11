"""验证能力层模板：base + springdoc 组合。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.db.meta_store import MetaStore
from agentforge.services.project_service import ProjectService
from agentforge.templates.capability import CapabilityRegistry, resolve_stack
from agentforge.templates.composer import TemplateComposer


def main() -> None:
    print("=" * 60)
    print("能力层模板验证 (springdoc)")
    print("=" * 60)

    meta = MetaStore()
    registry = CapabilityRegistry()
    composer = TemplateComposer(registry=registry)
    service = ProjectService(meta=meta, composer=composer, registry=registry)

    try:
        meta.init_schema()
        caps = registry.list_ids("4.0")
        if "springdoc" not in caps:
            raise RuntimeError(f"未找到 springdoc 能力层: {caps}")
        print(f"✓ 已注册能力层: {', '.join(caps)}")

        manifest = registry.load("springdoc", "4.0")
        if not manifest.overlay_dir.exists():
            raise RuntimeError("springdoc overlay 目录缺失")
        print(f"✓ manifest: {manifest.name}")

        stack = resolve_stack(["base", "springdoc"], framework_version="4.0", registry=registry)
        if stack != ["base", "springdoc"]:
            raise RuntimeError(f"栈解析错误: {stack}")
        print(f"✓ 能力栈: {' + '.join(stack)}")

        project_id = meta.create_project("cap-test", framework_version="4.0")
        target = composer.compose_to_sandbox(project_id, stack, framework_version="4.0", clean=True)

        pom = (target / "pom.xml").read_text(encoding="utf-8")
        if "springdoc-openapi-starter-webmvc-ui" not in pom:
            raise RuntimeError("pom 未合并 springdoc 依赖")

        config = target / "src/main/java/com/example/demo/config/OpenApiConfig.java"
        if not config.exists():
            raise RuntimeError("OpenApiConfig.java 未复制")

        app_yml = (target / "src/main/resources/application.yml").read_text(encoding="utf-8")
        if "swagger-ui" not in app_yml:
            raise RuntimeError("application.yml 未合并 springdoc 配置")
        print("✓ base + springdoc 组合成功")

        # 项目 metadata 仅 base，首次启用应写入栈
        project_id2 = meta.create_project("cap-enable-test", framework_version="4.0")
        first = service.enable_capability(project_id2, "springdoc")
        if first.get("already_enabled"):
            raise RuntimeError("首次启用不应为 already_enabled")
        if first["template_stack"] != ["base", "springdoc"]:
            raise RuntimeError(f"首次启用栈错误: {first['template_stack']}")
        print(f"✓ 首次启用: {first['template_stack']}")

        second = service.enable_capability(project_id2, "springdoc")
        if not second.get("already_enabled"):
            raise RuntimeError("重复启用应返回 already_enabled")
        print("✓ 幂等启用检测通过")

        meta.delete_project(project_id)
        meta.delete_project(project_id2)
        composer.sandbox.destroy(project_id)
        composer.sandbox.destroy(project_id2)
        print("✓ 测试数据已清理")

        print("=" * 60)
        print("能力层模板验证通过")
        print("=" * 60)
    except Exception as exc:
        print(f"✗ 验证失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        meta.close()


if __name__ == "__main__":
    main()
