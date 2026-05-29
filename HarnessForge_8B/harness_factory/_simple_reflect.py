from __future__ import annotations

import copy
import textwrap
from typing import Any, Callable, Dict, List, Optional

from jinja2 import StrictUndefined, Template
from rich.rule import Rule
from rich.text import Text

from Agents.memory import ActionStep, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import LogLevel
from module_action.base_action import ActionContext, BaseActionProvider
from module_planning.base_planning import BasePlanning


ACTION_SYSTEM = "simple_reflect"
PLANNING_SYSTEM = "simple_reflect"


SIMPLE_REFLECT_PROMPTS: dict[str, Any] = {
    "system_prompt": """You are a closed-set ReAct tool-using assistant with a light reflection loop.

Your job is to solve the user's task with the provided tools only. Use one main executor path, observe carefully, and stop as soon as the answer or required environment state is supported.

Core policy:
1. Treat the available tool schemas as the only source of valid tool names and argument names.
2. Prefer one tool call per step, especially for state-changing API or environment tasks.
3. Only call multiple tools in one step when they are clearly independent and read-only.
4. Never invent tools, APIs, arguments, files, patients, orders, records, or observations.
5. Never repeat an identical failed call unless a later observation gives a concrete reason it should now work.
6. If a tool fails due to schema or invalid arguments, repair the arguments or choose another valid tool on the next step.
7. If current observations already support the answer, call final_answer immediately.
8. For stateful tasks, make the minimal valid sequence of actions and avoid speculative changes.

Available tools:
{%- for tool in tools.values() %}
- {{ tool.name }}: {{ tool.description }}
    Inputs: {{ tool.inputs }}
    Output: {{ tool.output_type }}
{%- endfor %}

Output contract:
Return strict JSON only:
{
  "think": "brief reasoning for the next action",
  "tools": [
    {"name": "actual_tool_name", "arguments": {"arg": "value"}}
  ]
}

If no further non-final tool is needed, call final_answer as the only tool.""",
    "step": {
        "pre_messages": """Continue the simple ReAct loop.

Original task:
{{task}}

Available tool schemas:
{{tool_functions_json}}

Decision checklist:
- What fact, validation, or state transition is still missing?
- Is the next tool call valid under the exact schema above?
- Did the same call already fail? If yes, change the argument, choose a different valid tool, or finalize if enough evidence exists.
- For state-changing tools, avoid parallel calls and preserve transaction order.
- If observations already support the answer or completion condition, call final_answer only.

Return strict JSON only:
{
  "think": "brief reasoning for the next action",
  "tools": [
    {"name": "actual_tool_name", "arguments": {"arg": "value"}}
  ]
}"""
    },
    "final_answer": {
        "pre_messages": "Produce the final answer from the task, plan, reflections, and observed tool results.",
        "post_messages": """Return strict JSON only:
{
  "think": "brief reason why the answer is supported",
  "answer": "the final answer"
}

Rules:
- The answer field must contain only the requested final answer or completion result.
- Base the answer on observations only.
- Do not invent missing facts.
- For ToolHop-style tasks, return the raw short answer.

Task:
{{task}}""",
    },
    "planning": {
        "initial_plan": """You are the planning module for a simple single-executor tool agent.

Create a short, practical plan for the task. Do not design a multi-agent workflow, debate, committee, expert panel, or parallel investigation. The executor will use the provided tools directly.

Available tools:
{%- for tool in tools.values() %}
- {{ tool.name }}: {{ tool.description }}
    Inputs: {{ tool.inputs }}
    Output: {{ tool.output_type }}
{%- endfor %}

Plan requirements:
- Keep the plan to 2-4 concise steps.
- Name the exact kind of evidence or state transition needed.
- For stateful/API tasks, preserve the necessary transaction order.
- Include one fallback rule for invalid arguments or repeated failed calls.
- Do not solve the task during planning.

Return a concise numbered plan.""",
        "task_input": "Task:\n{{task}}",
    },
    "summary": {
        "update_pre_messages": """You are the reflection module for a simple single-executor tool agent.

Review the trajectory so far. Focus on:
- facts or state changes that are already established
- the next missing fact or required action
- repeated failed calls, invalid arguments, or schema mismatch
- whether the agent should stop and call final_answer

Do not propose multi-agent delegation. Do not invent tools.""",
        "update_post_messages": """Write a concise reflection for task {{task}} at step {{step}}.

Return:
1. established_facts
2. failed_or_repeated_patterns
3. next_best_action
4. ready_for_final_answer: yes/no""",
    },
}


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    return compiled_template.render(**variables)


