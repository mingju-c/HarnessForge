#!/usr/bin/env python
# coding=utf-8

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Portions of this file are modifications by OPPO PersonalAI Team.
# Licensed under the Apache License, Version 2.0.

import json
import re
from pathlib import Path
from copy import deepcopy
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from logging import getLogger
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple, TypedDict, Union
import yaml
from jinja2 import StrictUndefined, Template
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

import harness_runtime  # noqa: F401

from module_planning.registry import (
    get_planning_class,
    load_planning_prompt_templates,
    load_prompt_templates,
)

from .agent_types import AgentType, handle_agent_output_types
from .tools import FinalAnswerTool, VectorSimilarityRetrieve, Reasoning
from .memory import ActionStep, AgentMemory, PlanningStep, SummaryStep, SystemPromptStep, TaskStep, ToolCall
from .models import (
    ChatMessage,
    MessageRole,
)
from .monitoring import (
    YELLOW_HEX,
    AgentLogger,
    LogLevel,
)
from .tools import Tool
import json_repair
from .utils import (
    AgentError,
    AgentExecutionError,
    AgentGenerationError,
    AgentMaxStepsError,
    parse_json_tool_call,
)


logger = getLogger(__name__)


def get_variable_names(self, template: str) -> Set[str]:
    pattern = re.compile(r"\{\{([^{}]+)\}\}")
    return {match.group(1).strip() for match in pattern.finditer(template)}


def populate_template(template: str, variables: Dict[str, Any]) -> str:
    # Use default Undefined instead of StrictUndefined to handle auto-generated templates
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        # Retry with lenient undefined handling for auto-generated templates
        compiled_template = Template(template)
        try:
            return compiled_template.render(**variables)
        except Exception as e2:
            raise Exception(f"Error during jinja template rendering: {type(e2).__name__}: {e2}")

def parse_model_content(content: Union[str, dict]) -> dict:

    if isinstance(content, dict):
        return content
    elif isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"text": content}
    else:
        return {"unknown_type": str(content)}

class PlanningPromptTemplate(TypedDict):
    """
    Prompt templates for the planning step.

    Args:
        initial_plan (`str`): Initial plan prompt.
    """

    initial_plan: str

class SummaryPromptTemplate(TypedDict):
    """
    Prompt templates for the planning step.

    Args:
        update_pre_messages (`str`): Progress execution prompt.
        update_post_messages (`str`): Progress execution prompt.
    """

    update_pre_messages: str
    update_post_messages: str


class FinalAnswerPromptTemplate(TypedDict):
    """
    Prompt templates for the final answer.

    Args:
        pre_messages (`str`): Pre-messages prompt.
        post_messages (`str`): Post-messages prompt.
    """

    pre_messages: str
    post_messages: str


class PromptTemplates(TypedDict):
    """
    Prompt templates for the agent.

    Args:
        system_prompt (`str`): System prompt.
        planning ([`~agents.PlanningPromptTemplate`]): Planning prompt templates.
        summary ([`~agents.SummaryPromptTemplate`]): Summary prompt templates.
        final_answer ([`~agents.FinalAnswerPromptTemplate`]): Final answer prompt templates.
    """

    system_prompt: str
    planning: PlanningPromptTemplate
    summary: SummaryPromptTemplate
    final_answer: FinalAnswerPromptTemplate


EMPTY_PROMPT_TEMPLATES = PromptTemplates(
    system_prompt="",
    planning=PlanningPromptTemplate(initial_plan=""),
    summary=SummaryPromptTemplate(),
    final_answer=FinalAnswerPromptTemplate(pre_messages="", post_messages=""),
)


