"""生成完成后的沙盒整体验证与可选修复。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from agentforge.core.constants import MAX_VERIFY_REPAIR_ROUNDS
from agentforge.core.jdk import probe_java_version
from agentforge.utils.code_text import strip_code_fences
from agentforge.sandbox.manager import SandboxManager
from agentforge.utils.java_fix import (
    apply_deterministic_java_fixes,
    parse_maven_errors,
    paths_refer_to_same_java,
)
from agentforge.utils.maven_output import display_maven_message, sanitize_maven_output
from agentforge.utils.pom_deps import patch_pom_for_compile_errors
from agentforge.utils.llm_util import CHAT_MODELS, LLMUtil

if TYPE_CHECKING:
    from agentforge.agents.handoff import DomainResult
    from agentforge.rag.codegen_error_memory import CodegenErrorMemory

_JAVA_CLASS_RE = re.compile(r"\b(?:class|interface|enum)\s+([A-Za-z_][\w$]*)")
_INVALID_CLASS_RE = re.compile(r"\b(?:class|interface|enum)\s+([\u4e00-\u9fff\w$]+)")
_MAX_STUCK_ROUNDS = 2


@dataclass
class FileIssue:
    path: str
    issues: list[str] = field(default_factory=list)


@dataclass
class ProjectVerifyResult:
    ok: bool
    static_issues: list[FileIssue] = field(default_factory=list)
    compile_exit_code: int | None = None
    compile_message: str = ""
    compile_skipped: bool = False
    repaired_files: list[str] = field(default_factory=list)
    repair_rounds: int = 0
    stuck: bool = False
    stopped_reason: str = ""

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.ok:
            if self.compile_skipped:
                lines.append("整体验证：静态检查通过（环境无 mvn，已跳过编译）")
            else:
                lines.append("整体验证：通过（静态检查 + Maven 编译）")
            if self.repaired_files:
                lines.append(
                    f"已自动修复（{self.repair_rounds} 轮）："
                    f"{', '.join(_unique_paths(self.repaired_files))}"
                )
            return lines

        lines.append("整体验证：未完全通过")
        if self.stuck:
            lines.append(
                f"修复停滞：连续 {_MAX_STUCK_ROUNDS} 轮未解决同一问题，已停止自动修复"
            )
            if self.stopped_reason:
                lines.append(f"原因：{self.stopped_reason[:200]}")
        for item in self.static_issues:
            lines.append(f"- `{item.path}`：{'; '.join(item.issues)}")
        if self.compile_message:
            shown = display_maven_message(self.compile_message, max_chars=240)
            if shown:
                lines.append(f"- Maven：`{shown}`")
        if self.repaired_files:
            lines.append(
                f"已尝试修复（{self.repair_rounds} 轮）："
                f"{', '.join(_unique_paths(self.repaired_files))}"
            )
        return lines


def _unique_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def static_java_issues(code: str, file_path: str) -> list[str]:
    issues: list[str] = []
    cleaned = strip_code_fences(code)
    if not cleaned.strip():
        issues.append("文件为空")
        return issues

    if "```" in cleaned:
        issues.append("含 Markdown 代码块标记 ```")

    if file_path.endswith(".java"):
        if "package " not in cleaned:
            issues.append("缺少 package 声明")
        if cleaned.count("{") != cleaned.count("}"):
            issues.append("花括号不匹配")
        if not _JAVA_CLASS_RE.search(cleaned):
            bad = _INVALID_CLASS_RE.search(cleaned)
            if bad:
                issues.append(f"类名非法: {bad.group(1)}")
            else:
                issues.append("缺少 class/interface 声明")

        filename = file_path.rsplit("/", 1)[-1].removesuffix(".java")
        match = _JAVA_CLASS_RE.search(cleaned)
        if match and match.group(1) != filename:
            issues.append(f"类名 {match.group(1)} 与文件名 {filename} 不一致")

    return issues


def verify_fingerprint(verify: ProjectVerifyResult) -> str:
    parts: list[str] = []
    for item in sorted(verify.static_issues, key=lambda x: x.path):
        parts.append(f"{item.path}|{'|'.join(sorted(item.issues))}")
    if verify.compile_exit_code not in (None, 0):
        parts.append(
            f"compile:{verify.compile_exit_code}:"
            f"{sanitize_maven_output(verify.compile_message)[:500]}"
        )
    return "||".join(parts)


class ProjectVerifier:
    """各域生成完成后的项目级校验。"""

    COMPILE_COMMAND = "mvn -q -DskipTests compile"

    def __init__(self, sandbox: SandboxManager | None = None) -> None:
        self.sandbox = sandbox or SandboxManager()

    def verify(self, project_id: str, results: list[DomainResult]) -> ProjectVerifyResult:
        static_issues: list[FileIssue] = []

        for result in results:
            if not result.file_path.endswith(".java"):
                continue
            try:
                on_disk = self.sandbox.read_text(project_id, result.file_path)
            except Exception:
                on_disk = result.code
            code = strip_code_fences(on_disk or result.code)
            issues = static_java_issues(code, result.file_path)
            if issues:
                static_issues.append(FileIssue(result.file_path, issues))

        compile_exit: int | None = None
        compile_message = ""

        if static_issues:
            return ProjectVerifyResult(
                ok=False,
                static_issues=static_issues,
                compile_skipped=True,
            )

        pom = self.sandbox.project_dir(project_id) / "pom.xml"
        if not pom.exists():
            return ProjectVerifyResult(
                ok=False,
                static_issues=[FileIssue("pom.xml", ["沙盒缺少 pom.xml"])],
                compile_skipped=True,
            )

        try:
            run = self.sandbox.run_command(
                project_id,
                self.COMPILE_COMMAND,
                timeout=180,
            )
            compile_exit = int(run.get("exit_code", 1))
            stderr = str(run.get("stderr", "")).strip()
            stdout = str(run.get("stdout", "")).strip()
            raw_message = stderr or stdout or f"exit_code={compile_exit}"
            compile_message = sanitize_maven_output(raw_message) or raw_message
            if compile_exit != 0 and self._mvn_unavailable(raw_message):
                return ProjectVerifyResult(
                    ok=True,
                    compile_skipped=True,
                    compile_message="mvn 不可用，仅完成静态检查",
                )
            return ProjectVerifyResult(
                ok=compile_exit == 0,
                compile_exit_code=compile_exit,
                compile_message=compile_message if compile_exit != 0 else "compile ok",
            )
        except Exception as exc:
            return ProjectVerifyResult(
                ok=False,
                compile_skipped=True,
                compile_message=str(exc),
            )

    def verify_and_repair(
        self,
        project_id: str,
        results: list[DomainResult],
        *,
        llm: LLMUtil | None = None,
        user_message: str = "",
        max_repair_rounds: int = MAX_VERIFY_REPAIR_ROUNDS,
        error_memory: CodegenErrorMemory | None = None,
    ) -> tuple[ProjectVerifyResult, list[DomainResult]]:
        from agentforge.rag.codegen_error_memory import CodegenErrorMemory as _Memory

        memory = error_memory or _Memory(llm=llm)
        current = list(results)
        repaired: list[str] = []
        verify = self.verify(project_id, current)
        last_fingerprint = verify_fingerprint(verify) if not verify.ok else ""
        stuck_count = 0

        if not verify.ok:
            memory.record_verify_failure(
                project_id=project_id,
                round_idx=0,
                verify=verify,
                user_message=user_message,
            )
            verify = self._retry_after_pom_patch(project_id, current, verify, repaired)

        for round_idx in range(max_repair_rounds):
            if verify.ok or not llm:
                break

            verify = self._retry_after_pom_patch(project_id, current, verify, repaired)
            if verify.ok:
                break

            fingerprint = verify_fingerprint(verify)
            if fingerprint and fingerprint == last_fingerprint:
                stuck_count += 1
            else:
                stuck_count = 0
            last_fingerprint = fingerprint

            if stuck_count >= _MAX_STUCK_ROUNDS:
                verify.stuck = True
                verify.stopped_reason = fingerprint[:300] or "验证结果未变化"
                verify.repair_rounds = round_idx
                logger.bind(project_id=project_id).warning(
                    "修复停滞，停止自动修复: {}",
                    verify.stopped_reason,
                )
                break

            logger.bind(project_id=project_id).info(
                "整体验证未通过，开始修复 round={}/{} static={} compile={}",
                round_idx + 1,
                max_repair_rounds,
                len(verify.static_issues),
                verify.compile_exit_code,
            )
            current, fixed_paths, improved = self._repair_once(
                project_id,
                current,
                verify,
                llm=llm,
                user_message=user_message,
                error_memory=memory,
                repair_round=round_idx + 1,
            )
            if fixed_paths:
                repaired.extend(fixed_paths)

            if not improved:
                verify.stuck = True
                verify.stopped_reason = "本轮修复未产生有效变更"
                verify.repair_rounds = round_idx + 1
                verify.repaired_files = repaired
                logger.bind(project_id=project_id).warning(
                    "修复无进展，停止自动修复"
                )
                break

            verify = self.verify(project_id, current)
            verify.repaired_files = repaired
            verify.repair_rounds = round_idx + 1

            if not verify.ok:
                memory.record_verify_failure(
                    project_id=project_id,
                    round_idx=round_idx + 1,
                    verify=verify,
                    user_message=user_message,
                )

        return verify, current

    def _retry_after_pom_patch(
        self,
        project_id: str,
        results: list[DomainResult],
        verify: ProjectVerifyResult,
        repaired: list[str],
    ) -> ProjectVerifyResult:
        if verify.ok or verify.compile_exit_code in (None, 0):
            return verify

        added = patch_pom_for_compile_errors(
            self.sandbox.project_dir(project_id),
            verify.compile_message,
        )
        if not added:
            return verify

        logger.bind(project_id=project_id).info("已自动补充 pom 依赖: {}", added)
        repaired.append("pom.xml")
        verify = self.verify(project_id, results)
        verify.repaired_files = list(repaired)
        return verify

    def _target_issue_paths(
        self,
        verify: ProjectVerifyResult,
        results: list[DomainResult],
    ) -> dict[str, list[str]]:
        path_hints: dict[str, list[str]] = {}

        for item in verify.static_issues:
            path_hints[item.path] = list(item.issues)

        if verify.compile_exit_code not in (None, 0) and verify.compile_message:
            maven_errors = parse_maven_errors(verify.compile_message)
            if maven_errors:
                for result in results:
                    if not result.file_path.endswith(".java"):
                        continue
                    for maven_path, errors in maven_errors.items():
                        if paths_refer_to_same_java(result.file_path, maven_path):
                            path_hints.setdefault(result.file_path, []).extend(errors)
            else:
                fallback_paths = _extract_java_paths_from_compile(verify.compile_message)
                if fallback_paths:
                    for result in results:
                        if not result.file_path.endswith(".java"):
                            continue
                        for raw_path in fallback_paths:
                            if paths_refer_to_same_java(result.file_path, raw_path):
                                path_hints.setdefault(result.file_path, []).append(
                                    "Maven 编译失败（见整体编译输出）"
                                )

        return path_hints

    def _repair_once(
        self,
        project_id: str,
        results: list[DomainResult],
        verify: ProjectVerifyResult,
        *,
        llm: LLMUtil,
        user_message: str,
        error_memory: CodegenErrorMemory | None = None,
        repair_round: int = 1,
    ) -> tuple[list[DomainResult], list[str], bool]:
        from agentforge.agents.handoff import DomainResult
        from agentforge.rag.codegen_error_memory import CodegenErrorMemory as _Memory

        memory = error_memory or _Memory(llm=llm)
        path_hints = self._target_issue_paths(verify, results)
        if not path_hints:
            return results, [], False

        updated: list[DomainResult] = []
        fixed_paths: list[str] = []
        improved = False
        compile_hint = (
            sanitize_maven_output(verify.compile_message)[:1200]
            if verify.compile_message
            else ""
        )
        result_by_path = {r.file_path: r for r in results}

        for result in results:
            if result.file_path not in path_hints or not result.file_path.endswith(".java"):
                updated.append(result)
                continue

            try:
                code = self.sandbox.read_text(project_id, result.file_path)
            except Exception:
                code = result.code

            original = strip_code_fences(code)
            before_issues = static_java_issues(original, result.file_path)
            file_hints = path_hints.get(result.file_path, [])

            fixed_code = apply_deterministic_java_fixes(original, result.file_path)
            after_det_issues = static_java_issues(fixed_code, result.file_path)

            if fixed_code != original and len(after_det_issues) < len(before_issues):
                improved = True
                original = fixed_code
                before_issues = after_det_issues

            if not after_det_issues and verify.compile_exit_code in (None, 0):
                self.sandbox.write_text(project_id, result.file_path, fixed_code)
                fixed_paths.append(result.file_path)
                improved = True
                updated.append(self._updated_result(result, fixed_code))
                continue

            if after_det_issues and len(after_det_issues) < len(before_issues):
                self.sandbox.write_text(project_id, result.file_path, fixed_code)
                fixed_paths.append(result.file_path)
                improved = True
                updated.append(self._updated_result(result, fixed_code))
                continue

            if not after_det_issues and verify.compile_exit_code not in (None, 0):
                self.sandbox.write_text(project_id, result.file_path, fixed_code)
                original = fixed_code

            related_snippets = self._related_file_snippets(
                result.file_path,
                results,
                project_id,
            )
            llm_fixed = self._llm_repair_file(
                result=result,
                code=original,
                file_hints=file_hints,
                compile_hint=compile_hint,
                user_message=user_message,
                repair_round=repair_round,
                llm=llm,
                memory=memory,
                related_snippets=related_snippets,
            )
            if not llm_fixed:
                updated.append(result)
                continue

            llm_issues = static_java_issues(llm_fixed, result.file_path)
            if _normalize_code(llm_fixed) == _normalize_code(original):
                logger.bind(project_id=project_id).warning(
                    "修复未改变代码: {}",
                    result.file_path,
                )
                updated.append(result)
                continue

            if llm_issues and len(llm_issues) >= len(before_issues):
                logger.bind(project_id=project_id).warning(
                    "修复后问题未减少 {}: {}",
                    llm_issues,
                    result.file_path,
                )
                updated.append(result)
                continue

            self.sandbox.write_text(project_id, result.file_path, llm_fixed)
            fixed_paths.append(result.file_path)
            improved = True
            updated.append(self._updated_result(result, llm_fixed))

        return updated, fixed_paths, improved

    def _llm_repair_file(
        self,
        *,
        result: DomainResult,
        code: str,
        file_hints: list[str],
        compile_hint: str,
        user_message: str,
        repair_round: int,
        llm: LLMUtil,
        memory: CodegenErrorMemory,
        related_snippets: str,
    ) -> str | None:
        static_hint = "; ".join(file_hints)
        lesson_query = (
            f"{user_message[:200]} {result.file_path} {result.domain} "
            f"{static_hint} {compile_hint[:200]}"
        )
        error_lessons = memory.retrieve_for_codegen(
            lesson_query,
            codegen_domain=result.domain,
        )
        lessons_block = (
            f"\n历史错误教训（勿重复）:\n{error_lessons}\n"
            if error_lessons
            else ""
        )
        related_block = (
            f"\n相关文件（仅供 import/类型参考）:\n{related_snippets}\n"
            if related_snippets
            else ""
        )
        prompt = (
            f"用户需求: {user_message[:300]}\n"
            f"目标文件: {result.file_path}\n"
            f"修复轮次: {repair_round}\n"
            f"必须修复的问题:\n- " + "\n- ".join(file_hints or ["见编译输出"]) + "\n"
            f"编译输出:\n{compile_hint or '无'}\n"
            f"{lessons_block}"
            f"{related_block}\n"
            "只输出修复后的完整单文件 Java 源码。\n"
            "硬性要求：\n"
            "1. 禁止 Markdown 与 ```\n"
            "2. 类名必须与文件名一致，英文 PascalCase\n"
            "3. 必须包含正确 package 声明\n"
            "4. 必须能通过 mvn compile\n\n"
            f"当前代码:\n{code}"
        )
        try:
            raw = llm.chat(
                CHAT_MODELS["coder"],
                prompt,
                system=(
                    "你是 Java 代码修复专家。"
                    "只输出一个 .java 文件的完整源码，不要解释。"
                    "若无法确定修复方案，仍输出最接近可编译的版本。"
                ),
                max_tokens=2048,
            )
            fixed_code = strip_code_fences(raw)
            return apply_deterministic_java_fixes(fixed_code, result.file_path) or None
        except Exception as exc:
            logger.warning("LLM 修复 {} 失败: {}", result.file_path, exc)
            return None

    def _related_file_snippets(
        self,
        target_path: str,
        results: list[DomainResult],
        project_id: str,
        *,
        max_each: int = 500,
    ) -> str:
        blocks: list[str] = []
        for item in results:
            if item.file_path == target_path or not item.file_path.endswith(".java"):
                continue
            try:
                snippet = self.sandbox.read_text(project_id, item.file_path)
            except Exception:
                snippet = item.code
            snippet = strip_code_fences(snippet)[:max_each]
            blocks.append(f"// {item.file_path}\n{snippet}")
        return "\n\n".join(blocks[:4])

    @staticmethod
    def _updated_result(result: DomainResult, code: str) -> DomainResult:
        from agentforge.agents.handoff import DomainResult as DR

        return DR(
            domain=result.domain,
            agent=result.agent,
            summary=f"{result.summary}（已整体验证修复）",
            code=code,
            file_path=result.file_path,
            stages=result.stages,
        )

    @staticmethod
    def _mvn_unavailable(message: str) -> bool:
        lowered = message.lower()
        return "command not found" in lowered or "not found" in lowered and "mvn" in lowered


def _normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", strip_code_fences(code))


_JAVA_PATH_IN_LINE = re.compile(r"([\w./\\-]+src/main/java/[\w./\\-]+\.java)")


def _extract_java_paths_from_compile(message: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in message.splitlines():
        if "[ERROR]" not in line and "error:" not in line.lower():
            continue
        for match in _JAVA_PATH_IN_LINE.finditer(line.replace("\\", "/")):
            path = match.group(1)
            if "src/main/java/" in path:
                rel = "src/main/java/" + path.split("src/main/java/", 1)[1]
            else:
                rel = path
            if rel not in seen:
                seen.add(rel)
                found.append(rel)
    return found
