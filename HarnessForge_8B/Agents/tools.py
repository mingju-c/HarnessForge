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

import json
import uuid
import inspect
import logging
import copy
import time
from functools import wraps
from typing import Dict, Union, Any, List, Optional, TYPE_CHECKING

from ._function_type_hints_utils import _convert_type_hints_to_json_schema
from .agent_types import handle_agent_input_types, handle_agent_output_types
from .monitoring import LogLevel

import textwrap
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .memory import ActionStep, PlanningStep, ToolCall, AgentMemory
    from .models import ChatMessage, MessageRole


def validate_after_init(cls):
    original_init = cls.__init__

    @wraps(original_init)
    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.validate_arguments()

    cls.__init__ = new_init
    return cls


AUTHORIZED_TYPES = [
    "dict", "string", "boolean", "integer", "number",
    "image", "audio", "array", "object", "any", "null", "Tuple"
]

CONVERSION_DICT = {"str": "string", "int": "integer", "float": "number"}


class Tool:
    """
    HF-style Tool base class with argument/schema validation.
    """

    name: str
    description: str
    inputs: Dict[str, Dict[str, Union[str, type, bool]]]
    output_type: str

    def __init__(self, *args, **kwargs):
        self.is_initialized = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        validate_after_init(cls)

    def validate_arguments(self):
        required_attributes = {
            "description": str,
            "name": str,
            "inputs": dict,
            "output_type": str,
        }

        for attr, expected_type in required_attributes.items():
            attr_value = getattr(self, attr, None)
            if attr_value is None:
                raise TypeError(f"You must set an attribute {attr}.")
            if not isinstance(attr_value, expected_type):
                raise TypeError(
                    f"Attribute {attr} should have type {expected_type.__name__}, got {type(attr_value)} instead."
                )

        for input_name, input_content in self.inputs.items():
            assert isinstance(input_content, dict), f"Input '{input_name}' should be a dictionary."
            assert "type" in input_content and "description" in input_content, (
                f"Input '{input_name}' should have keys 'type' and 'description', has only {list(input_content.keys())}."
            )
            if input_content["type"] not in AUTHORIZED_TYPES:
                raise Exception(
                    f"Input '{input_name}': type '{input_content['type']}' is not authorized, should be one of {AUTHORIZED_TYPES}."
                )

        assert getattr(self, "output_type", None) in AUTHORIZED_TYPES

        # Validate forward signature unless explicitly skipped
        if not (hasattr(self, "skip_forward_signature_validation") and getattr(self, "skip_forward_signature_validation") is True):
            signature = inspect.signature(self.forward)
            if not set(signature.parameters.keys()) == set(self.inputs.keys()):
                raise Exception(
                    "Tool.forward signature params must exactly match tool.inputs keys."
                )

            json_schema = _convert_type_hints_to_json_schema(self.forward, error_on_missing_type_hints=False)["properties"]
            for key, value in self.inputs.items():
                assert key in json_schema, f"Input '{key}' should be in function signature."
                if "nullable" in value:
                    assert "nullable" in json_schema[key], (
                        f"Nullable '{key}' in inputs requires 'nullable' in function signature schema."
                    )
                if key in json_schema and "nullable" in json_schema[key]:
                    assert "nullable" in value, (
                        f"Nullable '{key}' in signature schema requires 'nullable' in inputs."
                    )

    def forward(self, *args, **kwargs):
        return NotImplementedError("Implement forward() in subclass.")

    def __call__(self, *args, sanitize_inputs_outputs: bool = False, **kwargs):
        if not self.is_initialized:
            self.setup()

        # allow dict-as-single-arg calling
        if len(args) == 1 and len(kwargs) == 0 and isinstance(args[0], dict):
            potential_kwargs = args[0]
            if all(key in self.inputs for key in potential_kwargs):
                args = ()
                kwargs = potential_kwargs

        if sanitize_inputs_outputs:
            args, kwargs = handle_agent_input_types(*args, **kwargs)
        outputs = self.forward(*args, **kwargs)
        if sanitize_inputs_outputs:
            outputs = handle_agent_output_types(outputs, self.output_type)
        return outputs

    def setup(self):
        self.is_initialized = True


class FinalAnswerTool(Tool):
    name = "final_answer"
    description = "Gives a clear, accurate final answer to the given task."
    inputs = {"answer": {"type": "string", "description": "The clear, accurate final answer to the task"}}
    output_type = "string"

    def forward(self, answer: Any) -> Any:
        return answer


class VectorSimilarityRetrieve(Tool):
    name = "vector_similarity_retrieve"
    description = "Retrieves the most similar historical execution step based on vector similarity."
    inputs = {"query": {"type": "string", "description": "Query describing what to retrieve"}}
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, memory, model):
        super().__init__()
        self.memory = memory
        self.model = model
        self.texts = []
        self.action_step_indices = []
        self.is_initialized = False

    def setup(self):
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            raise ImportError("Vector similarity retrieval requires: pip install numpy scikit-learn")
        self.np = np
        self.TfidfVectorizer = TfidfVectorizer
        self.cosine_similarity = cosine_similarity
        self.is_initialized = True

    def update_memory_embeddings(self):
        from .memory import ActionStep
        current_action_steps = [(i, step) for i, step in enumerate(self.memory.steps) if isinstance(step, ActionStep)]
        if len(current_action_steps) > len(self.texts):
            for i, step in current_action_steps[len(self.texts):]:
                messages = step.to_messages(summary_mode=False)
                text_parts = []
                for msg in messages:
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                    else:
                        text_parts.append(str(content))
                text_content = "\n".join(text_parts)
                if text_content.strip():
                    self.texts.append(text_content)
                    self.action_step_indices.append(i)

    def forward(self, query: str) -> str:
        if not self.is_initialized:
            self.setup()
        self.update_memory_embeddings()
        if not self.texts:
            return "No historical action steps available yet."

        vectorizer = self.TfidfVectorizer(max_features=1000, stop_words="english", ngram_range=(1, 2))
        all_texts = self.texts + [query]
        tfidf_matrix = vectorizer.fit_transform(all_texts)
        query_vector = tfidf_matrix[-1]
        history_vectors = tfidf_matrix[:-1]
        similarities = self.cosine_similarity(query_vector, history_vectors)[0]
        top_idx = similarities.argmax()

        from .memory import ActionStep
        action_steps = [step for step in self.memory.steps if isinstance(step, ActionStep)]
        if top_idx >= len(action_steps):
            return "Error: Index out of range."

        most_similar_step = action_steps[top_idx]
        messages = most_similar_step.to_messages(summary_mode=False)
        content_parts = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        content_parts.append(item.get("text", ""))
            else:
                content_parts.append(str(content))

        result_content = "\n".join(content_parts)
        return f"Most similar historical step (similarity score: {similarities[top_idx]:.3f}):\n\n{result_content}"


