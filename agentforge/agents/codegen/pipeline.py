"""三阶段代码生成：骨架 → 实现 → 测试修复。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agentforge.agents.codegen.limits import (
    MAX_IMPLEMENT_CHARS,
    MAX_SKELETON_CHARS,
    MAX_TEST_FIX_CHARS,
    enforce_output_limit,
    strip_code_fences,
)
from agentforge.plugins.base import HandoffPacket
from agentforge.sandbox.manager import SandboxManager
from agentforge.utils.llm_util import CHAT_MODELS, LLMUtil


@dataclass
class StageResult:
    stage: str
    code: str
    summary: str
    truncated: bool = False
    metadata: dict[str, Any] | None = None


class DomainCodegenAdapter(Protocol):
    def system_prompt(self, framework_version: str) -> str:
        ...

    def build_user_prompt(
        self,
        handoff: HandoffPacket,
        upstream: dict,
        *,
        rag_context: str = "",
    ) -> str:
        ...

    def dry_run_code(self, handoff: HandoffPacket) -> str:
        ...

    @property
    def spec(self) -> Any:
        ...


class PhasedCodegenPipeline:
    """骨架设计 → 单文件实现 → 测试修复。"""

    def __init__(self, llm: LLMUtil | None = None) -> None:
        self.llm = llm or LLMUtil()

    def run(
        self,
        agent: DomainCodegenAdapter,
        handoff: HandoffPacket,
        *,
        framework_version: str,
        upstream: dict,
        rag_context: str = "",
        project_id: str = "",
        file_path: str = "",
        dry_run: bool = False,
    ) -> tuple[str, list[StageResult]]:
        if dry_run:
            code = agent.dry_run_code(handoff)
            stage = StageResult(stage="implement", code=code, summary="dry-run")
            return code, [stage]

        skeleton = self._skeleton(
            agent, handoff, framework_version=framework_version,
            upstream=upstream, rag_context=rag_context,
        )
        implemented = self._implement(
            agent, handoff, skeleton.code,
            framework_version=framework_version,
            upstream=upstream, rag_context=rag_context,
        )
        fixed = self._test_fix(
            agent, handoff, implemented.code,
            framework_version=framework_version,
            project_id=project_id,
            file_path=file_path,
        )
        stages = [skeleton, implemented, fixed]
        return fixed.code, stages

    def _skeleton(
        self,
        agent: DomainCodegenAdapter,
        handoff: HandoffPacket,
        *,
        framework_version: str,
        upstream: dict,
        rag_context: str,
    ) -> StageResult:
        base = agent.build_user_prompt(handoff, upstream, rag_context=rag_context)
        prompt = (
            f"{base}\n\n"
            "【阶段 1/3：骨架设计】\n"
            "仅输出类/接口骨架：package、import、类声明、字段、方法签名。\n"
            "方法体用 `// TODO` 或 `throw new UnsupportedOperationException()` 占位。\n"
            "不要实现完整业务逻辑，控制体量。"
        )
        system = agent.system_prompt(framework_version) + " 当前阶段只生成代码骨架。"
        raw = self.llm.chat(
            CHAT_MODELS[agent.spec.model_key],
            prompt,
            system=system,
            max_tokens=512,
        )
        code, truncated = enforce_output_limit(raw, max_chars=MAX_SKELETON_CHARS, label="skeleton")
        return StageResult(
            stage="skeleton",
            code=code,
            summary="骨架设计完成",
            truncated=truncated,
        )

    def _implement(
        self,
        agent: DomainCodegenAdapter,
        handoff: HandoffPacket,
        skeleton_code: str,
        *,
        framework_version: str,
        upstream: dict,
        rag_context: str,
    ) -> StageResult:
        base = agent.build_user_prompt(handoff, upstream, rag_context=rag_context)
        prompt = (
            f"{base}\n\n"
            "【阶段 2/3：单文件实现】\n"
            f"基于以下骨架补全完整可编译代码（单文件）：\n```\n{skeleton_code}\n```\n"
            "只输出一个文件的完整 Java 源代码，不要使用 Markdown，不要包含 ``` 代码块标记。"
        )
        system = agent.system_prompt(framework_version) + " 当前阶段输出单文件完整实现。"
        raw = self.llm.chat(
            CHAT_MODELS[agent.spec.model_key],
            prompt,
            system=system,
            max_tokens=1024,
        )
        code, truncated = enforce_output_limit(raw, max_chars=MAX_IMPLEMENT_CHARS, label="implement")
        return StageResult(
            stage="implement",
            code=code,
            summary="单文件实现完成",
            truncated=truncated,
        )

    def _test_fix(
        self,
        agent: DomainCodegenAdapter,
        handoff: HandoffPacket,
        code: str,
        *,
        framework_version: str,
        project_id: str,
        file_path: str,
    ) -> StageResult:
        issues = _collect_issues(code, project_id=project_id, file_path=file_path)
        if not issues:
            return StageResult(stage="test_fix", code=code, summary="静态检查通过，无需修复")

        prompt = (
            f"【阶段 3/3：测试修复】\n"
            f"目标文件: {file_path}\n"
            f"发现问题:\n- " + "\n- ".join(issues) + "\n\n"
            f"请修复以下代码并只输出修复后的完整单文件 Java 源代码（不要 Markdown，不要 ```）：\n{strip_code_fences(code)}"
        )
        system = agent.system_prompt(framework_version) + " 当前阶段修复编译/结构问题。"
        raw = self.llm.chat(
            CHAT_MODELS[agent.spec.model_key],
            prompt,
            system=system,
            max_tokens=768,
        )
        fixed, truncated = enforce_output_limit(raw, max_chars=MAX_TEST_FIX_CHARS, label="test_fix")
        return StageResult(
            stage="test_fix",
            code=fixed,
            summary="测试修复完成",
            truncated=truncated,
            metadata={"issues": issues},
        )


def _collect_issues(code: str, *, project_id: str, file_path: str) -> list[str]:
    issues: list[str] = []
    if not code.strip():
        issues.append("代码为空")
        return issues

    if file_path.endswith(".java"):
        if "```" in code:
            issues.append("包含 Markdown 代码块标记 ```")
        if code.count("{") != code.count("}"):
            issues.append("花括号不匹配")
        if "class " not in code and "interface " not in code:
            issues.append("缺少 class 或 interface 声明")
        if "package " not in code:
            issues.append("缺少 package 声明")

    if project_id and file_path.endswith(".java"):
        sandbox = SandboxManager()
        try:
            project_dir = sandbox.project_dir(project_id)
            pom = project_dir / "pom.xml"
            if pom.exists():
                sandbox.write_text(project_id, file_path, code)
                result = sandbox.run_command(project_id, "mvn -q -DskipTests compile", timeout=90)
                if int(result["exit_code"]) != 0:
                    stderr = str(result.get("stderr", ""))[:400]
                    issues.append(f"Maven compile 失败: {stderr or result.get('stdout', '')[:200]}")
        except Exception as exc:
            issues.append(f"编译检查跳过: {exc}")

    return issues
