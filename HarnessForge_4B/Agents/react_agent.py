#!/usr/bin/env python
# coding=utf-8

from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional

try:
    import json_repair
except ModuleNotFoundError:
    class _JsonRepairFallback:
        @staticmethod
        def loads(text: str):
            return json.loads(text)

    json_repair = _JsonRepairFallback()


DEFAULT_SYSTEM_PROMPT = """
You are a ReAct Expert.
Loop: Thought -> Action -> Observation.
There is no planning phase, no summary phase, and no external tool use.
You solve the task through iterative reasoning and internal actions only.

At every step, output exactly one JSON object with this schema:
{
  "think": "brief reasoning for the next move",
  "action": "short action name",
  "action_input": "payload for that action"
}

Guidelines:
- Use short action names such as ANALYZE, DRAFT, REVISE, VERIFY, or FINAL_ANSWER.
- Use FINAL_ANSWER only when you are ready to commit to the final answer.
- Keep action_input focused on the immediate payload for that action.

Rules:
- Do not use markdown or code fences.
- Do not mention tools, execution, or internet access.
- Output exactly one JSON object and nothing else.
""".strip()


DEFAULT_FINAL_PROMPT = """
You must end now.
Use the accumulated ReAct history and return one strict JSON object with action FINAL_ANSWER.
Put the final answer only in action_input.
""".strip()


DEFAULT_STEP_PROMPT = """
Continue the ReAct loop for the current task.

Use only the prior Thought/Action/Observation trajectory above as context.
Do not repeat identical failed attempts.
Return exactly one JSON object with keys think, action, action_input.
Use FINAL_ANSWER only when ready to finish.
""".strip()


FINAL_ACTIONS = {
    "FINAL_ANSWER",
    "FINAL_SQL",
    "ANSWER",
}


@dataclass
class ReActStep:
    input_tokens: int = 0
    output_tokens: int = 0
    model_input_messages: List[Dict[str, Any]] | None = None
    model_output_raw: Any | None = None
    step_number: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    duration: float | None = None
    thought: str = ""
    action: str = ""
    action_input: Any = None
    observation: str = ""
    final_answer: str | None = None
    reasoning_content: str | None = None
    error: str | None = None

    def dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model_input_messages": self.model_input_messages,
            "model_output_raw": self.model_output_raw,
            "step_number": self.step_number,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "final_answer": self.final_answer,
            "reasoning_content": self.reasoning_content,
            "error": self.error,
        }

    def to_messages(self) -> List[Dict[str, Any]]:
        if isinstance(self.action_input, (dict, list)):
            action_input_text = json.dumps(self.action_input, ensure_ascii=False)
        else:
            action_input_text = str(self.action_input or "")

        assistant_text = (
            f"Thought: {self.thought}\n"
            f"Action: {self.action}\n"
            f"Action Input: {action_input_text}"
        )
        messages: List[Dict[str, Any]] = [
            {"role": "assistant", "content": [{"type": "text", "text": assistant_text}]}
        ]
        if self.observation:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": f"Observation: {self.observation}"}]}
            )
        if self.error:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": f"Error: {self.error}"}]}
            )
        return messages