class Reasoning(Tool):
    name = "reasoning"
    description = "Calls an LLM API for deep reasoning tasks."
    inputs = {"task": {"type": "string", "description": "Reasoning task description"}}
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, model=None):
        super().__init__()
        self.model = model
        self.api_key = None
        self.api_base = None
        self.model_id = None
        self.client = None
        self.is_initialized = False

    def setup(self):
        import os
        try:
            import openai
        except ModuleNotFoundError:
            raise ModuleNotFoundError("Please install 'openai' to use Reasoning tool: `pip install openai`") from None

        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base = os.getenv("OPENAI_BASE_URL")
        # Use PLANNING_MODEL for reasoning tasks
        self.model_id = os.getenv("PLANNING_MODEL")

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        if not self.model_id:
            raise ValueError("PLANNING_MODEL environment variable is not set")

        self.client = openai.OpenAI(base_url=self.api_base, api_key=self.api_key)
        self.is_initialized = True

    def forward(self, task: str | None = None, prompt: str | None = None) -> str:
        task = task or prompt
        if not task:
            return "Error: Missing reasoning task."

        if self.model is not None:
            return self._forward_with_shared_model(task)

        if not self.is_initialized:
            self.setup()

        max_retries = 4
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=[{"role": "user", "content": task}],
                    temperature=0.7,
                )
                content = None
                if response.choices:
                    content = getattr(response.choices[0].message, "content", None)
                if isinstance(content, str) and content.strip():
                    return content
                if content:
                    return str(content)
                if attempt < max_retries - 1:
                    backoff = min(2 ** attempt, 8)
                    logging.warning(
                        "Reasoning tool received empty response. "
                        f"Retrying in {backoff} seconds ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(backoff)
                    continue
                return "Error: Empty response from reasoning model"
            except Exception as e:
                if attempt < max_retries - 1:
                    backoff = min(2 ** attempt, 8)
                    logging.warning(
                        f"Reasoning tool error: {e}. Retrying in {backoff} seconds "
                        f"({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(backoff)
                    continue
                return f"Error during reasoning: {str(e)}"

    def _forward_with_shared_model(self, task: str) -> str:
        max_retries = 4
        for attempt in range(max_retries):
            try:
                response = self.model([{"role": "user", "content": task}])
                content = getattr(response, "content", None)
                if isinstance(content, str) and content.strip():
                    return content
                if content:
                    return str(content)
                if attempt < max_retries - 1:
                    backoff = min(2 ** attempt, 8)
                    logging.warning(
                        "Reasoning tool received empty response from shared model. "
                        f"Retrying in {backoff} seconds ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(backoff)
                    continue
                return "Error: Empty response from reasoning model"
            except Exception as e:
                if attempt < max_retries - 1:
                    backoff = min(2 ** attempt, 8)
                    logging.warning(
                        f"Reasoning tool error with shared model: {e}. "
                        f"Retrying in {backoff} seconds ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(backoff)
                    continue
                return f"Error during reasoning: {str(e)}"


def _domain_from_process_name(process_name: str) -> str:
    return (process_name.split("-", 1)[0] if process_name else "").strip().lower()

def _new_toolcall_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

class Process(Tool):
    name = "Process"
    description = (
                   "Executes a sequence of tool calls within a named sub-process in isolated sub-memory."
                   "Use it to group coherent steps such as retrieval, inspection, validation, or reasoning."
                  )
    inputs = {
        "process_name": {"type": "string", "description": "Short process label such as 'web', 'reasoning', 'inspection', or another task-specific domain name."},
        "tools": {"type": "array", "description": "List of tool-call dicts in execution order"},
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, agent):
        super().__init__()
        self.agent = agent

        self.web_system_prompt = textwrap.dedent("""
        You are a helpful assistant that can search the web, extract webpage content, simulate browser actions,
        and provide relevant information to solve the given task.

        Keep in mind that:
        - Do not be overly confident in your own knowledge. Searching can provide a broader perspective and help validate existing knowledge.
        - If one way fails to provide an answer, try other ways or methods. The answer does exist.
        - If the search snippet is unhelpful but the URL comes from an authoritative source, try visiting the website for more details.
        - When looking for specific numerical values (e.g., dollar amounts), prioritize reliable sources and avoid relying only on search snippets.
        - When solving tasks that require web searches, check Wikipedia first before exploring other websites.
        - You can simulate browser actions to get more information or verify the information you have found.

        Browser simulation is also helpful for finding target URLs:
        - Browser simulation operations do not necessarily need to find specific answers, but can also help find web page URLs that contain answers.
        - You can find the answer by performing subsequent operations on the URL, such as extracting the content of the webpage.

        Tool usage guidance:
        - Do not solely rely on document tools or browser simulation to find the answer; combine them as needed.
        - Some content may need browser simulation to get, or some content is rendered by JavaScript.

        Reporting requirement:
        - Mention the URLs you have visited and processed.

        Search tips:
        - Never add too many keywords in your search query.
        - For complex questions, search results may not directly answer; focus on official sources and use interaction step-by-step.

        Result acceptance:
        - You only need to collect relevant information; it may not directly answer the original question yet.
        """).strip()

        self.reasoning_system_prompt = textwrap.dedent("""
        You are a helpful assistant that specializes in reasoning and logical deduction.
        
        When necessary:
        - Break down complex problems into smaller steps.
        - Use logical reasoning to derive answers from the information you have.
        - If you need to perform calculations, do them carefully step-by-step.
        
        You should rely on the information provided in the context or gathered through search tools.
        """).strip()

        self.generic_system_prompt = textwrap.dedent("""
        You are a helpful assistant executing a focused sub-process for a larger task.

        Keep the sub-process coherent and goal-directed:
        - Use only the tool calls provided to the process.
        - Focus on gathering or validating the information needed for this sub-process.
        - Record the relevant observations clearly so they can be merged back into the main trajectory.
        """).strip()

    def _get_domain_config(self, process_name: str):
        if process_name == "web":
            return "web_memory", self.web_system_prompt
        elif process_name == "reasoning":
            return "reasoning_memory", self.reasoning_system_prompt
        else:
            safe_name = re.sub(r"[^a-z0-9_]+", "_", (process_name or "task").strip().lower()).strip("_") or "task"
            return f"{safe_name}_memory", self.generic_system_prompt

    def _ensure_domain_memory_initialized(self, process_name: str) -> list:
        from .memory import PlanningStep 

        mem_attr, system_prompt_content = self._get_domain_config(process_name)

        if not hasattr(self.agent, mem_attr) or getattr(self.agent, mem_attr) is None:
            setattr(self.agent, mem_attr, [])
        
        domain_memory = getattr(self.agent, mem_attr)

        if len(domain_memory) == 0:
            system_message = {"role": "system", "content": system_prompt_content}
            
            init_step = PlanningStep(
                model_input_messages=[system_message],
                plan=f"Initialize {process_name} environment",
                plan_think=f"Initializing {process_name} domain environment. System prompt injected successfully.",
                plan_reasoning="System initialization required." 
            )
            
            domain_memory.append(init_step)
            
        return domain_memory

    def forward(self, process_name: str, tools: List[Dict[str, Any]]) -> str:
        from .memory import ActionStep, ToolCall

        if not hasattr(self.agent, "_active_process_session"):
            self.agent._active_process_session = {}
        session_id = self.agent._active_process_session.get(process_name)
        if session_id is None:
            session_id = uuid.uuid4().hex[:8]
            self.agent._active_process_session[process_name] = session_id

        # 1. domain System Prompt 
        domain_memory = self._ensure_domain_memory_initialized(process_name)

        # 2. Tool_calling
        observations_full: List[str] = []
        observations_return: List[str] = []
        tool_calls_record: List[ToolCall] = []
        error_count = 0

        self.agent.logger.log(
            Panel(Text(f"Starting Process: {process_name} ({len(tools)} steps)")),
            level="INFO"
        )

        for tool_call_dict in tools:
            t_name = tool_call_dict.get("name")
            t_args = tool_call_dict.get("arguments", {}) or {}
            plan_think = tool_call_dict.get("plan_think", "") or ""
            
            try:
                observation_content = self.agent.execute_tool_call(t_name, t_args)
                observation_str = str(observation_content)
            except Exception as e:
                error_count += 1
                observation_str = f"Error: {str(e)}"

            tc_id = uuid.uuid4().hex[:8] 
            tool_calls_record.append(ToolCall(id=tc_id, name=t_name, arguments=t_args))

            observations_full.append(f"Action: {t_name}\nArgs: {t_args}\nResult: {observation_str}")

            header = f"== {t_name} =="
            if plan_think:
                header += f" | {plan_think}"
            observations_return.append(header + "\n" + observation_str)

        # 3. ActionStep
        domain_memory.append(ActionStep(
            model_input_messages=[], 
            tool_calls=tool_calls_record,
            observations="\n\n".join(observations_full),
            action_think=f"process={process_name};session={session_id};phase=trace",
            action_reasoning="",
        ))

        exec_status = "ok" if error_count == 0 else "tool_error"
        
        return (
            f"Process '{process_name}' executed {len(tools)} steps.\n"
            f"Status: {exec_status}\n"
            f"Observations:\n"
            + "\n".join(observations_return)
        )

def _get_prompt(d: dict, *keys, default=None):
    """Safe nested dict get by trying multiple keys (supports 'initial plan' and 'initial_plan')."""
    cur = d
    for k in keys[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    last = keys[-1]
    if isinstance(cur, dict) and last in cur:
        return cur[last]
    return default

def _render_jinja(template: str, variables: dict) -> str:
    """Render jinja2 template with strict undefined (fail fast on missing vars)."""
    from jinja2 import StrictUndefined, Template
    return Template(template, undefined=StrictUndefined).render(**variables)


class EndProcess(Tool):
    name = "EndProcess"
    description = "Finalizes the current process. Extracts key findings to global memory (commit) or handles failure with replanning."
    inputs = {
        "status": {
            "type": "string", 
            "description": "Execution status: 'finished' (success) or 'failed' (error/stuck)."
        },
        "process_name": {
            "type": "string", 
            "description": "The domain process name (e.g., 'web-search', 'reasoning-1')."
        },
        "commit": {
            "type": "string", 
            "description": "CRITICAL for 'finished': The final answer, summary, or extracted facts to persist in GLOBAL memory.", 
            "nullable": True
        },
        "failure_reason": {
            "type": "string", 
            "description": "CRITICAL for 'failed': Why it failed and what should be done differently.", 
            "nullable": True
        },
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    def _get_domain_memory(self, domain: str) -> list:
        mem_attr = f"{domain}_memory"
        if not hasattr(self.agent, mem_attr) or getattr(self.agent, mem_attr) is None:
            setattr(self.agent, mem_attr, [])
        return getattr(self.agent, mem_attr)

    def forward(self, status: str, process_name: str, **kwargs) -> str:
        """
        Refactored Logic:
        1. Identify Domain & Session.
        2. If Failed: 
           - Retrieve sub-memory trace.
           - Trigger LLM to generate a NEW Plan (PlanningStep).
           - Write failure summary to Global Memory.
           - Clean up intermediate steps.
        3. If Finished:
           - Extract 'commit' (the answer).
           - Write success summary (PROCESS_COMMIT) to Global Memory.
           - Clean up intermediate steps.
        """
        from .memory import ActionStep, PlanningStep, ToolCall
        from .models import ChatMessage, MessageRole
        from .monitoring import LogLevel
        from rich.text import Text

        # --- 1. Validation & Setup ---
        domain = _domain_from_process_name(process_name)
        if domain not in ("web", "reasoning"):
            return f"Error: Invalid domain '{domain}'. Must be 'web' or 'reasoning'."

        # Retrieve Session ID (to link sub-memory traces)
        session_id = getattr(self.agent, "_active_process_session", {}).get(process_name)
        
        # Helper to generate unique ID
        def _new_id(): return _new_toolcall_id(f"{process_name}:EndProcess:{status}")

        # --- 2. Handle Failure & Replanning ---
        if status == "failed":
            failure_reason = kwargs.get("failure_reason") or "Unknown failure reason."
            
            try:
                self.agent.logger.log(
                    Text(f"Process '{process_name}' Failed. Reason: {failure_reason}", style="bold red"),
                    level=LogLevel.ERROR
                )
            except Exception:
                pass

            # A. Retrieve Trace from Sub-Memory for Context
            domain_memory = self._get_domain_memory(domain)
            trace_steps = [
                s.observations for s in domain_memory
                if isinstance(s, ActionStep)
                and f"process={process_name}" in getattr(s, "action_think", "")
                and "phase=trace" in getattr(s, "action_think", "")
                and (session_id is None or f"session={session_id}" in getattr(s, "action_think", ""))
            ]
            trace_text = "\n".join(trace_steps)[-5000:] # Limit context size

            # B. Generate New Plan (Replanning)
            # We explicitly call the model here to pivot the strategy immediately.
            pt = getattr(self.agent, "prompt_templates", {}) or {}
            tpl = (
                _get_prompt(pt, "replanning", "initial plan")
                or _get_prompt(pt, "replanning", "initial_plan")
            )
            
            if tpl:
                replan_text = _render_jinja(
                    tpl,
                    variables={
                        "task": getattr(self.agent, "task", "Unknown Task"),
                        "process_name": process_name,
                        "trace": trace_text,
                        "failure_reason": failure_reason
                    },
                )
                
                replan_msgs = [{"role": MessageRole.SYSTEM, "content": [{"type": "text", "text": replan_text}]}]
                
                # Model Call
                try:
                    chat_message_plan: ChatMessage = self.agent.model(replan_msgs)
                    
                    # Insert PlanningStep into Global Memory
                    replanning_step = PlanningStep(
                        model_input_messages=replan_msgs,
                        plan=chat_message_plan.content,
                        plan_reasoning=getattr(chat_message_plan, "reasoning_content", None),
                        plan_think=f"Replanning triggered by failure in {process_name}",
                    )
                    self.agent.memory.steps.append(replanning_step)
                except Exception as e:
                    self.agent.logger.log(Text(f"Replanning generation failed: {e}", style="red"), level=LogLevel.ERROR)

            # C. Write Summary Marker (ActionStep)
            # This step is protected from deletion and serves as the "End" marker in history.
            summary_obs = (
                "PROCESS_COMMIT\n"
                f"Status: Failed\n"
                f"Process: {process_name}\n"
                f"Reason: {failure_reason}\n"
                "Action Taken: Replanning step generated and added to memory."
            )
            
            self.agent.memory.steps.append(ActionStep(
                model_input_messages=[],
                tool_calls=[ToolCall(id=_new_id(), name="EndProcess", arguments=kwargs)],
                observations=summary_obs,
                action_think=f"process={process_name};session={session_id};domain={domain};phase=summary"
            ))

            # D. Cleanup Global Memory (Remove noisy intermediate steps)
            DeleteMemory(self.agent).forward(
                target_memory="global",
                process_name=process_name,
                process_group=None,
                keep_summary=True,
                keep_only_latest_summary=True,
            )

            # E. Clear Session
            if hasattr(self.agent, "_active_process_session"):
                self.agent._active_process_session.pop(process_name, None)

            return f"Process failed. Replanning completed. Global memory cleaned."

        # --- 3. Handle Success & Commit ---
        elif status == "finished":
            commit_content = kwargs.get("commit") or ""
            
            # Fallback if model forgets to provide commit content
            if not commit_content.strip():
                commit_content = "(No commit content provided by model. Check sub-memory for details.)"

            try:
                self.agent.logger.log(
                    Text(f"Process '{process_name}' Finished. Committing findings.", style="bold green"),
                    level=LogLevel.INFO
                )
            except Exception:
                pass

            # A. Write Summary Marker (ActionStep)
            # This contains the EXTRACTED knowledge, not the raw logs.
            summary_obs = (
                "PROCESS_COMMIT\n"
                f"Status: Finished\n"
                f"Process: {process_name}\n"
                f"Merged Findings (Commit):\n{commit_content}"
            )

            self.agent.memory.steps.append(ActionStep(
                model_input_messages=[],
                tool_calls=[ToolCall(id=_new_id(), name="EndProcess", arguments=kwargs)],
                observations=summary_obs,
                action_think=f"process={process_name};session={session_id};domain={domain};phase=summary"
            ))

            # B. Cleanup Global Memory
            DeleteMemory(self.agent).forward(
                target_memory="global",
                process_name=process_name,
                process_group=None,
                keep_summary=True,
                keep_only_latest_summary=True,
            )

            # C. Clear Session
            if hasattr(self.agent, "_active_process_session"):
                self.agent._active_process_session.pop(process_name, None)

            return (
                    f"Process '{process_name}' finished. Findings committed to global memory.\n"
                    f"SYSTEM INSTRUCTION: The sub-process '{process_name}' is complete. "
                    f"Intermediate steps have been cleaned. DO NOT call EndProcess again. "
                )

        else:
            return "Error: Status must be 'finished' or 'failed'."

class DeleteMemory(Tool):
    name = "DeleteMemory"
    description = "Cleans up process execution traces from global memory, preserving summaries."
    inputs = {
        "target_memory": {
            "type": "string", 
            "description": "The target memory scope to clean (e.g., 'global')."
        },
        "process_name": {
            "type": "string", 
            "description": "The name of the process whose traces should be removed."
        },
        "process_group": {
            "type": "string", 
            "nullable": True, 
            "description": "Optional group identifier for batch cleaning."
        },
        "keep_summary": {
            "type": "boolean", 
            "default": True, 
            "description": "Whether to preserve the summary/commit step of the process."
        },
        "keep_only_latest_summary": {
            "type": "boolean", 
            "default": True, 
            "description": "If True, only the most recent summary is kept; older ones are deleted."
        },
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    def forward(self, target_memory, process_name, process_group, keep_summary, keep_only_latest_summary):
        from .memory import ActionStep

        if self.agent is None:
            return "Error: DeleteMemory tool not initialized with an agent instance."

        if target_memory != "global": 
            return "Skipped non-global memory."

        steps = self.agent.memory.steps
        new_steps = []
        
        def is_protected_summary(step):
            if not isinstance(step, ActionStep): return False
            obs = getattr(step, "observations", "") or ""
            think = getattr(step, "action_think", "") or ""
            is_summ = "PROCESS_COMMIT" in obs or "phase=summary" in think
            
            matches_proc = False
            if process_name and f"process={process_name}" in think: matches_proc = True
            
            return is_summ and matches_proc

        summary_indices = [i for i, s in enumerate(steps) if is_protected_summary(s)]
        indices_to_keep = set()

        if keep_summary:
            if keep_only_latest_summary and summary_indices:
                indices_to_keep.add(summary_indices[-1]) 
            else:
                indices_to_keep.update(summary_indices)

        removed_count = 0
        for i, step in enumerate(steps):
            # 1. not ActionStep -> keep
            if not isinstance(step, ActionStep):
                new_steps.append(step)
                continue

            # 2. Summary -> keep
            if i in indices_to_keep:
                new_steps.append(step)
                continue
            
            # 3. EndProcess  -> Keep
            is_end_process_call = False
            for tc in (step.tool_calls or []):
                if tc.name == "EndProcess":
                    is_end_process_call = True
                    break
            
            if is_end_process_call:
                new_steps.append(step)
                continue

            # 4. Process  -> delete
            is_target_process = False
            for tc in (step.tool_calls or []):
                args = tc.arguments or {}
                if args.get("process_name") == process_name:
                    is_target_process = True
                    break
            
            if is_target_process:
                removed_count += 1
                continue # Skip adding to new_steps (Delete)
                
            new_steps.append(step)

        self.agent.memory.steps = new_steps
        return f"Memory cleaned. Removed {removed_count} steps. Summary preserved."

class VoteTool(Tool):
    """
    Decision-making aggregator for heterogeneous ensembles in JoyAgent.
    Implements Majority Vote and Critic-based Verdict.
    """
    name = "vote_and_synthesize"
    description = "Evaluates and aggregates answers from multiple heterogeneous agents using Majority Vote or Critic Verdict."
    inputs = {
        "task": {"type": "string", "description": "The original task description."},
        "candidates": {
            "type": "array", 
            "description": "A list of candidate solution dictionaries. Each dict MUST have 'agent_name', 'answer', and 'message_object'."
        }
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.agent = None

    def _canonicalize(self, answer: str) -> str:
        import re
        # Standardize: lowercase, remove special chars to improve matching
        text = str(answer).lower().strip()
        text = re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", text)
        return text

    def forward(
        self,
        task: str,
        candidates: Optional[List[Dict[str, Any]]] = None,
        answers: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if candidates is None and answers is not None:
            candidates = answers
        if not candidates:
            return "Error: No candidate answers provided for voting."
            
        # 1. Majority Vote Logic
        votes = {}
        for cand in candidates:
            raw_ans = cand.get("answer", "")
            can_ans = self._canonicalize(raw_ans)
            if can_ans:
                if can_ans not in votes:
                    votes[can_ans] = {"count": 0, "original": raw_ans}
                votes[can_ans]["count"] += 1
        
        total_votes = len(candidates)
        majority_threshold = total_votes / 2
        best_candidate = None
        for can_ans, info in votes.items():
            if info["count"] > majority_threshold:
                best_candidate = info["original"]
                break
        
        # 2. Extract Hidden Working Memory from Agent
        full_data = getattr(self.agent, "_ensemble_internal_memory", [])
        memory_map = {d["agent_name"]: d["message_object"] for d in full_data}
        
        # Token Optimization: Use deepcopy for rendering to avoid polluting 
        # the Supervisor's tool-call memory with massive expert traces.
        render_candidates = copy.deepcopy(candidates)
        for cand in render_candidates:
            if cand["agent_name"] in memory_map:
                cand["message_object"] = memory_map[cand["agent_name"]]
            else:
                cand["message_object"] = {
                    "reasoning_chains": [],
                    "tool_invocations": [],
                    "intermediate_evidence": [],
                }

        # 3. Critic Verdict (Working Memory Analysis)
        pt = getattr(self.agent, "prompt_templates", {}) if self.agent else {}
        if pt and "critic" in pt:
            tpl = pt["critic"]["prompt"]
            prompt = _render_jinja(tpl, {"task": task, "candidates": render_candidates, "best_candidate": best_candidate})
        else:
            return "Error: Critic prompt template not found in YAML."

        msg = [{"role": "user", "content": prompt}]
        try:
            response = self.model(msg)
            res_text = getattr(response, "content", str(response))
            
            # --- JoyAgent: Record Semantic Memory (Knowledge Distillation) ---
            try:
                # 1. Extract succinct trajectory from memory
                succinct_steps = self.agent.memory.get_succinct_steps()
                clean_traj = []
                # Token Optimization: Only take the most relevant steps (e.g., last 15 steps)
                # and truncate observations more aggressively for the distiller
                for s in succinct_steps[-15:]:
                    item = {}
                    if s.get("action_think"): item["think"] = s["action_think"]
                    if s.get("observations"): item["obs"] = str(s["observations"])[:200]
                    if item: clean_traj.append(item)
                
                # 2. Get distiller prompt from YAML
                if pt and "distiller" in pt:
                    distill_tpl = pt["distiller"]["prompt"]
                    distill_prompt = _render_jinja(distill_tpl, {
                        "task": task,
                        "trajectory": json.dumps(clean_traj, ensure_ascii=False)[:4000],
                        "answer": res_text
                    })
                    
                    # 3. Call model to distill
                    distill_msg = [{"role": "user", "content": distill_prompt}]
                    distill_res = self.model(distill_msg)
                    knowledge_unit = getattr(distill_res, "content", str(distill_res))
                    
                    # 4. Append to Global Memory (self.agent.memory.steps)
                    from .memory import ActionStep
                    self.agent.memory.steps.append(ActionStep(
                        observations=f"HISTORICAL_KNOWLEDGE_UNIT:\n{knowledge_unit}",
                        action_think="semantic_memory_distillation"
                    ))
            except Exception as e:
                # Silent failure for background memory tasks
                logger.warning(f"Semantic memory distillation failed: {e}")

            # Ensure a definitive result is parsed from Critic
            if "verdict_answer" not in res_text and "{" not in res_text:
                # Fallback if model fails to output JSON or specific key
                return f"Final Decision: {best_candidate if best_candidate else candidates[0]['answer']}\nReasoning: Synthesis of expert consensus."

            maj_info = f"\n[Majority Check]: Found common answer '{best_candidate}'" if best_candidate else "\n[Majority Check]: No clear majority."
            return f"{res_text}\n{maj_info}"
        except Exception as e:
            return f"Error during voting synthesis: {str(e)}"

class EnsembleTool(Tool):
    """
    Parallel execution tool for heterogeneous ensembles (PE + ReAct).
    Captures Working Memory (traces) for subsequent Voting.
    """
    name = "ensemble_executor"
    description = "Parallelly invokes Plan-Execute and ReAct expert teams. Returns answers and message objects (Working Memory)."
    inputs = {
        "task": {"type": "string", "description": "The specific sub-task description for the expert team to solve."},
        "react_agent_num": {"type": "integer", "description": "Number of ReAct agents to use."},
        "plan_execute_agent": {"type": "boolean", "description": "Whether to include a Plan-Execute agent."},
        "max_steps": {"type": "integer", "description": "Maximum steps for each expert agent.", "default": 30}
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, pe_worker, react_workers):
        super().__init__()
        self.pe_worker = pe_worker
        self.react_workers = react_workers
        self.agent = None # Supervisor reference

    def forward(self, task: str, react_agent_num: int = 2, plan_execute_agent: bool = True, max_steps: int = 30) -> str:
        from concurrent.futures import ThreadPoolExecutor
        from rich.panel import Panel
        from rich.text import Text
        from rich.console import Console
        console = Console()
        
        active_workers = []
        if plan_execute_agent and self.pe_worker:
            active_workers.append(self.pe_worker)
        
        num_react = min(react_agent_num, len(self.react_workers))
        active_workers.extend(self.react_workers[:num_react])
        
        console.print(Panel(Text(f"Starting Ensemble Strategy\n"
                                 f"PE Experts: {'1' if plan_execute_agent else '0'} | ReAct Experts: {num_react}\n"
                                 f"Max Steps per Expert: {max_steps}", 
                                 style="bold yellow"), title="Ensemble Initialization"))

        candidate_results = []
        
        def run_worker(worker):
            # Local Working Memory for this agent's session
            msg_obj = {
                "reasoning_chains": [],
                "tool_invocations": [],
                "intermediate_evidence": []
            }
            try:
                lower_name = worker.name.lower()
                # Determine prefix based on worker role, avoiding false positives like 'expert'
                if "react" in lower_name:
                    prefix = "ReAct"
                elif "pe" in lower_name or "plan" in lower_name:
                    prefix = "PE"
                else:
                    prefix = "Worker"
                
                console.print(Text(f"\n[{prefix} Expert] '{worker.name}' initializing session..."))
                
                final_output = None
                from .memory import ActionStep, PlanningStep
                
                # Set the worker's max_steps to the value passed to ensemble_executor
                worker.max_steps = max_steps
                for step in worker.run(task, stream=True):
                    if isinstance(step, ActionStep):
                        if step.action_think: 
                            # Token Optimization: Truncate thoughts for working memory
                            msg_obj["reasoning_chains"].append(str(step.action_think)[:200] + "...")
                            
                        if step.tool_calls:
                            for tc in step.tool_calls:
                                msg_obj["tool_invocations"].append({"tool": tc.name, "args": tc.arguments})
                        
                        obs = step.observations or "(No observation)"
                        # Token Optimization: Aggressive truncation of evidence for working memory
                        # to keep the subsequent voting/critic stage context small.
                        msg_obj["intermediate_evidence"].append(str(obs)[:400] + "..." if len(str(obs)) > 400 else str(obs))
                        
                        short_obs = str(obs)[:200] + "..." if len(str(obs)) > 200 else str(obs)
                        console.print(Text(f"[{prefix}-Step {step.step_number}] Obs: {short_obs}", style="italic grey50"))
                        
                    elif isinstance(step, PlanningStep):
                        msg_obj["reasoning_chains"].append(f"Plan: {step.plan}")
                        console.print(Text(f"[{prefix}-Plan] {step.plan[:100]}...", style="bold blue"))
                    else:
                        final_output = step
                
                return {
                    "agent_name": worker.name,
                    "answer": str(final_output),
                    "success": True,
                    "message_object": msg_obj
                }
            except Exception as e:
                return {"agent_name": worker.name, "answer": f"Error: {e}", "success": False, "message_object": msg_obj}

        with ThreadPoolExecutor(max_workers=len(active_workers)) as executor:
            future_to_worker = {executor.submit(run_worker, w): w for w in active_workers}
            for future in future_to_worker:
                data = future.result()
                status_style = "cyan" if data.get("success") else "bold red"
                console.print(Panel(Text(f"Expert: {data['agent_name']}\nConclusion: {data['answer'][:300]}...", style=status_style), title=f"Expert execution finished"))
                candidate_results.append(data)
        
        # 4. STORE Working Memory into Supervisor's hidden attribute
        if self.agent:
            self.agent._ensemble_internal_memory = candidate_results

        # 5. HIDE detailed msg_obj from the returned Observation but KEEP unique sources
        clean_results = []
        for d in candidate_results:
            # Extract unique URLs from tool invocations to provide quick source transparency
            sources = []
            msg_obj = d.get("message_object", {})
            for inv in msg_obj.get("tool_invocations", []):
                if inv.get("tool") == "crawl_page" and inv.get("args", {}).get("url"):
                    sources.append(inv["args"]["url"])
                elif inv.get("tool") == "web_search":
                    # Note: web_search doesn't have a single URL but we could log the query
                    pass
            
            clean_results.append({
                "agent_name": d["agent_name"],
                "answer": d["answer"],
                "success": d["success"],
                "sources": list(set(sources)) # Unique URLs only
            })

        return json.dumps(clean_results, indent=2, ensure_ascii=False)


class Executor(Tool):
    """
    Combined Executor: Provides current graph status and executes a node based on its 4-tuple.
    """
    name = "Executor"
    description = "Returns current Knowledge Flow Graph status AND executes a specified node task using its 4-tuple (ti, di, si, ci)."
    inputs = {
        "node_id": {"type": "string", "description": "The ID of the node (e.g., n1).", "nullable": True},
        "ti": {"type": "string", "description": "Task type: search/info-acquisition, solve, or answer.", "nullable": True},
        "di": {"type": "string", "description": "Task description.", "nullable": True},
        "si": {"type": "string", "description": "Current execution state.", "nullable": True},
        "ci": {"type": "string", "description": "Knowledge context from upstream nodes.", "nullable": True}
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    def _get_available_execution_tools(self) -> list[dict[str, Any]]:
        excluded = {
            self.name,
            "Refine",
            "final_answer",
            "Process",
            "EndProcess",
            "DeleteMemory",
            "vector_similarity_retrieve",
            "check_plan_progress",
            "update_plan_status",
        }
        available: list[dict[str, Any]] = []
        for tool_name, tool in getattr(self.agent, "tools", {}).items():
            if tool_name in excluded:
                continue
            available.append(
                {
                    "name": tool_name,
                    "description": getattr(tool, "description", ""),
                    "inputs": getattr(tool, "inputs", {}),
                }
            )
        return available

    def forward(self, node_id: Optional[str] = None, **kwargs) -> str:
        if not hasattr(self.agent, "knowledge_graph"):
            return "Knowledge graph not initialized."
        
        import json
        g = self.agent.knowledge_graph
        
        # 1. Observe Mode: Empty call returns ready nodes and status summary
        if not node_id:
            ready_nodes = []
            for nid, n in g["nodes"].items():
                if n["status"] == "pending":
                    deps = [e[0] for e in g["edges"] if e[1] == nid]
                    if all(g["nodes"].get(d, {}).get("status") == "success" for d in deps):
                        ready_nodes.append({
                            "node_id": nid,
                            "ti": n.get("type"),
                            "di": n.get("task"),
                            "si": n.get("status"),
                            "ci": n.get("context", "")
                        })
            
            status_summary = {nid: {"type": n["type"], "status": n["status"]} for nid, n in g["nodes"].items()}
            return f"FLOW_STATUS: {json.dumps(status_summary)}\nREADY_NODES: {json.dumps(ready_nodes, ensure_ascii=False)}"

        # 2. Execution Mode: Multi-step internal logic
        ti = kwargs.get("ti", "search")
        di = kwargs.get("di", "")
        # Get all upstream successful contexts (ci flow)
        upstream_contexts = "\n".join([f"Node {nid}: {n['context']}" for nid, n in g["nodes"].items() if n['status'] == 'success'])

        if ti == "answer" or ti == "solve":
            # Mode A: Logic Synthesis (No external search)
            self.agent.logger.log(f"[Node {node_id} Agent]: Synthesizing knowledge from upstream nodes...", level="INFO")
            res = self.agent.execute_tool_call("reasoning", {
                "task": f"Objective: {di}. \n\nUpstream Contexts: {upstream_contexts}. \n\nSynthesize the specific answer for this node. Be precise."
            })
            return f"EXECUTION_SUCCESS(node_id={node_id}):\n{res}"

        else:
            # Mode B: Multi-step information-acquisition trajectory
            self.agent.logger.log(
                f"[Node {node_id} Agent]: Starting multi-step task-tool trajectory...",
                level="INFO",
            )
            execution_history = ""
            available_tools = self._get_available_execution_tools()
            if not available_tools:
                return (
                    f"EXECUTION_FAILED(node_id={node_id}): "
                    "No execution tools are available for this node."
                )

            tool_catalog = json.dumps(available_tools, ensure_ascii=False)

            # Internal loop for depth (max 3 steps)
            for step in range(3):
                decision_task = textwrap.dedent(f"""
                    Node Task: {di}
                    Context: {upstream_contexts}
                    Internal Progress: {execution_history}

                    You must choose EXACTLY ONE next tool call from the available tools below.
                    Use the tool that best advances evidence gathering, validation, or task-specific interaction.
                    Do not invent tool names or arguments.

                    Available tools:
                    {tool_catalog}

                    Output ONLY a JSON tool call in this format:
                    {{"name": "actual_tool_name", "arguments": {{"arg": "value"}}}}
                """).strip()

                tool_call_json = self.agent.execute_tool_call("reasoning", {"task": decision_task})

                try:
                    tc = (
                        json.loads(tool_call_json.split("```json")[-1].split("```")[0])
                        if "```json" in tool_call_json
                        else json.loads(tool_call_json)
                    )
                    obs = self.agent.execute_tool_call(tc["name"], tc.get("arguments", {}))
                    execution_history += (
                        f"\nStep {step + 1} Action ({tc['name']}): {tc.get('arguments', {})}"
                        f"\nObservation: {obs}"
                    )
                except Exception as e:
                    execution_history += f"\nStep {step + 1} Error: {str(e)}"

                is_done = self.agent.execute_tool_call(
                    "reasoning",
                    {
                        "task": (
                            f"Based on: {execution_history}, can we fully answer '{di}' "
                            "or provide the required node context? Reply 'YES' or 'NO'."
                        )
                    },
                )
                if "YES" in is_done.upper():
                    break

            final_ci = self.agent.execute_tool_call(
                "reasoning",
                {
                    "task": (
                        f"Task: {di}. \nEvidence gathered: {execution_history}. \n\n"
                        "Distill the findings into a concise knowledge context (ci) "
                        "for downstream tasks."
                    )
                },
            )
            return f"EXECUTION_SUCCESS(node_id={node_id}):\n{final_ci}"

class Refine(Tool):
    """
    Combined Refiner: Updates node results and optionally modifies graph structure.
    """
    name = "Refine"
    description = "Updates node knowledge (ci) and status (si), and manages structure (Add/Del/Mod nodes/edges)."
    inputs = {
        "node_id": {"type": "string", "description": "ID of node to update (required).", "nullable": True},
        "knowledge_ci": {"type": "string", "description": "Distilled knowledge from execution.", "nullable": True},
        "status_si": {"type": "string", "description": "Status: 'success' or 'failed'.", "nullable": True},
        "add_nodes": {"type": "array", "description": "New nodes to add.", "nullable": True},
        "del_nodes": {"type": "array", "description": "IDs of nodes to delete.", "nullable": True},
        "add_edges": {"type": "array", "description": "New edges [source, target].", "nullable": True},
        "del_edges": {"type": "array", "description": "Edges to delete [source, target].", "nullable": True}
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    def forward(self, node_id: Optional[str] = None, **kwargs) -> str:
        if not hasattr(self.agent, "knowledge_graph"): return "Error: No graph."
        g = self.agent.knowledge_graph
        # 1. Update node
        if node_id and node_id in g["nodes"]:
            status = kwargs.get("status_si") or kwargs.get("si")
            if status:
                g["nodes"][node_id]["status"] = status
            knowledge = kwargs.get("knowledge_ci") or kwargs.get("ci")
            if knowledge:
                g["nodes"][node_id]["context"] = knowledge

        def _as_list(val):
            return val if isinstance(val, list) else []

        # 2. Add structure
        add_nodes = _as_list(kwargs.get("add_nodes"))
        for n in add_nodes:
            if not isinstance(n, dict):
                continue
            nid = n.get("node_id") or n.get("id")
            if not nid:
                continue
            n_type = n.get("type") or n.get("ti") or n.get("task_type") or "search"
            n_task = n.get("task") or n.get("di") or n.get("description") or n.get("content") or ""
            n_status = n.get("status") or n.get("si") or "pending"
            n_context = n.get("context") or n.get("ci") or ""
            g["nodes"][nid] = {
                "node_id": nid,
                "type": n_type,
                "task": n_task,
                "status": n_status,
                "context": n_context,
            }

        add_edges = _as_list(kwargs.get("add_edges"))
        for e in add_edges:
            s = t = None
            if isinstance(e, dict):
                s = e.get("source") or e.get("from")
                t = e.get("target") or e.get("to")
            elif isinstance(e, (list, tuple)) and len(e) == 2:
                s, t = e
            if s and t:
                edge = [str(s), str(t)]
                if edge not in g["edges"]:
                    g["edges"].append(edge)

        # 3. Delete structure
        del_nodes = _as_list(kwargs.get("del_nodes"))
        for nid in del_nodes:
            g["nodes"].pop(nid, None)
            g["edges"] = [e for e in g["edges"] if e[0] != nid and e[1] != nid]

        del_edges = _as_list(kwargs.get("del_edges"))
        for e in del_edges:
            s = t = None
            if isinstance(e, dict):
                s = e.get("source") or e.get("from")
                t = e.get("target") or e.get("to")
            elif isinstance(e, (list, tuple)) and len(e) == 2:
                s, t = e
            if s and t:
                edge = [str(s), str(t)]
                if edge in g["edges"]:
                    g["edges"].remove(edge)

        # 4. Return updated status summary to avoid empty Executor() calls
        import json
        ready_nodes = []
        for nid, n in g["nodes"].items():
            if n["status"] == "pending":
                deps = [e[0] for e in g["edges"] if e[1] == nid]
                if all(g["nodes"].get(d, {}).get("status") == "success" for d in deps):
                    ready_nodes.append({
                        "node_id": nid,
                        "ti": n.get("type"),
                        "di": n.get("task"),
                        "si": n.get("status"),
                        "ci": n.get("context", "")
                    })
        
        status_summary = {nid: {"type": n["type"], "status": n["status"]} for nid, n in g["nodes"].items()}
        status_info = f"FLOW_STATUS: {json.dumps(status_summary)}\nREADY_NODES: {json.dumps(ready_nodes, ensure_ascii=False)}"
                
        return f"Refine completed for node {node_id or 'Graph Structure'}. Graph updated.\n\nUPDATED_{status_info}"

class UpdatePlanStatus(Tool):
    name = "update_plan_status"
    description = "Updates the status and result of a planned task."
    inputs = {
        "task_id": {"type": "integer", "description": "The ID of the task to update."},
        "status": {"type": "string", "description": "New status: pending, running, completed, failed."},
        "result": {"type": "string", "description": "The result or feedback of the task execution.", "nullable": True}
    }
    output_type = "string"

    def __init__(self, agent=None):
        super().__init__()
        self.agent = agent

    def forward(self, task_id: int, status: str, result: str = None) -> str:
        if self.agent is None:
            return "Error: Tool not linked to an agent."
        
        # Access tasks from planning module
        if not hasattr(self.agent, "planning") or not hasattr(self.agent.planning, "orchestra_tasks"):
            return "Error: Agent planning module or orchestra_tasks not found."
            
        tasks = self.agent.planning.orchestra_tasks
        if task_id < 0 or task_id >= len(tasks):
            return f"Error: Task ID {task_id} not found."
        
        task = tasks[task_id]
        task["status"] = status
        if result is not None:
            task["result"] = result
        return f"Task {task_id} updated to {status}."

class CheckPlanProgress(Tool):
    name = "check_plan_progress"
    description = "Lists all planned tasks and their current status to help decide the next step."
    inputs = {}
    output_type = "string"

    def __init__(self, agent=None):
        super().__init__()
        self.agent = agent

    def forward(self) -> str:
        if self.agent is None:
            return "Error: Tool not linked to an agent."
            
        if not hasattr(self.agent, "planning") or not hasattr(self.agent.planning, "orchestra_tasks"):
            return "No tasks planned yet or planning module not available."
            
        tasks = self.agent.planning.orchestra_tasks
        if not tasks:
            return "The plan is currently empty."
        
        summary = "Current Execution Plan Status:\n"
        for t in tasks:
            summary += f"ID {t['id']}: [{t['status'].upper()}] {t['description']} (Category: {t['category']}, Result: {t['result'] or 'N/A'})\n"
        return summary

__all__ = [
    "AUTHORIZED_TYPES",
    "Tool",
    "FinalAnswerTool",
    "VectorSimilarityRetrieve",
    "Reasoning",
    "Process",
    "EndProcess",
    "DeleteMemory",
    "VoteTool",
    "EnsembleTool",
    "Executor",
    "Refine",
    "UpdatePlanStatus",
    "CheckPlanProgress"
]