class MultiStepAgent:
    """
    Agent class that solves the given task step by step, using the ReAct framework:
    While the objective is not reached, the agent will perform a cycle of action (given by the LLM) and observation (obtained from the environment).

    Args:
        tools (`list[Tool]`): [`Tool`]s that the agent can use.
        model (`Callable[[list[dict[str, str]]], ChatMessage]`): Model that will generate the agent's actions.
        prompt_templates ([`~agents.PromptTemplates`], *optional*): Prompt templates.
        max_steps (`int`, default `6`): Maximum number of steps the agent can take to solve the task.
        verbosity_level (`LogLevel`, default `LogLevel.INFO`): Level of verbosity of the agent's logs.
        grammar (`dict[str, str]`, *optional*): Grammar used to parse the LLM output.
        managed_agents (`list`, *optional*): Managed agents that the agent can call.
        name (`str`, *optional*): Necessary for a managed agent only - the name by which this agent can be called.
        description (`str`, *optional*): Necessary for a managed agent only - the description of this agent.
        provide_run_summary (`bool`, *optional*): Whether to provide a run summary when called as a managed agent.
    """

    def __init__(
            self,
            tools: List[Tool],
            model: Callable[[List[Dict[str, str]]], ChatMessage],
            prompt_templates: Optional[PromptTemplates] = None,
            max_steps: int = 40,
            verbosity_level: LogLevel = LogLevel.INFO,
            grammar: Optional[Dict[str, str]] = None,
            managed_agents: Optional[List] = None,
            summary_interval: Optional[int] = None,
            name: Optional[str] = None,
            description: Optional[str] = None,
            provide_run_summary: bool = False,
            debug: bool = False,
            prompts_type: Optional[str] = "default",
    ):
        self.agent_name = self.__class__.__name__
        self.model = model
        self.prompt_templates = prompt_templates or EMPTY_PROMPT_TEMPLATES
        self.max_steps = max_steps
        self.step_number: int = 0
        self.grammar = grammar
        self.summary_interval = summary_interval
        self.state = {}
        self.name = name
        self.description = description
        self.provide_run_summary = provide_run_summary
        self.debug = debug
        self.action_trajectory = []
        self.managed_agents = {}

        for tool in tools:
            assert isinstance(tool, Tool), f"This element is not of class Tool: {str(tool)}"
        self.tools = {tool.name: tool for tool in tools}
        self.tools["final_answer"] = FinalAnswerTool()
        self.system_prompt = self.initialize_system_prompt()
        self.input_messages = None
        self.task = None
        self.memory = AgentMemory(self.system_prompt)
        self.logger = AgentLogger(level=verbosity_level)
        self.prompts_type = prompts_type
        self.planning = None  # To be initialized in subclasses

    @property
    def logs(self):
        logger.warning(
            "The 'logs' attribute is deprecated and will soon be removed. Please use 'self.memory.steps' instead."
        )
        return [self.memory.system_prompt] + self.memory.steps

    def initialize_system_prompt(self):
        """To be implemented in child classes"""
        pass

    def write_memory_to_messages(
            self,
            memory_steps: Optional[List[ActionStep]] = None,
            summary_mode: Optional[bool] = False,
            include_system_prompt: Optional[bool] = True,
    ) -> List[Dict[str, str]]:
        """
        Reads past llm_outputs, actions, and observations or errors from the memory into a series of messages
        that can be used as input to the LLM. Adds a number of keywords (such as PLAN, error, etc) to help
        the LLM.
        
        Args:
            memory_steps: Optional list of memory steps to convert
            summary_mode: Whether to use summary mode
            include_system_prompt: Whether to include system prompt in output (default: True)
        """
        messages = []
        if include_system_prompt:
            messages = self.memory.system_prompt.to_messages(summary_mode=summary_mode)
        for memory_step in memory_steps if memory_steps else self.memory.steps:
            messages.extend(memory_step.to_messages(summary_mode=summary_mode))
        return messages

    def visualize(self):
        """Creates a rich tree visualization of the agent's structure."""
        self.logger.visualize_agent_tree(self)

    def provide_final_answer(self, task: str) -> Tuple[str, str]:
        """
        Provide the final answer to the task, based on the logs of the agent's interactions.

        Args:
            task (`str`): Task to perform.
            images (`list[str]`, *optional*): Paths to image(s).

        Returns:
            `str`: Final answer to the task.
        """
        messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": self.prompt_templates["final_answer"]["pre_messages"],
                    }
                ],
            }
        ]
        messages += self.write_memory_to_messages()[1:]
        messages += [
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": populate_template(
                            self.prompt_templates["final_answer"]["post_messages"], variables={"task": task}
                        ),
                    }
                ],
            }
        ]
        try:
            chat_message: ChatMessage = self.model(messages)
            final_answer = chat_message.content
            final_cot_think = chat_message.reasoning_content
            final_answer_json = json_repair.loads(final_answer)
            final_answer_think, final_answer_res = final_answer_json.get("think", ""), final_answer_json.get("answer", "")
            return final_cot_think, final_answer_think, final_answer_res
        
        except Exception as e:
            return None, None, f"Error in generating final LLM output:\n{e}"

    def execute_tool_call(self, tool_name: str, arguments: Union[Dict[str, str], str]) -> Any:
        """
        Execute tool with the provided input and returns the result.
        This method replaces arguments with the actual values from the state if they refer to state variables.

        Args:
            tool_name (`str`): Name of the Tool to execute (should be one from self.tools).
            arguments (Dict[str, str]): Arguments passed to the Tool.
        """
        tool = self.tools.get(tool_name)
        managed_agent = self.managed_agents.get(tool_name)

        if tool is None and managed_agent is None:
            known_names = list(dict.fromkeys([*self.tools.keys(), *self.managed_agents.keys()]))
            error_msg = f"Unknown tool {tool_name}, should be instead one of {known_names}."
            raise AgentExecutionError(error_msg, self.logger)

        try:
            if isinstance(arguments, str):
                if tool is not None:
                    observation = tool.__call__(arguments, sanitize_inputs_outputs=True)
                else:
                    observation = managed_agent.run(arguments)
            elif isinstance(arguments, dict):
                for key, value in arguments.items():
                    if isinstance(value, str) and value in self.state:
                        arguments[key] = self.state[value]
                if tool is not None:
                    observation = tool.__call__(**arguments, sanitize_inputs_outputs=True)
                else:
                    observation = managed_agent.run(arguments.get("task", str(arguments)))
            else:
                error_msg = f"Arguments passed to tool should be a dict or string: got a {type(arguments)}."
                raise AgentExecutionError(error_msg, self.logger)
            return observation
        except Exception as e:
            if tool_name in self.tools:
                error_msg = (
                    f"Error when executing tool {tool_name} with arguments {arguments}: {type(e).__name__}: {e}\nYou should only use this tool with a correct input.\n"
                    f"As a reminder, this tool's description is the following: '{tool.description}'.\nIt takes inputs: {tool.inputs} and returns output type {tool.output_type}"
                )
                raise AgentExecutionError(error_msg, self.logger)
            elif tool_name in self.managed_agents:
                error_msg = (
                    f"Error in calling team member: {e}\nYou should only ask this team member with a correct request.\n"
                    f"As a reminder, this team member's description is the following:\n{managed_agent}"
                )
                raise AgentExecutionError(error_msg, self.logger)

    def step(self, memory_step: ActionStep) -> Union[None, Any]:
        """To be implemented in children classes. Should return either None if the step is not final."""
        pass

    def run(
            self,
            task: str,
            stream: bool = False,
            reset: bool = True,
            answer: Optional[str] = None,
            images: Optional[List[str]] = None,
            additional_args: Optional[Dict] = None,
    ):
        self.task = task
        self.answer = answer

        self.system_prompt = self.initialize_system_prompt()
        self.memory.system_prompt = SystemPromptStep(system_prompt=self.system_prompt)

        self.logger.log_task(
            content=self.task.strip(),
            subtitle=f"{type(self.model).__name__} - {(self.model.model_id if hasattr(self.model, 'model_id') else '')}",
            level=LogLevel.INFO,
            title=self.name if hasattr(self, "name") else None,
        )

        self.memory.steps.append(TaskStep(task=self.task, task_images=images))

        if stream:
            # The steps are returned as they are executed through a generator to iterate on.
            return self._run(task=self.task, images=images)
        # Outputs are returned only at the end as a string. We only look at the last step
        return deque(self._run(task=self.task, images=images), maxlen=1)[0]

    def _run(self, task: str, images: List[str] | None = None) -> Generator[ActionStep | AgentType, None, None]:
        """
        Run the agent in streaming mode and returns a generator of all the steps.

        Args:
            task (`str`): Task to perform.
            images (`list[str]`): Paths to image(s).
        """
        pass
    def planning_step(self, task) -> PlanningStep:
        """
        Used periodically by the agent to plan the next steps to reach the objective.

        Args:
            task (`str`): Task to perform.
            is_first_step (`bool`): If this step is not the first one, the plan should be an update over a previous plan.
            step (`int`): The number of the current step, used as an indication for the LLM.
        """
        if self.planning is not None:
            planning_step = self.planning.topology_initialize(task)
            if hasattr(self.model, "get_token_counts"):
                counts = self.model.get_token_counts()
                planning_step.input_tokens = counts.get("input_token_count", 0) or 0
                planning_step.output_tokens = counts.get("output_token_count", 0) or 0
            return planning_step

        # # Fallback to default implementation
        # input_messages = [
        #     {
        #         "role": MessageRole.SYSTEM,
        #         "content": [
        #             {
        #                 "type": "text",
        #                 "text": populate_template(
        #                     self.prompt_templates["planning"]["initial_plan"],
        #                     variables={
        #                         "tools": self.tools,
        #                     },
        #                 ),
        #             }
        #         ],
        #     },
        # ]
        # task_messages = [{
        #     "role": MessageRole.USER,
        #     "content": [{"type": "text", "text": populate_template(self.prompt_templates["planning"]["task_input"], variables={"task": task})}],
        # }]
        # chat_message_plan: ChatMessage = self.model(input_messages + task_messages)
        # think_content = chat_message_plan.reasoning_content
        # plans = chat_message_plan.content
        # plans_think, plans_answer = "", plans

        # final_plan_redaction = textwrap.dedent(
        #     f"""Here is the plan of action that I will follow to solve the task:\n```\n{plans_answer}\n```\n"""
        # )

        # self.logger.log(
        #     Rule("[bold]Initial plan", style="orange"),
        #     Text(final_plan_redaction),
        #     level=LogLevel.INFO,
        # )

        # self.memory.steps.append(
        #     PlanningStep(
        #         model_input_messages=input_messages,
        #         plan=plans_answer,
        #         plan_think=plans_think,
        #         plan_reasoning=think_content,

        #     )
        # )

        # return PlanningStep(
        #     model_input_messages=input_messages,
        #     plan=plans_answer,
        #     plan_think=plans_think,
        #     plan_reasoning=think_content,
        # )


    def summary_step(self, task, step: int) -> SummaryStep:
        """
        Used periodically by the agent to summary the steps to reach the objective.

        Args:
            task (`str`): Task to perform.
            step (`int`): The number of the current step, used as an indication for the LLM.
        """
        if self.planning is not None:
            summary_step = self.planning.adaptation(task, step, self.write_memory_to_messages)
            if hasattr(self.model, "get_token_counts"):
                counts = self.model.get_token_counts()
                summary_step.input_tokens = counts.get("input_token_count", 0) or 0
                summary_step.output_tokens = counts.get("output_token_count", 0) or 0
            return summary_step

        # # Fallback to default implementation
        # memory_messages = self.write_memory_to_messages()[1:]

        # update_pre_messages = {
        #     "role": MessageRole.SYSTEM,
        #     "content": [{"type": "text", "text": self.prompt_templates["summary"]["update_pre_messages"]}],
        # }
        # update_post_messages = {
        #     "role": MessageRole.USER,
        #     "content": [{"type": "text", "text": self.prompt_templates["summary"]["update_post_messages"]}],
        # }
        # input_messages = [update_pre_messages] + memory_messages + [update_post_messages]
        # chat_message_summary: ChatMessage = self.model(input_messages)

        # summary_answer = chat_message_summary.content
        # summary_cot_content = chat_message_summary.reasoning_content


        # final_summary_redaction = textwrap.dedent(
        #     f"""
        #     Here is my summary of action to solve the task:
        #     ```
        #     {summary_answer}
        #     ```"""
        # )
        # self.memory.steps.append(
        #     SummaryStep(
        #         model_input_messages=input_messages,
        #         summary=summary_answer,
        #         summary_reasoning=summary_cot_content,
        #     )
        # )
        # self.logger.log(
        #     Rule("[bold]Summary", style="orange"),
        #     Text(final_summary_redaction),
        #     level=LogLevel.INFO,
        # )
        # return SummaryStep(
        #     model_input_messages=input_messages,
        #     summary=summary_answer,
        #     summary_reasoning=summary_cot_content,
        # )


    def to_dict(self) -> Dict[str, Any]:
        """Converts agent into a dictionary."""

        tool_dicts = [tool.to_dict() for tool in self.tools.values()]
        tool_requirements = {req for tool in self.tools.values() for req in tool.to_dict()["requirements"]}
        managed_agents_requirements = {
            req for managed_agent in self.managed_agents.values() for req in managed_agent.to_dict()["requirements"]
        }
        requirements = tool_requirements | managed_agents_requirements
        if hasattr(self, "authorized_imports"):
            BASE_BUILTIN_MODULES = [
                "collections",
                "datetime",
                "itertools",
                "math",
                "queue",
                "random",
                "re",
                "stat",
                "statistics",
                "time",
                "unicodedata",
            ]
            requirements.update(
                {package.split(".")[0] for package in self.authorized_imports if package not in BASE_BUILTIN_MODULES}
            )

        agent_dict = {
            "tools": tool_dicts,
            "model": {
                "class": self.model.__class__.__name__,
                "data": self.model.to_dict(),
            },
            "managed_agents": {
                managed_agent.name: managed_agent.__class__.__name__ for managed_agent in self.managed_agents.values()
            },
            "prompt_templates": self.prompt_templates,
            "max_steps": self.max_steps,
            "verbosity_level": int(self.logger.level),
            "grammar": self.grammar,
            "name": self.name,
            "description": self.description,
            "requirements": list(requirements),
        }
        return agent_dict



