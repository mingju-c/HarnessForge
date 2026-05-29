import textwrap
import json
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from module_planning.base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Fill Jinja2 template with variables.
    """
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")

class PlanningProvider(BasePlanning):
    """
    Planning implementation for hierarchical task decomposition.
    Includes task decomposition and state management.
    """

    def __init__(
        self,
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        tools: Dict[str, Tool],
        prompt_templates: Dict[str, Any],
        memory: AgentMemory,
        logger: AgentLogger
    ):
        super().__init__(model, tools, prompt_templates, memory, logger)
        self.orchestra_tasks = []

    def topology_initialize(self, task: str) -> PlanningStep:
        self.logger.log(
            Rule("[bold]Task Planning", style="cyan"),
            level=LogLevel.INFO,
        )
        
        system_message = {
            "role": MessageRole.SYSTEM,
            "content": [
                {
                    "type": "text",
                    "text": populate_template(
                        self.prompt_templates["planning"]["initial_plan"],
                        variables={"task": task},
                    ),
                }
            ],
        }
        task_message = {
            "role": MessageRole.USER,
            "content": [
                {
                    "type": "text",
                    "text": populate_template(
                        self.prompt_templates["planning"].get("task_input", "User Objective: {{task}}"),
                        variables={"task": task},
                    ),
                }
            ],
        }
        messages = [system_message]
        memory_guidance = self.append_memory_guidance(messages)
        model_messages = messages + [task_message]
        
        try:
            # Use the model to decompose the task
            response: ChatMessage = self.model(model_messages)
            content = (response.content or "").strip()
            if not content:
                raise ValueError("Empty planning content")
            
            # Basic cleanup of the response content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            tasks_data = json.loads(content.strip())
            
            if not isinstance(tasks_data, list):
                raise ValueError("Model response is not a list")

            self.orchestra_tasks = []
            for i, t in enumerate(tasks_data):
                self.orchestra_tasks.append({
                    "id": i,
                    "description": t.get("description", "Unknown task"),
                    "priority": t.get("priority", "medium"),
                    "category": t.get("category", "general"),
                    "status": "pending",
                    "result": None
                })
            
            plan_text = "\n".join([f"{i}. [{t['priority'].upper()}] {t['description']}" for i, t in enumerate(self.orchestra_tasks)])
            self.logger.log(
                Text(f"Decomposed objective into {len(self.orchestra_tasks)} tasks:\n{plan_text}"),
                level=LogLevel.INFO
            )
            
        except Exception as e:
            self.logger.log(
                Text(
                    f"Failed to decompose task via LLM: {str(e)}. Falling back to single-task mode."
                ),
                level=LogLevel.ERROR,
            )
            self.orchestra_tasks = [{
                "id": 0,
                "description": task,
                "priority": "high",
                "category": "general",
                "status": "pending",
                "result": None
            }]
            plan_text = f"1. [HIGH] {task}"

        planning_step = PlanningStep(
            model_input_messages=model_messages,
            plan=plan_text,
            plan_think="Automated task decomposition completed. The system is ready for structured execution.",
            plan_reasoning="Hierarchical decomposition into manageable steps. The model must now use 'check_plan_progress' to begin execution and follow the mandatory JSON output format strictly.",
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
        self.logger.log(
            Rule("[bold]Progress Check & Summary", style="cyan"),
            level=LogLevel.INFO,
        )

        # Get all messages including the system prompt and previous steps
        memory_messages = write_memory_to_messages()
        
        # Construct messages for the model to generate a summary
        messages = memory_messages + [
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["summary"]["update_post_messages"],
                            variables={
                                "task": task,
                                "step": step,
                                "orchestra_tasks": json.dumps(self.orchestra_tasks, indent=2, ensure_ascii=False)
                            }
                        ),
                    }
                ],
            }
        ]
        
        try:
            response: ChatMessage = self.model(messages)
            summary_content = response.content
            summary_reasoning = getattr(response, "reasoning_content", "Periodic status review for hierarchical orchestration.")
            
            self.logger.log(
                Text(f"Strategic Summary (Step {step}):\n{summary_content}"),
                level=LogLevel.INFO
            )
            
            summary_step = SummaryStep(
                model_input_messages=messages,
                summary=summary_content,
                summary_reasoning=summary_reasoning,
            )
        except Exception as e:
            self.logger.log(
                Text(f"Failed to generate summary: {str(e)}"),
                level=LogLevel.ERROR,
            )
            summary_step = SummaryStep(
                model_input_messages=[],
                summary="Monitoring execution progress. Summary generation failed, but the process continues.",
                summary_reasoning=f"Error: {str(e)}",
            )
            
        self.memory.steps.append(summary_step)
        return summary_step

PLANNING_SYSTEM = 'agentorchestra'
PLANNING_MODULE = 'agentorchestra'
PlanningClass = PlanningProvider

__all__ = ['PLANNING_SYSTEM', 'PLANNING_MODULE', 'PlanningProvider', 'PlanningClass']

