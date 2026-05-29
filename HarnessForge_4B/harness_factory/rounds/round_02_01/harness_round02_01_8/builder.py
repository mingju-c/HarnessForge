from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Agents.agents import ToolCallingAgent
from module_action.base_action import ActionContext
from .action_module.provider import ACTION_SYSTEM, get_provider
from .memory_module.provider import MEMORY_SYSTEM as DEFAULT_MEMORY_SYSTEM
from .planning_module.provider import PLANNING_SYSTEM, PlanningClass


HARNESS_NAME = 'harness_round02_01_8'
DEFAULT_BENCH_TYPE = None
PAIRING_REASON = 'round02_lightweight_verifier'


def _bind_agent_reference(agent: ToolCallingAgent, tool: object | None) -> None:
    if tool is not None and hasattr(tool, "agent"):
        setattr(tool, "agent", agent)


def _ensure_owl_memory(agent: ToolCallingAgent) -> None:
    if getattr(agent, "planning_system", None) != "owl":
        return
    if not hasattr(agent, "web_memory") or agent.web_memory is None:
        agent.web_memory = []
    if not hasattr(agent, "reasoning_memory") or agent.reasoning_memory is None:
        agent.reasoning_memory = []


def prepare_context(context: ActionContext) -> ActionContext:
    bench_type = context.bench_type or DEFAULT_BENCH_TYPE
    prepared_kwargs = dict(context.kwargs)
    prepared_kwargs["planning_class"] = PlanningClass
    prepared_kwargs.setdefault("max_tool_calls_per_step", 2)
    prepared_kwargs.setdefault("round02_profile", 'harness_round02_01_8')
    return replace(
        context,
        planning_system=PLANNING_SYSTEM,
        action_system=ACTION_SYSTEM,
        prompts_type=ACTION_SYSTEM,
        bench_type=bench_type,
        project_root=Path(__file__).resolve().parent,
        kwargs=prepared_kwargs,
    )


def build_agent_from_context(context: ActionContext) -> ToolCallingAgent:
    prepared_context = prepare_context(context)
    action_provider = get_provider()
    agent = action_provider.build(prepared_context)

    setattr(agent, "planning_system", prepared_context.planning_system)
    setattr(agent, "action_system", prepared_context.action_system)
    setattr(agent, "harness_name", HARNESS_NAME)
    setattr(
        agent,
        "harness_metadata",
        {
            "planning_system": PLANNING_SYSTEM,
            "action_system": ACTION_SYSTEM,
            "default_bench_type": DEFAULT_BENCH_TYPE,
            "recommended_memory_system": DEFAULT_MEMORY_SYSTEM,
            "pairing_reason": PAIRING_REASON,
            "round": "round_02_01",
            "design_focus": 'low-overhead verifier with schema cooldown and support recording',
            "policy": getattr(agent, "harness_policy", {}),
        },
    )

    if prepared_context.vector_tool is not None:
        prepared_context.vector_tool.memory = agent.memory

    _bind_agent_reference(agent, prepared_context.process_tool)
    _bind_agent_reference(agent, prepared_context.end_process_tool)
    _bind_agent_reference(agent, prepared_context.delete_memory_tool)
    _bind_agent_reference(agent, prepared_context.executor_tool)
    _bind_agent_reference(agent, prepared_context.refine_tool)

    _ensure_owl_memory(agent)
    return agent
