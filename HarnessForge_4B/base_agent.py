#!/usr/bin/env python
# coding=utf-8
# Copyright 2025 The OPPO Inc. PersonalAI team. All rights reserved.
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

from dotenv import load_dotenv
from utils import safe_json_loads

from pathlib import Path
from typing import Any

import harness_runtime  # noqa: F401

from Agents.agents import ToolCallingAgent
from Agents.memory import ActionStep, PlanningStep, TaskStep, SummaryStep
from Agents.tools import Tool
from Agents.tools import (
    VectorSimilarityRetrieve, Reasoning, Process, EndProcess,
    DeleteMemory, Executor, Refine
)
from module_action.base_action import ActionContext
from module_action.registry import get_action_provider

try:
    from module_action.search_tools import WebSearchTool, CrawlPageTool
except Exception:
    class WebSearchTool(Tool):
        name = "web_search"
        description = "Unavailable placeholder for WebSearchTool."
        inputs: dict[str, dict[str, str]] = {"query": {"type": "string", "description": "Search query"}}
        output_type = "string"

        def __init__(self, *args, **kwargs):
            super().__init__()

        def forward(self, query):
            raise RuntimeError(
                "WebSearchTool is unavailable. Please add module_action.search_tools.WebSearchTool."
            )

    class CrawlPageTool(Tool):
        name = "crawl_page"
        description = "Unavailable placeholder for CrawlPageTool."
        inputs: dict[str, dict[str, Any]] = {
            "url": {"type": "string", "description": "Target URL"},
            "query": {"type": "string", "description": "Question or extraction target on the page", "nullable": True},
        }
        output_type = "string"

        def __init__(self, *args, **kwargs):
            super().__init__()

        def forward(self, url, query=None):
            raise RuntimeError(
                "CrawlPageTool is unavailable. Please add module_action.search_tools.CrawlPageTool."
            )

try:
    from module_action.mm_tools import (
        VisualInspectorTool,
        AudioInspectorTool,
        TextInspectorTool,
    )
except Exception:
    class VisualInspectorTool(Tool):
        name = "inspect_file_as_image"
        description = "Unavailable placeholder for VisualInspectorTool."
        inputs: dict[str, dict[str, Any]] = {
            "file_path": {"type": "string", "description": "Image file path"},
            "question": {"type": "string", "description": "Question about image", "nullable": True},
        }
        output_type = "string"

        def __init__(self, *args, **kwargs):
            super().__init__()

        def forward(self, file_path, question=None):
            raise RuntimeError(
                "VisualInspectorTool is unavailable. Please add module_action.mm_tools.VisualInspectorTool."
            )

    class TextInspectorTool(Tool):
        name = "inspect_file_as_text"
        description = "Unavailable placeholder for TextInspectorTool."
        inputs: dict[str, dict[str, Any]] = {
            "file_path": {"type": "string", "description": "Text file path"},
            "question": {"type": "string", "description": "Question about text", "nullable": True},
        }
        output_type = "string"

        def __init__(self, *args, **kwargs):
            super().__init__()

        def forward(self, file_path, question=None):
            raise RuntimeError(
                "TextInspectorTool is unavailable. Please add module_action.mm_tools.TextInspectorTool."
            )

    class AudioInspectorTool(Tool):
        name = "inspect_file_as_audio"
        description = "Unavailable placeholder for AudioInspectorTool."
        inputs: dict[str, dict[str, Any]] = {
            "file_path": {"type": "string", "description": "Audio file path"},
            "question": {"type": "string", "description": "Question about audio", "nullable": True},
        }
        output_type = "string"

        def __init__(self, *args, **kwargs):
            super().__init__()

        def forward(self, file_path, question=None):
            raise RuntimeError(
                "AudioInspectorTool is unavailable. Please add module_action.mm_tools.AudioInspectorTool."
            )

try:
    from module_action.cosight_tool import ExpertParallelTool, CAMVTool
except Exception:
    class ExpertParallelTool(Tool):
        name = "expert_parallel"
        description = "Unavailable placeholder for ExpertParallelTool."
        inputs: dict[str, dict[str, Any]] = {
            "task": {"type": "string", "description": "Task"},
            "num_expert": {"type": "integer", "description": "Number of experts"},
        }
        output_type = "string"

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.agents = kwargs.get("agents", [])
            self.prompt_templates = None

        def set_prompt_templates(self, prompt_templates):
            self.prompt_templates = prompt_templates

        def forward(self, task, num_expert):
            raise RuntimeError(
                "ExpertParallelTool is unavailable. Please add module_action.cosight_tool.ExpertParallelTool."
            )

    class CAMVTool(Tool):
        name = "camv"
        description = "Unavailable placeholder for CAMVTool."
        inputs: dict[str, dict[str, Any]] = {
            "task": {"type": "string", "description": "Task"},
            "expert_packages": {"type": "string", "description": "Serialized expert findings"},
        }
        output_type = "string"

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.prompt_templates = None

        def set_prompt_templates(self, prompt_templates):
            self.prompt_templates = prompt_templates

        def forward(self, task, expert_packages):
            raise RuntimeError(
                "CAMVTool is unavailable. Please add module_action.cosight_tool.CAMVTool."
            )

