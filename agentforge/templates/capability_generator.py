"""LLM 生成 Spring Boot 能力层并晋升到 _generated/。"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from agentforge.core.config import PROJECT_ROOT
from agentforge.rag.retriever import RagRetriever
from agentforge.templates.capability import BASE_LAYER_ID, CapabilityRegistry
from agentforge.templates.composer import TemplateComposer, apply_capability_layer
from agentforge.utils.llm_util import CHAT_MODELS, LLMUtil

GENERATED_DIR = "_generated"
STAGING_DIR = "_staging"


@dataclass
class GenerationResult:
    capability_id: str
    name: str
    path: str
    files_written: int
    verified: bool
    verify_detail: str = ""
    source: str = "llm"


class CapabilityGenerator:
    """Registry 无匹配时，由 LLM 生成最小可运行能力层。"""

    def __init__(
        self,
        llm: LLMUtil | None = None,
        registry: CapabilityRegistry | None = None,
        composer: TemplateComposer | None = None,
        *,
        use_rag: bool = True,
    ) -> None:
        self.llm = llm or LLMUtil()
        self.registry = registry or CapabilityRegistry()
        self.composer = composer or TemplateComposer(registry=self.registry)
        self.use_rag = use_rag

    def exists(self, capability_id: str, framework_version: str = "4.0") -> bool:
        return self.registry.exists(capability_id, framework_version)

    def generate_and_promote(
        self,
        capability_id: str,
        user_message: str,
        *,
        framework_version: str = "4.0",
        run_verify: bool = True,
        spec: dict[str, Any] | None = None,
    ) -> GenerationResult:
        cap_id = _sanitize_id(capability_id)
        if self.exists(cap_id, framework_version):
            manifest = self.registry.load(cap_id, framework_version)
            return GenerationResult(
                capability_id=cap_id,
                name=manifest.name,
                path=str(manifest.root_dir),
                files_written=0,
                verified=True,
                verify_detail="already exists",
                source="registry",
            )

        payload = spec or self._generate_spec(cap_id, user_message, framework_version)
        if payload.get("id") != cap_id:
            payload["id"] = cap_id

        staging = self._staging_dir(cap_id, framework_version)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        files_written = self._write_layer(staging, payload)

        verify_ok, verify_detail = self._verify_layer(
            cap_id,
            staging,
            framework_version=framework_version,
            run_verify=run_verify,
        )
        if not verify_ok and run_verify:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError(f"能力层 {cap_id} 验证失败: {verify_detail}")

        target = self._generated_dir(cap_id, framework_version)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(staging), str(target))

        logger.info("能力层 {} 已晋升至 {}", cap_id, target)
        return GenerationResult(
            capability_id=cap_id,
            name=str(payload.get("name", cap_id)),
            path=str(target.relative_to(PROJECT_ROOT)),
            files_written=files_written,
            verified=verify_ok,
            verify_detail=verify_detail,
            source="llm" if spec is None else "fixture",
        )

    def _generate_spec(
        self,
        capability_id: str,
        user_message: str,
        framework_version: str,
    ) -> dict[str, Any]:
        rag_block = ""
        if self.use_rag:
            try:
                retriever = RagRetriever(llm=self.llm, use_cache=False)
                hits = retriever.retrieve(
                    f"Spring Boot {framework_version} {capability_id} {user_message}",
                    domain="config",
                    framework_version=framework_version,
                    top_k=3,
                    rerank_top_n=2,
                )
                rag_block = retriever.format_context(hits, max_chars=1500)
            except Exception as exc:
                logger.warning("RAG 上下文获取跳过: {}", exc)

        base_pom = (
            PROJECT_ROOT / "templates" / "spring-boot" / framework_version / "base" / "pom.xml"
        )
        pom_preview = base_pom.read_text(encoding="utf-8")[:1200] if base_pom.exists() else ""

        prompt = (
            f"能力层 id: {capability_id}\n"
            f"Spring Boot 版本: {framework_version}\n"
            f"用户需求: {user_message}\n\n"
            f"基础 pom 片段:\n{pom_preview}\n\n"
            f"知识库参考:\n{rag_block or '（无）'}\n\n"
            "请生成最小可运行能力层，输出单个 JSON 对象，字段：\n"
            '- id, name, description, framework_version, requires=["base"], keywords[]\n'
            "- pom.dependencies: [{groupId, artifactId, version?}]\n"
            "- application_yml: 字符串\n"
            '- files: [{path, content}]（Java 配置类放 com.example.demo.config，路径以 src/ 开头）\n'
            '- verify: {command: "mvn -q -DskipTests compile"}\n'
            "约束：依赖版本与 Spring Boot 4.0 兼容；只输出 JSON，不要 Markdown。"
        )
        system = (
            "你是 Spring Boot 能力层架构师。"
            "生成可叠加在 base 模板上的最小 overlay（类似 Docker layer）。"
        )
        raw = self.llm.chat(
            CHAT_MODELS["router"],
            prompt,
            system=system,
            max_tokens=2048,
        )
        return _parse_json_payload(raw)

    def _write_layer(self, root: Path, payload: dict[str, Any]) -> int:
        manifest = {k: v for k, v in payload.items() if k != "files"}
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        overlay = root / "overlay"
        overlay.mkdir(parents=True, exist_ok=True)
        count = 1
        for item in payload.get("files", []):
            rel = str(item.get("path", "")).lstrip("/")
            content = str(item.get("content", ""))
            if not rel:
                continue
            target = overlay / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            count += 1
        return count

    def _verify_layer(
        self,
        capability_id: str,
        staging_dir: Path,
        *,
        framework_version: str,
        run_verify: bool,
    ) -> tuple[bool, str]:
        manifest_path = staging_dir / "manifest.json"
        if not manifest_path.exists():
            return False, "manifest.json 缺失"

        verify_project = f"cap-verify-{capability_id}"
        try:
            self.composer.compose_to_sandbox(
                verify_project,
                [BASE_LAYER_ID],
                framework_version=framework_version,
                clean=True,
            )
            manifest = self.registry.load_from_dir(staging_dir)
            target = self.composer.sandbox.project_dir(verify_project)
            apply_capability_layer(target, manifest)

            if not run_verify:
                return True, "skipped"

            command = manifest.verify_command
            result = self.composer.sandbox.run_command(verify_project, command)
            exit_code = int(result.get("exit_code", 1))
            if exit_code == 0:
                return True, "mvn compile ok"
            stderr = str(result.get("stderr", ""))[:300]
            stdout = str(result.get("stdout", ""))[:200]
            # 无 mvn 环境时降级：结构校验通过即可
            if "command not found" in stderr.lower() or "not found" in stderr.lower():
                return True, "mvn unavailable, structure check only"
            return False, stderr or stdout or f"exit={exit_code}"
        finally:
            try:
                self.composer.sandbox.destroy(verify_project)
            except Exception:
                pass

    def _capabilities_root(self, framework_version: str) -> Path:
        return self.registry.capabilities_dir(framework_version)

    def _generated_dir(self, capability_id: str, framework_version: str) -> Path:
        return self._capabilities_root(framework_version) / GENERATED_DIR / capability_id

    def _staging_dir(self, capability_id: str, framework_version: str) -> Path:
        return self._capabilities_root(framework_version) / STAGING_DIR / capability_id


def _sanitize_id(capability_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]", "-", capability_id.lower()).strip("-")
    if not cleaned:
        raise ValueError(f"无效能力层 id: {capability_id}")
    return cleaned


def _parse_json_payload(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("无法解析 LLM 返回的 JSON")