class ToolCallingAgent(MultiStepAgent):

    def __init__(
            self,
            tools: List[Tool],
            model: Callable[[List[Dict[str, str]]], ChatMessage],
            prompt_templates: Optional[PromptTemplates] = None,
            summary_interval: Optional[int] = None,
            prompts_type: Optional[str] = None,
            memory_provider=None,
            planning_system: Optional[str] = "flash_searcher",
            planning_class: Optional[type[Any]] = None,
            execute_model: Optional[Callable[[List[Dict[str, str]]], ChatMessage]] = None,
            project_root: Optional[Path] = None,
            max_tool_calls_per_step: Optional[int] = None,
            **kwargs,
    ):
        super().__init__(
            tools=tools,
            model=model,
            prompt_templates=prompt_templates,
            summary_interval=summary_interval,
            prompts_type=prompts_type,
            **kwargs,
        )
        self.max_tool_calls_per_step = max_tool_calls_per_step
        # Use execute_model for action steps if provided, otherwise fallback to planning model
        self.execute_model = execute_model if execute_model is not None else model
        # If prompts_type is not specified, use planning_system name as default
        if prompts_type is None:
            prompts_type = planning_system

        try:
            project_root = project_root or Path(__file__).resolve().parents[1]
            if prompt_templates is None:
                self.prompt_templates = load_prompt_templates(
                    project_root=project_root,
                    prompts_type=prompts_type,
                )
            else:
                self.prompt_templates = prompt_templates
            try:
                self.planning_prompt_templates = load_planning_prompt_templates(
                    project_root=project_root,
                    prompts_type=planning_system,
                )
            except FileNotFoundError:
                self.planning_prompt_templates = self.prompt_templates
        except FileNotFoundError as exc:
            raise AgentError(str(exc), self.logger) from exc
        except yaml.YAMLError as e:
            raise AgentError(f"YAML parse error: {e}", self.logger)
        except ValueError as e:
            raise AgentError(f"Invalid prompt templates: {e}", self.logger)
        self.summary_interval = summary_interval
        self.memory_provider = memory_provider

        # Initialize planning module based on planning_system parameter
        if planning_class is None:
            try:
                planning_class = get_planning_class(planning_system)
            except ValueError as exc:
                raise AgentError(str(exc), self.logger) from exc
            except ModuleNotFoundError as exc:
                raise AgentError(
                    f"Failed to import planning module for '{planning_system}': {exc}",
                    self.logger,
                ) from exc
            except Exception as exc:
                raise AgentError(
                    f"Unexpected planning initialization error for '{planning_system}': {exc}",
                    self.logger,
                ) from exc
        self.planning = planning_class(
            model=self.model,
            tools=self.tools,
            prompt_templates=self.planning_prompt_templates,
            memory=self.memory,
            logger=self.logger
        )

    def initialize_system_prompt(self) -> str:
        system_prompt = populate_template(
            self.prompt_templates["system_prompt"],
            variables={"tools": self.tools},
        )
        return system_prompt

    def _terminal_tool_answer(
        self,
        tool_name: str,
        tool_arguments: Any,
        observation: Any,
    ) -> Any:
        tool = self.tools.get(tool_name)
        if tool is None or not getattr(tool, "terminal_tool", False):
            return None

        predicate = getattr(tool, "is_terminal_observation", None)
        if callable(predicate) and not predicate(observation):
            return None

        answer_getter = getattr(tool, "terminal_answer", None)
        if callable(answer_getter):
            return answer_getter(tool_arguments, observation)
        return str(observation).strip()

    def _get_memory_guidance(self, memory_status, step_number: int = 0) -> Optional[str]:
        if not self.memory_provider:
            return None

        try:
            memory_types = harness_runtime.get_memory_types_module(memory_provider=self.memory_provider)
            MemoryRequest = memory_types.MemoryRequest
            MemoryItemType = memory_types.MemoryItemType

            current_context = self._format_current_context()
            memory_request = MemoryRequest(
                query=self.task if hasattr(self, 'task') else "",
                context=current_context,
                status=memory_status,
                additional_params={"step_number": step_number}
            )

            memory_response = self.memory_provider.provide_memory(memory_request)

            if memory_response.memories:
                text_contents = []
                tools_without_description = []

                for memory_item in memory_response.memories:
                    if memory_item.type == MemoryItemType.TEXT:
                        if isinstance(memory_item.content, str) and memory_item.content:
                            text_contents.append(memory_item.content)
                    elif memory_item.type == MemoryItemType.API:
                        tool = None
                        tool_name = None
                        tool_description = None
                        has_text_content = False

                        if memory_item.metadata and 'wrapped_tool' in memory_item.metadata:
                            tool = memory_item.metadata['wrapped_tool']
                            tool_name = memory_item.metadata.get('skill_name', getattr(tool, 'name', None))
                            tool_description = memory_item.metadata.get('description', getattr(tool, 'description', ''))
                            if isinstance(memory_item.content, str) and memory_item.content:
                                text_contents.append(memory_item.content)
                                has_text_content = True
                        elif hasattr(memory_item.content, 'name') and hasattr(memory_item.content, 'description'):
                            tool = memory_item.content
                            tool_name = tool.name
                            tool_description = tool.description

                        if tool and tool_name:
                            if tool_name not in self.tools:
                                self.tools[tool_name] = tool
                                logger.info(f"Memory system added new tool: {tool_name}")
                                if not has_text_content:
                                    desc_text = tool_description or "No description available"
                                    tools_without_description.append(f"- {tool_name}: {desc_text}")

                combined_parts = []
                if text_contents:
                    combined_parts.extend(text_contents)

                if tools_without_description:
                    tools_section = (
                        "\n[New Tools Added by Memory System]\n"
                        + "\n".join(tools_without_description)
                        + "\nYou can now use these tools to help solve the task."
                    )
                    combined_parts.append(tools_section)

                if combined_parts:
                    return "\n".join(combined_parts)

        except Exception as e:
            logger.warning(f"Memory provider error: {e}")

        return None

    def _format_current_context(self) -> str:
        try:
            messages = self.write_memory_to_messages()
            context_parts = []

            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", [])

                if isinstance(content, list):
                    text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    text = " ".join(text_parts)
                else:
                    text = str(content)

                if text:
                    context_parts.append(f"{role}: {text}")

            return "\n".join(context_parts)
        except Exception as e:
            logger.warning(f"Error formatting context: {e}")
            return ""

    def planning_step(self, task) -> PlanningStep:
        if self.planning is not None:
            memory_guidance_content = None
            if self.memory_provider:
                try:
                    memory_types = harness_runtime.get_memory_types_module(memory_provider=self.memory_provider)
                    MemoryStatus = memory_types.MemoryStatus
                    memory_guidance_content = self._get_memory_guidance(MemoryStatus.BEGIN, step_number=0)
                except Exception as e:
                    logger.warning(f"Memory provider error: {e}")
                    memory_guidance_content = None

            if hasattr(self.planning, "memory_guidance"):
                self.planning.memory_guidance = memory_guidance_content

            planning_step = self.planning.topology_initialize(task)
            planning_step.memory_guidance = memory_guidance_content
            if hasattr(self.model, "get_token_counts"):
                counts = self.model.get_token_counts()
                planning_step.input_tokens = counts.get("input_token_count", 0) or 0
                planning_step.output_tokens = counts.get("output_token_count", 0) or 0
            return planning_step

        return super().planning_step(task)

    def _run(self, task: str, images: List[str] | None = None) -> Generator[ActionStep | AgentType, None, None]:
        """
        Run the agent in streaming mode and returns a generator of all the steps.

        Args:
            task (`str`): Task to perform.
            images (`list[str]`): Paths to image(s).
        """
        final_answer = None
        self.step_number = 0
        while final_answer is None and self.step_number <= self.max_steps:
            step_start_time = time.time()
            memory_step = ActionStep(
                step_number=self.step_number,
                start_time=step_start_time,
                observations_images=images,
            )
            try:
                if self.step_number == 0:
                    self.planning_step(task)
                    self.step_number += 1
                elif self.summary_interval is not None and self.step_number % self.summary_interval == 0:
                    self.summary_step(
                        task,
                        step=self.step_number,
                    )
                    self.step_number += 1
                self.logger.log_rule(f"Step {self.step_number}", level=LogLevel.INFO)
                final_answer = self.step(memory_step)
            except AgentError as e:
                memory_step.error = e
                raise
            finally:
                memory_step.end_time = time.time()
                memory_step.duration = memory_step.end_time - step_start_time
                self.memory.steps.append(memory_step)
                self.step_number += 1
                yield memory_step

        if final_answer is None and self.step_number > self.max_steps:
            error_message = "Reached max steps."
            step_start_time = time.time()
            cot_think, final_think, final_answer = self.provide_final_answer(task)

            final_memory_step = ActionStep(
                step_number=self.step_number, error=AgentMaxStepsError(error_message, self.logger)
            )

            final_memory_step.action_reasoning = cot_think
            final_memory_step.action_think = final_think
            final_memory_step.action_output = final_answer
            final_memory_step.end_time = time.time()
            final_memory_step.duration = memory_step.end_time - step_start_time
            self.memory.steps.append(final_memory_step)

            yield final_memory_step

        yield handle_agent_output_types(final_answer)

    def reformulate_tool_fuctions(self, tool_list: List[Tool]) -> str:
        json_schema_list = []
        for tool in tool_list:
            required = []
            properties = deepcopy(tool.inputs)
            for key, value in properties.items():
                if value["type"] == "any":
                    value["type"] = "string"
                if not ("nullable" in value and value["nullable"]):
                    required.append(key)
            json_schema_list.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "properties": properties,
                    "required": required,
                }
            })
        return json.dumps(json_schema_list, indent=2, ensure_ascii=False)
    

    def step(self, memory_step: ActionStep, memory_messages=None) -> Union[None, Any]:
        memory_messages = self.write_memory_to_messages() if memory_messages is None else memory_messages
        self.input_messages = memory_messages

        if self.memory_provider:
            try:
                memory_types = harness_runtime.get_memory_types_module(memory_provider=self.memory_provider)
                MemoryStatus = memory_types.MemoryStatus
                memory_guidance_content = self._get_memory_guidance(MemoryStatus.IN, step_number=self.step_number)
            except Exception as e:
                logger.warning(f"Memory provider error: {e}")
                memory_guidance_content = None

            if memory_guidance_content:
                formatted_memory = (
                    "---Memory System Guidance---\n"
                    f"{memory_guidance_content}\n"
                    "---End Memory---"
                )
                memory_message = {
                    "role": MessageRole.USER,
                    "content": [{"type": "text", "text": formatted_memory}]
                }
                memory_messages = memory_messages + [memory_message]
                memory_step.memory_guidance = memory_guidance_content

        # Add new step in logs
        memory_step.model_input_messages = memory_messages.copy()

        instruction_message = [{
            "role": MessageRole.USER,
            "content": [{
                "type": "text",
                "text": populate_template(
                    self.prompt_templates["step"]["pre_messages"],
                    variables={
                        "tool_functions_json": self.reformulate_tool_fuctions(list(self.tools.values())),
                        "task": self.task
                    }
                )
            }]
        }]
        
        try:
            # Use execute_model for action steps
            model_message: ChatMessage = self.execute_model(
                memory_messages + instruction_message,
            )
            if hasattr(self.execute_model, "get_token_counts"):
                counts = self.execute_model.get_token_counts()
                memory_step.input_tokens = counts.get("input_token_count", 0) or 0
                memory_step.output_tokens = counts.get("output_token_count", 0) or 0
            
            memory_step.model_output_messages = model_message

            raw_content = model_message.content
            if isinstance(raw_content, str):
                try:
                    content_dict = json_repair.loads(raw_content)
                except Exception as e:
                    content_dict = []
                    raise Exception(f"Unsupported step output: {type(raw_content)}: {e}")
            else:
                content_dict = raw_content

            if isinstance(content_dict, list):
                first_item = content_dict[0] if content_dict else None
                if isinstance(first_item, dict) and "tools" in first_item:
                    answer_data = first_item.get("tools", [])
                    memory_step.action_think = first_item.get("think", "No 'think' field in response")
                else:
                    answer_data = content_dict
                    memory_step.action_think = "No 'think' field in response"
            elif isinstance(content_dict, dict):
                if "tools" in content_dict:
                    answer_data = content_dict.get("tools", None)
                elif "name" in content_dict and (
                    "arguments" in content_dict or "function" in content_dict
                ):
                    answer_data = [content_dict]
                elif "tool" in content_dict and isinstance(content_dict["tool"], dict):
                    answer_data = [content_dict["tool"]]
                elif "tool_calls" in content_dict:
                    answer_data = content_dict.get("tool_calls", None)
                else:
                    answer_data = None
                memory_step.action_think = content_dict.get("think", "No 'think' field in response")
            else:
                answer_data = "No fuction calling in response"
                memory_step.action_think = "No 'think' field in response"

            if (
                answer_data is None
                and isinstance(content_dict, dict)
                and "final_answer" in self.tools
            ):
                for answer_key in ("answer", "final_answer"):
                    answer_value = content_dict.get(answer_key)
                    if isinstance(answer_value, str) and answer_value.strip():
                        answer_data = [
                            {
                                "name": "final_answer",
                                "arguments": {"answer": answer_value.strip()},
                            }
                        ]
                        break

            # Normalize tool calls from potentially malformed model outputs.
            if isinstance(answer_data, list):
                pending_tool_calls = list(answer_data)
            elif isinstance(answer_data, dict):
                pending_tool_calls = [answer_data]
            elif answer_data is None:
                pending_tool_calls = []
            else:
                pending_tool_calls = [answer_data]

            tool_calls_list = []
            while pending_tool_calls:
                item = pending_tool_calls.pop(0)

                if isinstance(item, list):
                    pending_tool_calls = item + pending_tool_calls
                    continue

                if isinstance(item, str):
                    try:
                        parsed_item = json_repair.loads(item)
                    except Exception:
                        logger.warning(f"Skip malformed tool call string: {item[:200]}")
                        continue
                    pending_tool_calls = [parsed_item] + pending_tool_calls
                    continue

                if not isinstance(item, dict):
                    logger.warning(f"Skip malformed tool call item type: {type(item)}")
                    continue

                # Some models wrap calls in {"tools": [...]} again.
                if "tools" in item:
                    nested_tools = item.get("tools")
                    if isinstance(nested_tools, list):
                        pending_tool_calls = nested_tools + pending_tool_calls
                    elif nested_tools is not None:
                        pending_tool_calls = [nested_tools] + pending_tool_calls
                    continue

                # Some APIs return {"function": {"name": ..., "arguments": ...}}
                if "function" in item and isinstance(item["function"], dict):
                    function_data = item["function"]
                    item = {
                        "name": item.get("name") or function_data.get("name", ""),
                        "arguments": item.get("arguments", function_data.get("arguments", {})),
                        "id": item.get("id", ""),
                    }

                if not isinstance(item.get("name"), str) or not item.get("name"):
                    logger.warning(f"Skip tool call without valid name: {item}")
                    continue

                tool_calls_list.append(item)

            if not tool_calls_list and getattr(model_message, "tool_calls", None):
                for raw_tool_call in model_message.tool_calls:
                    function_data = getattr(raw_tool_call, "function", None)
                    if function_data is None:
                        continue
                    tool_name = getattr(function_data, "name", "")
                    if not isinstance(tool_name, str) or not tool_name:
                        continue
                    tool_arguments = getattr(function_data, "arguments", {})
                    if isinstance(tool_arguments, str):
                        try:
                            tool_arguments = json_repair.loads(tool_arguments)
                        except Exception:
                            pass
                    tool_calls_list.append(
                        {
                            "name": tool_name,
                            "arguments": tool_arguments,
                            "id": getattr(raw_tool_call, "id", ""),
                        }
                    )

            max_tool_calls = getattr(self, "max_tool_calls_per_step", None)
            if (
                isinstance(max_tool_calls, int)
                and max_tool_calls > 0
                and len(tool_calls_list) > max_tool_calls
            ):
                logger.warning(
                    "Truncating tool calls from %s to %s for this step.",
                    len(tool_calls_list),
                    max_tool_calls,
                )
                tool_calls_list = tool_calls_list[:max_tool_calls]

            memory_step.tool_calls = []
            final_answer_value = None
            observations = []
            
            # Process each tool call

            self.logger.log(
                Panel(Text(f"Function calling number: {len(tool_calls_list)} calls: {str(tool_calls_list)}")),
                level=LogLevel.INFO,
            )

            # Parallel tool execution. (Please ensure that the tool implement has sufficient concurrency!)
             # ================ Parallel Tool Execution ================== #
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = []
                tool_info_list = []
                
                for idx, tool_call in enumerate(tool_calls_list):
                    if not isinstance(tool_call, dict):
                        logger.warning(f"Skip non-dict tool call at index {idx}: {tool_call}")
                        continue

                    tool_name = tool_call.get("name", "")
                    tool_arguments = tool_call.get("arguments", {})
                    tool_call_id = tool_call.get("id", "")

                    if isinstance(tool_arguments, str):
                        try:
                            tool_arguments = json_repair.loads(tool_arguments)
                        except Exception:
                            # Keep raw string if it is not valid JSON.
                            pass
                    
                    tool_call_obj = ToolCall(name=tool_name, arguments=tool_arguments, id=tool_call_id)
                    memory_step.tool_calls.append(tool_call_obj)
                    
                    self.logger.log(
                        Panel(Text(f"Calling tool: '{tool_name}' with arguments: {tool_arguments}")),
                        level=LogLevel.INFO,
                    )
                    
                    if tool_name == "final_answer":
                        if isinstance(tool_arguments, dict):
                            answer = tool_arguments.get("answer", tool_arguments)
                        else:
                            answer = tool_arguments
                        
                        final_answer_value = answer
                        self.logger.log(
                            Text(f"Final answer: {final_answer_value}", style=f"bold {YELLOW_HEX}"),
                            level=LogLevel.INFO,
                        )
                        observations.append(str(final_answer_value))
                        break

                    future = executor.submit(self.execute_tool_call, tool_name, tool_arguments)
                    futures.append((idx, future, tool_name, tool_arguments))
                    tool_info_list.append((idx, tool_name, tool_arguments))
                
                if final_answer_value is not None:
                    memory_step.observations = "\n\n".join(observations) if observations else "No observations"
                    return final_answer_value
                
                if futures:
                    futures.sort(key=lambda x: x[0])
                    
                    for idx, future, tool_name, tool_arguments in futures:
                        try:
                            observation = future.result()
                            if isinstance(observation, dict) and "report" in observation:
                                if memory_step.subagent_trajectories is None:
                                    memory_step.subagent_trajectories = {}
                                existing_entries = memory_step.subagent_trajectories.setdefault(tool_name, [])
                                if isinstance(existing_entries, list):
                                    existing_entries.append(observation)
                                else:
                                    memory_step.subagent_trajectories[tool_name] = [observation]
                                updated_information = str(observation.get("report", "")).strip()
                            else:
                                updated_information = str(observation).strip()
                            
                            observations.append(
                                f"Results for tool call '{tool_name}' with arguments '{tool_arguments}':\n{updated_information}"
                            )
                            self.logger.log(
                                f"Observations: {updated_information.replace('[', '|')}",
                                level=LogLevel.INFO,
                            )
                            terminal_answer = self._terminal_tool_answer(
                                tool_name, tool_arguments, observation
                            )
                            if terminal_answer is not None:
                                final_answer_value = terminal_answer
                                self.logger.log(
                                    Text(
                                        f"Terminal tool '{tool_name}' completed task: {final_answer_value}",
                                        style=f"bold {YELLOW_HEX}",
                                    ),
                                    level=LogLevel.INFO,
                                )
                        except Exception as e:
                            observation = str(e)
                            self.logger.error(f"Tool execution error: {observation}")
                            observations.append(
                                f"Error for tool call '{tool_name}' with arguments '{tool_arguments}':\n{observation}"
                            )
            memory_step.observations = "\n\n".join(observations) if observations else "No observations"
            # ================ Parallel Tool Execution ================== #

            # ================ Sequence Tool Execution ================== #
            # for tool_call in tool_calls_list:
            #     tool_name = tool_call.get("name", "")
            #     tool_arguments = tool_call.get("arguments", {})
            #     tool_call_id = tool_call.get("id", "")
                
            #     # Create tool call object
            #     tool_call_obj = ToolCall(name=tool_name, arguments=tool_arguments, id=tool_call_id)
            #     memory_step.tool_calls.append(tool_call_obj)
                
            #     self.logger.log(
            #         Panel(Text(f"Calling tool: '{tool_name}' with arguments: {tool_arguments}")),
            #         level=LogLevel.INFO,
            #     )
            #     if tool_name == "final_answer":
            #         if isinstance(tool_arguments, dict):
            #             answer = tool_arguments.get("answer", tool_arguments)
            #         else:
            #             answer = tool_arguments
                    
            #         final_answer_value = answer
            #         self.logger.log(
            #             Text(f"Final answer: {final_answer_value}", style=f"bold {YELLOW_HEX}"),
            #             level=LogLevel.INFO,
            #         )
                
            #         observations.append(str(final_answer_value))
            #         break

            #     try:
            #         observation = self.execute_tool_call(tool_name, tool_arguments)
            #     except Exception as e:
            #         observation = str(e)
            #         self.logger.error(f"Tool execution error: {str(e)}")

            #     updated_information = str(observation).strip()
                
            #     observations.append(f"Results for tool call '{tool_name}' with arguments '{tool_arguments}':\n{updated_information}")
            #     self.logger.log(
            #         f"Observations: {updated_information.replace('[', '|')}",
            #         level=LogLevel.INFO,
            #     )

            # # Set step observations
            # memory_step.observations = "\n\n".join(observations) if observations else "No observations"
            # ============== Sequence Tool Execution ================ #
            
            # Handle final answer if present
            if final_answer_value is not None:
                return final_answer_value
            
            return None

        except Exception as e:
            raise AgentGenerationError(f"Error in generating tool call with model:\n{e}", self.logger) from e