class PureReActAgent:
    def __init__(
        self,
        model,
        max_steps: int = 8,
        system_prompt: Optional[str] = None,
        step_prompt: Optional[str] = None,
        final_prompt: Optional[str] = None,
    ):
        self.model = model
        self.max_steps = max_steps
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.step_prompt = step_prompt or DEFAULT_STEP_PROMPT
        self.final_prompt = final_prompt or DEFAULT_FINAL_PROMPT
        self.task: Optional[str] = None
        self.step_number = 0
        self.trajectory: List[ReActStep] = []

    def reset(self) -> None:
        self.step_number = 0
        self.trajectory = []

    def run(self, task: str, stream: bool = False) -> Any:
        self.reset()
        self.task = task
        if stream:
            return self._run(task)
        return deque(self._run(task), maxlen=1)[0]

    def build_messages(self) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": [{"type": "text", "text": self.system_prompt}]},
            {"role": "user", "content": [{"type": "text", "text": f"Task:\n{self.task or ''}"}]},
        ]
        for step in self.trajectory:
            messages.extend(step.to_messages())
        return messages

    def _run(self, task: str) -> Generator[Any, None, None]:
        final_answer = None
        while final_answer is None and self.step_number < self.max_steps:
            self.step_number += 1
            step_start_time = time.time()
            step = ReActStep(step_number=self.step_number, start_time=step_start_time)

            try:
                input_messages = self.build_messages() + [self._build_step_instruction()]
                step.model_input_messages = input_messages

                model_message = self.model(input_messages)
                step.model_output_raw = getattr(model_message, "raw", None)
                step.reasoning_content = getattr(model_message, "reasoning_content", None)
                if hasattr(self.model, "get_token_counts"):
                    counts = self.model.get_token_counts()
                    step.input_tokens = counts.get("input_token_count", 0) or 0
                    step.output_tokens = counts.get("output_token_count", 0) or 0

                thought, action, action_input = self._parse_model_message(model_message)
                step.thought = thought
                step.action = action
                step.action_input = action_input

                final_answer, observation = self._apply_action(action, action_input)
                step.observation = observation
                step.final_answer = final_answer
            except Exception as exc:
                step.error = str(exc)
                step.observation = f"Invalid step format or action: {exc}"
            finally:
                step.end_time = time.time()
                step.duration = step.end_time - step_start_time
                self.trajectory.append(step)
                yield step

        if final_answer is None:
            final_answer = self._force_final_answer(task)

        yield final_answer

    def _build_step_instruction(self) -> Dict[str, Any]:
        return {"role": "user", "content": [{"type": "text", "text": self.step_prompt}]}

    def _parse_model_message(self, model_message) -> tuple[str, str, str]:
        raw_content = getattr(model_message, "content", "") or ""
        if not isinstance(raw_content, str):
            raw_content = str(raw_content)

        parsed = self._load_json_object(raw_content)
        thought = str(parsed.get("thought") or parsed.get("think") or "").strip()
        action = str(parsed.get("action") or "").strip().upper()
        action_input = parsed.get("action_input")

        if action_input is None:
            if "sql" in parsed:
                action_input = parsed["sql"]
            elif "answer" in parsed:
                action_input = parsed["answer"]

        if isinstance(action_input, dict):
            if "sql" in action_input:
                action_input = action_input["sql"]
            elif "answer" in action_input:
                action_input = action_input["answer"]
            else:
                action_input = json.dumps(action_input, ensure_ascii=False)
        elif isinstance(action_input, list):
            action_input = json.dumps(action_input, ensure_ascii=False)
        elif action_input is None:
            action_input = ""
        else:
            action_input = str(action_input)

        if not action:
            raise ValueError("action is empty")

        return thought, action, action_input.strip()

    def _load_json_object(self, text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json_repair.loads(cleaned)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match is None:
                raise ValueError("model response did not contain a JSON object")
            data = json_repair.loads(match.group(0))

        if isinstance(data, list):
            if not data or not isinstance(data[0], dict):
                raise ValueError("model response JSON list does not start with an object")
            data = data[0]
        if not isinstance(data, dict):
            raise ValueError("model response JSON is not an object")
        return data

    def _normalize_answer(self, text: str) -> str:
        return " ".join(text.strip().split())

    def _validate_final_answer(self, answer: str) -> List[str]:
        issues: List[str] = []
        if not answer:
            issues.append("final answer is empty")
        return issues

    def _latest_candidate_answer(self) -> str:
        for step in reversed(self.trajectory):
            if isinstance(step.action_input, str) and step.action_input.strip():
                return self._normalize_answer(step.action_input)
        return ""

    def _is_final_action(self, action: str) -> bool:
        return action in FINAL_ACTIONS

    def _apply_action(self, action: str, action_input: str) -> tuple[Optional[str], str]:
        normalized_input = self._normalize_answer(action_input)

        if self._is_final_action(action):
            issues = self._validate_final_answer(normalized_input)
            if issues:
                return None, "FINAL_ANSWER rejected: " + "; ".join(issues)
            return normalized_input, "Final answer accepted."

        if not normalized_input:
            return None, "Action noted. No concrete payload provided yet."

        if any(token in action for token in {"DRAFT", "REVISE", "CANDIDATE", "ANSWER", "SQL"}):
            return None, "Candidate noted. Continue refining or finalize when ready."

        if "VERIFY" in action or "CHECK" in action or "CRITIQUE" in action:
            return None, "Verification noted. Update the candidate if needed, or finalize."

        return None, "Action noted. Continue reasoning from the updated state."

    def _force_final_answer(self, task: str) -> str:
        candidate_answer = self._latest_candidate_answer().strip()
        if candidate_answer:
            return candidate_answer

        input_messages = self.build_messages() + [
            {"role": "user", "content": [{"type": "text", "text": f"{self.final_prompt}\n\nTask:\n{task}"}]}
        ]
        model_message = self.model(input_messages)
        _, action, action_input = self._parse_model_message(model_message)
        if not self._is_final_action(action):
            raw_content = getattr(model_message, "content", "") or ""
            sql_match = re.search(r"(WITH[\s\S]+|SELECT[\s\S]+)", raw_content, flags=re.IGNORECASE)
            if sql_match:
                return self._normalize_answer(sql_match.group(1))
            return self._normalize_answer(raw_content)
        return self._normalize_answer(action_input)
