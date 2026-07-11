"""LangGraph 三层多智能体主图：路由 → 领域 SubGraph → 整合。"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from loguru import logger

from agentforge.agents.handoff import DomainResult
from agentforge.agents.integrator import IntegratorAgent
from agentforge.agents.router import RouterAgent
from agentforge.agents.state import AgentState
from agentforge.agents.subgraphs.domain import run_domain_subgraph
from agentforge.plugins import get_framework
from agentforge.templates.loader import compose_template_to_sandbox
from agentforge.utils.llm_util import LLMUtil


def _get_llm(state: AgentState) -> LLMUtil:
    llm = state.get("metadata", {}).get("llm")
    return llm if isinstance(llm, LLMUtil) else LLMUtil()


def _is_dry_run(state: AgentState) -> bool:
    return bool(state.get("metadata", {}).get("dry_run"))


def _get_template_stack(state: AgentState) -> list[str]:
    stack = state.get("template_stack")
    if stack:
        return list(stack)
    meta = state.get("metadata", {})
    if isinstance(meta.get("template_stack"), list):
        return list(meta["template_stack"])
    return ["base"]


def _ensure_sandbox(state: AgentState) -> None:
    if _is_dry_run(state):
        return
    project_id = state["project_id"]
    try:
        compose_template_to_sandbox(
            project_id,
            _get_template_stack(state),
            framework_version=state.get("framework_version", "4.0"),
            clean=True,
        )
        logger.bind(project_id=project_id).info(
            "沙盒已从模板栈初始化: {}", _get_template_stack(state)
        )
    except Exception as exc:
        logger.warning("沙盒初始化跳过: {}", exc)


def _route_node(state: AgentState) -> AgentState:
    llm = _get_llm(state)
    router = RouterAgent(llm)
    plugin = get_framework(state.get("tech_stack", "spring-boot"))
    use_llm = not _is_dry_run(state)
    domains, handoffs, system_prompt = router.route(
        state["user_message"],
        tech_stack=state.get("tech_stack", "spring-boot"),
        framework_version=state.get("framework_version", "4.0"),
        use_llm=use_llm,
    )
    domains = plugin.sort_domains(domains)
    handoffs = [plugin.build_handoff(d, state["user_message"]) for d in domains]
    logger.bind(session_id=state.get("session_id")).info("主图-路由: {}", domains)
    return {
        "route_domains": domains,
        "handoffs": handoffs,
        "system_prompt": system_prompt,
    }


def _execute_node(state: AgentState) -> AgentState:
    """第二层：按依赖顺序执行各领域 SubGraph，上游产出传递给下游。"""
    _ensure_sandbox(state)
    llm = _get_llm(state)
    dry_run = _is_dry_run(state)
    plugin = get_framework(state.get("tech_stack", "spring-boot"))
    ordered_domains = plugin.sort_domains(state.get("route_domains", []))
    handoff_map = {
        h.payload.get("domain", h.target): h for h in state.get("handoffs", [])
    }

    results: list[DomainResult] = []
    outputs: dict[str, str] = {}
    upstream: dict[str, DomainResult] = {}

    for domain in ordered_domains:
        handoff = handoff_map.get(domain)
        if not handoff:
            continue
        domain_result = run_domain_subgraph(
            handoff,
            tech_stack=state.get("tech_stack", "spring-boot"),
            framework_version=state.get("framework_version", "4.0"),
            project_id=state["project_id"],
            upstream=upstream,
            llm=llm,
            dry_run=dry_run,
            write_sandbox=not dry_run,
        )
        results.append(domain_result)
        outputs[domain] = domain_result.code
        upstream[domain] = domain_result

    logger.bind(session_id=state.get("session_id")).info(
        "主图-执行: {} 个 SubGraph 完成，顺序={}", len(results), ordered_domains
    )
    return {
        "domain_results": results,
        "domain_outputs": outputs,
    }


def _integrate_node(state: AgentState) -> AgentState:
    integrator = IntegratorAgent(_get_llm(state))
    results = state.get("domain_results", [])
    system, final_prompt = integrator.prepare(
        state["user_message"],
        state.get("route_domains", []),
        results,
    )
    return {
        "system_prompt": system,
        "final_prompt": final_prompt,
    }


@lru_cache
def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("route", _route_node)
    graph.add_node("execute", _execute_node)
    graph.add_node("integrate", _integrate_node)
    graph.add_edge(START, "route")
    graph.add_edge("route", "execute")
    graph.add_edge("execute", "integrate")
    graph.add_edge("integrate", END)
    return graph.compile()


def run_agent_pipeline(
    *,
    session_id: str,
    project_id: str,
    user_message: str,
    tech_stack: str = "spring-boot",
    framework_version: str = "4.0",
    template_stack: list[str] | None = None,
    llm: LLMUtil | None = None,
    dry_run: bool = False,
) -> AgentState:
    graph = build_agent_graph()
    stack = template_stack or ["base"]
    initial: AgentState = {
        "session_id": session_id,
        "project_id": project_id,
        "tech_stack": tech_stack,
        "framework_version": framework_version,
        "template_stack": stack,
        "user_message": user_message,
        "metadata": {"llm": llm, "dry_run": dry_run, "template_stack": stack},
    }
    return graph.invoke(initial)