load_dotenv(override=True)

class BaseAgent:
    def __init__(self, model):
        self.model = model
        self.agent_fn = None

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)

    def capture_trajectory(self, ):
        if not hasattr(self, 'agent_fn'):
            raise ValueError("[capture_trajectory] agent_fn is not defined.")
        if not isinstance(self.agent_fn, ToolCallingAgent):
            raise ValueError("[capture_trajectory] agent_fn must be an instance of ToolCallingAgent.")
        trajectory = []
        for step_num, step in enumerate(self.agent_fn.memory.steps):
            if isinstance(step, TaskStep):
                continue
            elif isinstance(step, PlanningStep):
                traj = {
                    "name": "plan",
                    "value": step.plan,
                    "think": step.plan_think,
                    "cot_think": step.plan_reasoning,
                    "memory_guidance": getattr(step, "memory_guidance", None),
                }
                trajectory.append(traj)
            elif isinstance(step, SummaryStep):
                traj = {"name": "summary", "value": step.summary, "cot_think": step.summary_reasoning}
                trajectory.append(traj)
            elif isinstance(step, ActionStep):
                safe_tool_calls = step.tool_calls if step.tool_calls is not None else []
                traj = {
                    "name": "action",
                    "tool_calls": [st.dict() for st in safe_tool_calls],
                    "obs": step.observations,
                    "think": step.action_think,
                    "cot_think": step.action_reasoning,
                    "memory_guidance": getattr(step, "memory_guidance", None),
                    "subagent_trajectories": getattr(step, "subagent_trajectories", None),
                }
                trajectory.append(traj)
            else:
                raise ValueError("[capture_trajectory] Unknown Step:", step)

        return {
            "agent_trajectory": trajectory,
        }

    def forward(self, task, answer=None, return_json=False, max_retries=3):
        last_error = None
        for _ in range(max_retries):
            try:
                if answer is not None:
                    result = self.agent_fn.run(task, answer=answer)
                else:
                    result = self.agent_fn.run(task)
                if return_json and isinstance(result, str):
                    result = safe_json_loads(result)
                elif not return_json and isinstance(result, dict):
                    result = str(result)
                return {
                    "agent_result": result, **self.capture_trajectory()
                }
            except Exception as e:
                last_error = e
                print(f"[BaseAgent] error: {e}")
                continue
        return {"error": str(last_error)}


