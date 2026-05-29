import json
import textwrap
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from .base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")


class JoyAgentPlanning(BasePlanning):

    def _get_role_planning_templates(self, role: Dict[str, str]) -> Dict[str, str]:
        if role["name"] == "PE-Worker":
            return {
                "initial_plan": (
                    "### Roadmap (One-time)\n"
                    "1. Identify the key task requirements and missing information.\n"
                    "2. Use the available tools to gather, inspect, validate, or compute the needed evidence.\n"
                    "3. Cross-check critical findings when necessary.\n"
                    "4. Produce a definitive answer.\n"
                    "[STRICT] Follow the roadmap. No re-planning."
                ),
                "task_input": "Task: {{task}}. Generate roadmap.",
            }
        if role["name"] == "ReAct-Worker":
            return {
                "initial_plan": "### ReAct Strategy\nLoop: Think -> Act -> Observe.",
                "task_input": "Task: {{task}}. State strategy.",
            }
        return self.prompt_templates.get("planning", {})

    def _get_role_summary_templates(self, role: Dict[str, str]) -> Dict[str, str]:
        if role["name"] == "PE-Worker":
            return {
                "update_pre_messages": "Reporting progress...",
                "update_post_messages": "Summarize status versus roadmap. No re-planning.",
            }
        if role["name"] == "ReAct-Worker":
            return {
                "update_pre_messages": "Analyzing exploration...",
                "update_post_messages": "Summarize findings and adapt if blocked.",
            }
        return self.prompt_templates.get("summary", {})

    def _get_role_info(self) -> Dict[str, str]:
        explicit_role = getattr(self, "role_info", None)
        if isinstance(explicit_role, dict) and explicit_role.get("name"):
            return explicit_role

        content = self.prompt_templates.get("system_prompt", "")
        if "coordination agent" in content.lower():
            return {"name": "Task Augmentation", "style": "bold yellow", "title_suffix": ""}
        if "plan-and-execute expert" in content.lower():
            return {"name": "PE-Worker", "style": "cyan", "title_suffix": " Roadmap"}
        if "react expert" in content.lower():
            return {"name": "ReAct-Worker", "style": "magenta", "title_suffix": " Strategy"}
        return {"name": "Worker", "style": "blue", "title_suffix": " Planning"}

    def topology_initialize(self, task: str) -> PlanningStep:
        role = self._get_role_info()
        planning_templates = self._get_role_planning_templates(role)
        retrieved_knowledge = ""

        # 1. Semantic Memory Retrieval (Supervisor only)
        if role['name'] == "Task Augmentation":
            vector_tool = self.tools.get("vector_similarity_retrieve")
            if vector_tool:
                try:
                    # Search through current memory steps (which include historical Knowledge Units)
                    retrieved_knowledge = vector_tool.forward(task)
                    if "No historical action steps" in retrieved_knowledge or "Error" in retrieved_knowledge:
                        retrieved_knowledge = ""
                    else:
                        # Token Optimization: Strictly truncate historical context
                        if len(retrieved_knowledge) > 500:
                            retrieved_knowledge = retrieved_knowledge[:500] + "... (truncated)"

                        # Format history to be clearly distinct from current task
                        retrieved_knowledge = f"\n[PAST EXPERIENCE (For Reference Only)]:\n{retrieved_knowledge}"
                        self.logger.log(Text("\n[Semantic Memory] Relevant historical context retrieved.", style="italic cyan"), level=LogLevel.INFO)
                except Exception:
                    retrieved_knowledge = ""

        input_messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            planning_templates["initial_plan"],
                            variables={"tools": self.tools, "retrieved_knowledge": retrieved_knowledge, "task": task},
                        ),
                    }
                ],
            },
        ]
        memory_guidance = self.append_memory_guidance(input_messages)
        task_messages = [{
            "role": MessageRole.USER,
            "content": [{"type": "text", "text": populate_template(planning_templates["task_input"], variables={"task": task})}],
        }]

        chat_message_plan: ChatMessage = self.model(input_messages + task_messages)
        plans_answer = chat_message_plan.content
        think_content = getattr(chat_message_plan, "reasoning_content", "")

        title = f"{role['name']}{role['title_suffix']}"

        self.logger.log(
            Rule(title, style=role['style']),
            Text(f"\n{plans_answer}\n"),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=plans_answer,
            plan_think="",
            plan_reasoning=think_content,
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(
        self,
        task: str,
        step: int,
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]]
    ) -> SummaryStep:
        role = self._get_role_info()
        if role['name'] == "Task Augmentation":
            return SummaryStep(model_input_messages=[], summary="Monitoring ensemble execution...", summary_reasoning="")
        summary_templates = self._get_role_summary_templates(role)

        # Worker Summary Policy: STRICTLY Progress-only, NO re-planning.
        memory_messages = write_memory_to_messages(None, False)[1:]
        summary_policy = "\n[SUMMARY POLICY]: Report progress ONLY. DO NOT change the initial roadmap or propose new plans."

        input_messages = [
            {"role": MessageRole.SYSTEM, "content": [{"type": "text", "text": summary_templates["update_pre_messages"] + summary_policy}]},
            *memory_messages,
            {"role": MessageRole.USER, "content": [{"type": "text", "text": summary_templates["update_post_messages"]}]}
        ]

        chat_message_summary: ChatMessage = self.model(input_messages)
        summary_answer = chat_message_summary.content
        summary_cot = getattr(chat_message_summary, "reasoning_content", "")

        self.logger.log(
            Rule(f"{role['name']} Execution Summary", style="blue"),
            Text(f"\n{summary_answer}\n"),
            level=LogLevel.INFO,
        )

        summary_step = SummaryStep(input_messages, summary_answer, summary_cot)
        self.memory.steps.append(summary_step)
        return summary_step
