"""领域 SubGraph：三阶段代码生成 + RAG 上下文。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from loguru import logger

from agentforge.agents.codegen.pipeline import PhasedCodegenPipeline
from agentforge.agents.codegen.limits import strip_code_fences
from agentforge.agents.domains.spring_boot import get_domain_agent
from agentforge.agents.handoff import DomainResult
from agentforge.plugins.base import HandoffPacket
from agentforge.rag.retriever import RagRetriever
from agentforge.utils.llm_util import LLMUtil


class DomainState(TypedDict, total=False):
    handoff: HandoffPacket
    tech_stack: str
    framework_version: str
    project_id: str
    dry_run: bool
    llm: Any
    upstream: dict[str, DomainResult]
    rag_context: str
    code: str
    summary: str
    file_path: str
    stages: list[dict[str, str]]


def _prepare_context_node(state: DomainState) -> DomainState:
    handoff = state["handoff"]
    domain = handoff.payload.get("domain", handoff.target)
    if state.get("dry_run"):
        return {"rag_context": ""}

    llm: LLMUtil = state["llm"] if state.get("llm") else LLMUtil()
    framework_version = state.get("framework_version", "4.0")
    retriever = RagRetriever(llm=llm)
    query = f"{handoff.task_summary} {domain} Spring Boot {framework_version}"
    chunks = retriever.retrieve(
        query,
        domain=domain,
        framework_version=framework_version,
    )
    rag_context = retriever.format_context(chunks)

    from agentforge.rag.codegen_error_memory import CodegenErrorMemory

    error_lessons = CodegenErrorMemory(llm=llm).retrieve_for_codegen(
        f"{handoff.task_summary} {domain} Java codegen",
        codegen_domain=domain,
        framework_version=framework_version,
    )
    if error_lessons:
        rag_context = f"{error_lessons}\n\n{rag_context}"

    return {"rag_context": rag_context}


def _codegen_node(state: DomainState) -> DomainState:
    handoff = state["handoff"]
    domain = handoff.payload.get("domain", handoff.target)
    agent = get_domain_agent(domain)
    upstream = state.get("upstream", {})
    framework_version = state.get("framework_version", "4.0")
    llm: LLMUtil = state["llm"] if state.get("llm") else LLMUtil()
    file_path = agent.target_file(handoff)
    pipeline = PhasedCodegenPipeline(llm)

    code, stage_results = pipeline.run(
        agent,
        handoff,
        framework_version=framework_version,
        upstream=upstream,
        rag_context=state.get("rag_context", ""),
        project_id=state.get("project_id", ""),
        file_path=file_path,
        dry_run=bool(state.get("dry_run")),
    )

    stages = [
        {"stage": s.stage, "summary": s.summary, "truncated": str(s.truncated)}
        for s in stage_results
    ]
    summary = stage_results[-1].summary if stage_results else f"{domain} 完成"
    logger.bind(domain=domain, agent=agent.spec.agent_name, stages=len(stages)).info(summary)
    return {
        "code": code,
        "summary": f"{agent.spec.agent_name} {summary} → {file_path}",
        "file_path": file_path,
        "stages": stages,
    }


@lru_cache
def build_domain_subgraph():
    graph = StateGraph(DomainState)
    graph.add_node("prepare", _prepare_context_node)
    graph.add_node("codegen", _codegen_node)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "codegen")
    graph.add_edge("codegen", END)
    return graph.compile()


def run_domain_subgraph(
    handoff: HandoffPacket,
    *,
    tech_stack: str = "spring-boot",
    framework_version: str = "4.0",
    project_id: str = "",
    upstream: dict[str, DomainResult] | None = None,
    llm: LLMUtil | None = None,
    dry_run: bool = False,
    write_sandbox: bool = True,
) -> DomainResult:
    """执行单个领域 SubGraph，可选落盘沙盒。"""
    subgraph = build_domain_subgraph()
    domain = handoff.payload.get("domain", handoff.target)
    agent = get_domain_agent(domain)

    result_state = subgraph.invoke({
        "handoff": handoff,
        "tech_stack": tech_stack,
        "framework_version": framework_version,
        "project_id": project_id,
        "upstream": upstream or {},
        "dry_run": dry_run,
        "llm": llm,
    })

    file_path = result_state.get("file_path", agent.target_file(handoff))
    code = strip_code_fences(result_state.get("code", ""))

    if write_sandbox and project_id and code and not dry_run:
        from agentforge.sandbox.manager import SandboxManager

        SandboxManager().write_text(project_id, file_path, code)

    return DomainResult(
        domain=domain,
        agent=agent.spec.agent_name,
        summary=result_state.get("summary", ""),
        code=code,
        file_path=file_path,
        stages=result_state.get("stages"),
    )