class CoreAgent(BaseAgent):
    def __init__(
        self,
        model,
        summary_interval,
        prompts_type=None,
        max_steps=40,
        planning_system="flash_searcher",
        action_system=None,
        memory_provider=None,
        **kwargs
    ):
        super().__init__(model)
        self.action_system = action_system or planning_system
        bench_type = kwargs.pop("bench_type", None)
        harness_name = kwargs.pop("harness_name", None) or kwargs.pop("harness", None)
        normalized_bench_type = str(bench_type or kwargs.get("dataset_type") or "").strip().lower()
        strict_bench_tools = bool(
            kwargs.pop(
                "strict_bench_tools",
                normalized_bench_type in {"toolhop", "api_bank", "restbench", "mixed", "mixed_agent", "mixeddata", "taubench"},
            )
        )
        toolhop_sample = kwargs.get("toolhop_sample") if normalized_bench_type == "toolhop" else None
        toolhop_mode = kwargs.get("toolhop_mode", "closed") if normalized_bench_type == "toolhop" else None
        toolhop_functions: list[str] = []
        toolhop_tool_specs: list[dict[str, Any]] = []
        if isinstance(toolhop_sample, dict):
            raw_functions = toolhop_sample.get("functions", [])
            if isinstance(raw_functions, list):
                toolhop_functions = [
                    function_source
                    for function_source in raw_functions
                    if isinstance(function_source, str)
                ]
            raw_tools = toolhop_sample.get("tools", {})
            if isinstance(raw_tools, dict):
                toolhop_tool_specs = [
                    tool_spec
                    for tool_spec in raw_tools.values()
                    if isinstance(tool_spec, dict)
                ]
        if "extra_tools" in kwargs:
            raise ValueError(
                "CoreAgent(..., extra_tools=...) has been removed. "
                "Define bench tools in harness/module_action/tools.py instead."
            )

        web_tool = WebSearchTool()
        crawl_tool = CrawlPageTool(model=model)
        vector_tool = VectorSimilarityRetrieve(
            memory=None,
            model=model
        )
        
        reasoning_tool = Reasoning(model=model)
        process_tool = Process(agent=None)
        end_process_tool = EndProcess(agent=None)
        delete_memory_tool = DeleteMemory(agent=None)
        
        expert_parallel_tool = ExpertParallelTool(model=model, agents=[])
        camv_tool = CAMVTool(model=model)
        
        executor_tool = Executor(agent=None)
        refine_tool = Refine(agent=None)

        context = ActionContext(
            model=model,
            summary_interval=summary_interval,
            prompts_type=prompts_type,
            max_steps=max_steps,
            planning_system=planning_system,
            action_system=self.action_system,
            memory_provider=memory_provider,
            project_root=Path(__file__).resolve().parent,
            bench_type=bench_type or kwargs.get("dataset_type"),
            db_path=kwargs.get("db_path"),
            kwargs=kwargs,
            strict_bench_tools=strict_bench_tools,
            toolhop_sample=toolhop_sample,
            toolhop_mode=toolhop_mode,
            toolhop_functions=toolhop_functions,
            toolhop_tool_specs=toolhop_tool_specs,
            web_tool=web_tool,
            crawl_tool=crawl_tool,
            vector_tool=vector_tool,
            reasoning_tool=reasoning_tool,
            process_tool=process_tool,
            end_process_tool=end_process_tool,
            delete_memory_tool=delete_memory_tool,
            expert_parallel_tool=expert_parallel_tool,
            camv_tool=camv_tool,
            executor_tool=executor_tool,
            refine_tool=refine_tool,
        )
        from module_action.tools import load_bench_tools

        context.bench_tools = load_bench_tools(
            context.bench_type,
            db_path=context.db_path,
            context=context,
        )
        if harness_name:
            harness_module = harness_runtime.import_harness_module(harness_name)
            build_agent_from_context = getattr(harness_module, "build_agent_from_context", None)
            if build_agent_from_context is None:
                raise ValueError(
                    f"Harness '{harness_name}' does not export build_agent_from_context()."
                )
            self.agent_fn = build_agent_from_context(context)
        else:
            action_provider = get_action_provider(self.action_system)
            self.agent_fn = action_provider.build(context)

        # Set memory reference after agent initialization
        vector_tool.memory = self.agent_fn.memory
        process_tool.agent = self.agent_fn
        end_process_tool.agent = self.agent_fn
        delete_memory_tool.agent = self.agent_fn
        executor_tool.agent = self.agent_fn
        refine_tool.agent = self.agent_fn

        # sub memory space for owl planning_system
        if getattr(self.agent_fn, "planning_system", None) == "owl":
            if not hasattr(self.agent_fn, "web_memory") or self.agent_fn.web_memory is None:
                self.agent_fn.web_memory = []
            if not hasattr(self.agent_fn, "reasoning_memory") or self.agent_fn.reasoning_memory is None:
                self.agent_fn.reasoning_memory = []

class SearchAgent(CoreAgent):
    def __init__(
        self,
        model,
        summary_interval,
        prompts_type=None,
        max_steps=40,
        planning_system="flash_searcher",
        memory_provider=None,
        **kwargs
    ):
        super().__init__(
            model=model,
            summary_interval=summary_interval,
            prompts_type=prompts_type,
            max_steps=max_steps,
            planning_system=planning_system,
            action_system=planning_system,
            memory_provider=memory_provider,
            **kwargs,
        )


class MMSearchAgent(BaseAgent):
    def __init__(self, model, summary_interval, prompts_type=None, max_steps=40, planning_system="flash_searcher", memory_provider=None, **kwargs):
        super().__init__(model)

        web_tool = WebSearchTool()
        crawl_tool = CrawlPageTool(model=model)
        visual_tool = VisualInspectorTool(model, 100000)
        text_tool = TextInspectorTool(model, 100000)
        audio_tool = AudioInspectorTool(model, 100000)
        vector_tool = VectorSimilarityRetrieve(
            memory=None,  # Will be set after ToolCallingAgent initialization
            model=model
        )
        reasoning_tool = Reasoning(model=model)
        
        process_tool = Process(agent=None)
        end_process_tool = EndProcess(agent=None)
        delete_memory_tool = DeleteMemory(agent=None)
        # tools = [web_tool, crawl_tool, visual_tool] text or audio tool may not useful during agent execution.
        tools = [web_tool, crawl_tool, visual_tool, text_tool, audio_tool, vector_tool, reasoning_tool,
                 process_tool, end_process_tool, delete_memory_tool]

        self.agent_fn = ToolCallingAgent(
            model=model,
            tools=tools,
            summary_interval=summary_interval,
            max_steps=max_steps,
            prompts_type=prompts_type,
            planning_system=planning_system,
            memory_provider=memory_provider,
        )

        # Set memory reference after agent initialization
        vector_tool.memory = self.agent_fn.memory
        process_tool.agent = self.agent_fn
        end_process_tool.agent = self.agent_fn
        delete_memory_tool.agent = self.agent_fn
        
        # sub memory space for owl planning_system
        if getattr(self.agent_fn, "planning_system", None) == "owl":
            if not hasattr(self.agent_fn, "web_memory") or self.agent_fn.web_memory is None:
                self.agent_fn.web_memory = []
            if not hasattr(self.agent_fn, "reasoning_memory") or self.agent_fn.reasoning_memory is None:
                self.agent_fn.reasoning_memory = []


