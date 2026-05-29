import textwrap
import json
import re
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from rich.rule import Rule
from rich.text import Text

from .base_planning import BasePlanning
from Agents.memory import ActionStep, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import LogLevel


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")


class CosightPlanning(BasePlanning):
    """
    Coordination planning:
    Step 1: call `co_sight` exactly once
    Step 2: call `final_answer` exactly once
    """

    def _is_expert_mode(self) -> bool:
        role_info = getattr(self, "role_info", None)
        if isinstance(role_info, dict):
            role_name = str(role_info.get("name", "")).lower()
            if "expert" in role_name:
                return True
            if "coordinator" in role_name:
                return False
        return "cosight_internal" not in self.prompt_templates

    def topology_initialize(self, task: str) -> PlanningStep:
        """
        Let the model decide how many experts (1-4) are needed based on task complexity.
        If this is an internal expert, generate a simple research plan via LLM.
        """
        if self._is_expert_mode():
            expert_plan_prompt = f"As an expert researcher, provide a very concise, step-by-step research plan (max 3 steps) for this task: {task}\nReturn ONLY the plan text."
            try:
                input_messages = []
                memory_guidance = self.append_memory_guidance(input_messages)
                input_messages.append({"role": "user", "content": [{"type": "text", "text": expert_plan_prompt}]})
                resp = self.model(input_messages)
                plan_text = getattr(resp, "content", str(resp)).strip()
            except Exception:
                plan_text = "Analyze task requirements and use available tools to gather and verify evidence."
                memory_guidance = None

            self.logger.log(
                Rule("Expert Plan", style="green"),
                Text(f"Proposed Research Strategy:\n{plan_text}\n"),
                level=LogLevel.INFO,
            )

            planning_step = PlanningStep(
                model_input_messages=[],
                plan=plan_text,
                plan_think="",
                plan_reasoning="Expert-level research strategy generated.",
                memory_guidance=memory_guidance,
            )
            self.memory.steps.append(planning_step)
            return planning_step

        judge_prompt = f"""Analyze the following task and decide how many experts (integer 1-4) are needed to solve it reliably. 
Consider complexity, potential for conflicting information, and depth of research required.
Task: {task}
Return ONLY a JSON object: {{"num_expert": N, "reasoning": "..."}}"""

        try:
            input_messages = []
            input_messages.append({"role": "user", "content": [{"type": "text", "text": judge_prompt}]})
            memory_guidance = self.append_memory_guidance(input_messages)
            resp = self.model(input_messages)
            out = getattr(resp, "content", str(resp))
            match = re.search(r"\{.*\}", out, re.DOTALL)
            data = json.loads(match.group(0)) if match else {}
            num_expert = int(data.get("num_expert", 3))
            num_expert = max(1, min(4, num_expert))
            reasoning = data.get("reasoning", "Dynamic expert count based on task complexity.")
        except (AttributeError, ValueError):
            num_expert = 3
            reasoning = "Defaulting to 3 experts due to analysis failure."
            memory_guidance = None

        plan_text = json.dumps([{"name": "expert_parallel", "arguments": {"task": task, "num_expert": num_expert}}])
        plan_reasoning = f"Analysis: {reasoning} -> Protocol starts with 'expert_parallel' for {num_expert} experts."

        self.logger.log(
            Rule("Execution", style="orange"),
            Text(f"Complexity analysis complete: Using {num_expert} experts. Initializing expert group...\nReasoning: {reasoning}\nPlan: {plan_text}\n"),
            level=LogLevel.INFO,
        )

        planning_step = PlanningStep(
            model_input_messages=[],
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
        write_memory_to_messages: Callable[[Optional[List[ActionStep]], Optional[bool]], List[Dict[str, str]]],
    ) -> SummaryStep:

        summary_step = SummaryStep(
            model_input_messages="",
            summary="",
            summary_reasoning="",
        )
        return summary_step
