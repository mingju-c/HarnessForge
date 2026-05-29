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

from dataclasses import asdict, dataclass
from logging import getLogger
from typing import Any, Dict, List, TypedDict, Union

from .models import ChatMessage, MessageRole
from .monitoring import AgentLogger, LogLevel
from .utils import AgentError, make_json_serializable


logger = getLogger(__name__)


class Message(TypedDict):
    role: MessageRole
    content: str | list[dict]

@dataclass
class ToolCall:
    name: str
    arguments: Any
    id: str

    def dict(self):
        return {
            "name": self.name,
            "arguments": make_json_serializable(self.arguments),
        }

@dataclass
class MemoryStep:
    input_tokens: int = 0
    output_tokens: int = 0
    model_input_messages: List[Dict[str, Any]] | None = None
    model_output_raw: Any | None = None

    def dict(self):
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model_input_messages": self.model_input_messages,
            "model_output_raw": self.model_output_raw,
        }

    def to_messages(self, **kwargs) -> List[Dict[str, Any]]:
        raise NotImplementedError


@dataclass
class ActionStep(MemoryStep):
    model_output_messages: List[Message] | None = None
    tool_calls: List[ToolCall] | None = None
    start_time: float | None = None
    end_time: float | None = None
    step_number: int | None = None
    error: AgentError | None = None
    duration: float | None = None
    observations: str | None = None
    observations_images: List[str] | None = None
    action_output: Any = None
    action_think: Any = None
    action_reasoning: Any = None
    score: float = 0.0
    evaluate_thought: str | None = None
    memory_guidance: str | None = None
    subagent_trajectories: Dict[str, Any] | None = None
    
    def dict(self):
        res = super().dict()
        res.update({
            "model_output_messages": self.model_output_messages,
            "tool_calls": [tc.dict() for tc in self.tool_calls] if self.tool_calls else [],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "step_number": self.step_number,
            "error": self.error.dict() if self.error else None,
            "duration": self.duration,
            "observations": self.observations,
            "action_think": self.action_think,
            "action_output": make_json_serializable(self.action_output),
            "action_reasoning": self.action_reasoning,
            "score": self.score,
            "evaluate_thought": self.evaluate_thought,
            "memory_guidance": self.memory_guidance,
            "subagent_trajectories": make_json_serializable(self.subagent_trajectories),
        })
        return res

    def to_messages(self, summary_mode: bool = False, show_model_input_messages: bool = False) -> List[Message]:
        messages = []
        if self.memory_guidance:
            formatted_memory = (
                "---Memory System Guidance---\n"
                f"{self.memory_guidance}\n"
                "---End Memory---"
            )
            messages.append(
                Message(
                    role=MessageRole.USER,
                    content=[{"type": "text", "text": formatted_memory}]
                )
            )
        if self.model_input_messages is not None and show_model_input_messages:
            messages.append(Message(role=MessageRole.SYSTEM, content=self.model_input_messages))

        if self.tool_calls:
            tool_output = {
                "tools":[tc.dict() for tc in self.tool_calls]
            }
            messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=[
                        {
                            "type": "text",
                            "text": "Calling tools:\n" + str(tool_output),
                        }
                    ],
                )
            )

        if self.observations is not None:
            messages.append(
                Message(
                    role=MessageRole.TOOL_RESPONSE,
                    content=[
                        {
                            "type": "text",
                            "text": f"Tool calling observation:\n{self.observations}",
                        }
                    ],
                )
            )
        if self.error is not None:
            error_message = (
                "Error:\n"
                + str(self.error)
                + "\nNow let's retry: take care not to repeat previous errors! If you have retried several times, try a completely different approach.\n"
            )
            message_content = f"Call id: {self.tool_calls[0].id}\n" if self.tool_calls else ""
            message_content += error_message
            messages.append(
                Message(role=MessageRole.TOOL_RESPONSE, content=[{"type": "text", "text": message_content}])
            )
        return messages


@dataclass
class PlanningStep(MemoryStep):
    plan: str = ""
    plan_think: str = ""
    plan_reasoning: str = ""
    memory_guidance: str | None = None

    def dict(self):
        res = super().dict()
        res.update({
            "plan": self.plan,
            "plan_think": self.plan_think,
            "plan_reasoning": self.plan_reasoning,
            "memory_guidance": self.memory_guidance,
        })
        return res

    def to_messages(self, summary_mode: bool, **kwargs) -> List[Message]:
        messages = []
        if self.memory_guidance:
            formatted_memory = (
                "————Memory System Guidance————\n"
                f"{self.memory_guidance}\n"
                "————End Memory————"
            )
            messages.append(
                Message(
                    role=MessageRole.USER, 
                    content=[{"type": "text", "text": formatted_memory}]
                )
            )
            
        messages.append(
            Message(
                role=MessageRole.USER, content=[{"type": "text", "text": f"Now, begin your planning analysis for this task!"}]
            )
        )
        messages.append(
            Message(
                role=MessageRole.ASSISTANT, content=[{"type": "text", "text": f"[PLAN]:\n{self.plan.strip()}"}]
            )
        )
        return messages
    
@dataclass
class SummaryStep(MemoryStep):
    summary: str = ""
    summary_reasoning: str = ""

    def dict(self):
        res = super().dict()
        res.update({
            "summary": self.summary,
            "summary_reasoning": self.summary_reasoning,
        })
        return res

    def to_messages(self, summary_mode: bool, **kwargs) -> List[Message]:
        messages = []
        messages.append(
            Message(
                role=MessageRole.USER, content=[{"type": "text", "text": f"Now, summarize and analysis the task completion status and provide recommendations for next steps!"}]
            )
        )
        messages.append(
            Message(
                role=MessageRole.ASSISTANT, content=[{"type": "text", "text": f"[SUMMARY]:\n{self.summary.strip()}"}]
            )
        )
        return messages

@dataclass
class TaskStep(MemoryStep):
    task: str = ""
    task_images: List[str] | None = None

    def to_messages(self, summary_mode: bool = False, **kwargs) -> List[Message]:
        content = [{"type": "text", "text": f"New task:\n{self.task}"}]

        return [Message(role=MessageRole.USER, content=content)]


@dataclass
class SystemPromptStep(MemoryStep):
    system_prompt: str = ""

    def to_messages(self, summary_mode: bool = False, **kwargs) -> List[Message]:
        if summary_mode:
            return []
        return [Message(role=MessageRole.SYSTEM, content=[{"type": "text", "text": self.system_prompt}])]


class AgentMemory:
    def __init__(self, system_prompt: str):
        self.system_prompt = SystemPromptStep(system_prompt=system_prompt)
        self.steps: List[Union[TaskStep, ActionStep, PlanningStep, SummaryStep]] = []

    def reset(self):
        self.steps = []

    def get_succinct_steps(self) -> list[dict]:
        return [
            {key: value for key, value in step.dict().items() if key != "model_input_messages"} for step in self.steps
        ]

    def get_full_steps(self) -> list[dict]:
        return [step.dict() for step in self.steps]