def simple_reflect_prompt_templates() -> dict[str, Any]:
    return copy.deepcopy(SIMPLE_REFLECT_PROMPTS)


class SimpleReflectPlanningProvider(BasePlanning):
    def topology_initialize(self, task: str) -> PlanningStep:
        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["planning"]["initial_plan"],
                            {"task": task, "tools": self.tools},
                        ),
                    }
                ],
            }
        ]
        memory_guidance = self.append_memory_guidance(input_messages)
        task_messages = [
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["planning"].get("task_input", "Task:\n{{task}}"),
                            {"task": task, "tools": self.tools},
                        ),
                    }
                ],
            }
        ]

        response: ChatMessage = self.model(input_messages + task_messages)
        plan_text = getattr(response, "content", str(response))
        plan_reasoning = getattr(response, "reasoning_content", "") or ""

        self.logger.log(
            Rule("Simple Reflect Plan", style="orange"),
            Text(textwrap.dedent(f"""Plan:
```
{plan_text}
```""")),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plan_text,
            plan_think="",
            plan_reasoning=plan_reasoning,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[
            [Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]
        ],
    ) -> SummaryStep:
        memory_messages = write_memory_to_messages(None, False)[1:]
        variables = {"task": task, "step": step, "tools": self.tools}
        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["summary"]["update_pre_messages"],
                            variables,
                        ),
                    }
                ],
            },
            *memory_messages,
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["summary"]["update_post_messages"],
                            variables,
                        ),
                    }
                ],
            },
        ]

        response: ChatMessage = self.model(input_messages)
        summary_text = getattr(response, "content", str(response))
        summary_reasoning = getattr(response, "reasoning_content", "") or ""

        self.logger.log(
            Rule("Simple Reflection", style="orange"),
            Text(f"\n{summary_text}\n"),
            level=LogLevel.INFO,
        )

        summary_step = SummaryStep(
            model_input_messages=input_messages,
            summary=summary_text,
            summary_reasoning=summary_reasoning,
        )
        self.memory.steps.append(summary_step)
        return summary_step


class SimpleReflectActionProvider(BaseActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    DEFAULT_SUMMARY_INTERVAL = 6

    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = self.PROMPTS_TYPE
        self.prompt_templates = simple_reflect_prompt_templates()
        self.organization_planning_system = PLANNING_SYSTEM

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        agent = self.create_agent(
            context,
            tools=tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        if getattr(agent, "planning", None) is not None:
            agent.planning.prompt_templates = simple_reflect_prompt_templates()
        if agent.summary_interval is None and context.max_steps >= self.DEFAULT_SUMMARY_INTERVAL + 2:
            agent.summary_interval = self.DEFAULT_SUMMARY_INTERVAL
        setattr(
            agent,
            "simple_reflect_policy",
            {
                "mode": "single_executor_with_periodic_reflection",
                "summary_interval": agent.summary_interval,
                "no_parallel_subagents": True,
            },
        )
        return agent


__all__ = [
    "ACTION_SYSTEM",
    "PLANNING_SYSTEM",
    "SimpleReflectActionProvider",
    "SimpleReflectPlanningProvider",
    "simple_reflect_prompt_templates",
]
