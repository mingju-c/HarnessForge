from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, PlanningStep, SummaryStep
from Agents.tools import Tool


JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
JSON_ARRAY_PATTERN = re.compile(r"\[.*\]", re.DOTALL)


class CoSightBaseTool(Tool):
    """Shared utilities for the parallel investigation tools."""

    _shared_buffer: List[Dict[str, Any]] = []

    def __init__(
        self,
        model: Any,
        *,
        verbose: bool = True,
        prompt_templates: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.verbose = verbose
        self.prompt_templates = prompt_templates or {}
        self._logger = logging.getLogger(f"module_action.{self.name}")

    def set_prompt_templates(self, prompt_templates: Dict[str, Any]) -> None:
        self.prompt_templates = prompt_templates or {}

    def _internal_prompt_templates(self) -> Dict[str, Any]:
        return self.prompt_templates.get("coordination_internal") or self.prompt_templates.get("cosight_internal", {})

    def _populate_template(self, template: str, variables: Dict[str, Any]) -> str:
        if not template:
            return ""
        compiled_template = Template(template, undefined=StrictUndefined)
        return compiled_template.render(**variables)

    def _log(self, message: str) -> None:
        if self.verbose:
            self._logger.info(message)

    def _short(self, text: str, limit: int = 220) -> str:
        text = (text or "").replace("\n", " ").strip()
        return text if len(text) <= limit else text[:limit] + "..."

    def _render_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part)
        return str(content)

    def _llm(self, prompt: str) -> str:
        self._log(f"[{self.name}.llm] prompt={self._short(prompt, 160)}")
        started = time.time()
        response = self.model(
            [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        )
        elapsed = time.time() - started
        output = self._render_content_text(getattr(response, "content", response))
        self._log(f"[{self.name}.llm] done in {elapsed:.2f}s, out={self._short(output, 200)}")
        return output

    def _consensus_answer(self, packages: List[Dict[str, Any]]) -> tuple[str, int]:
        answers = []
        for pkg in packages:
            answer = str(pkg.get("answer", "")).strip()
            if answer:
                answers.append(answer)
        if not answers:
            return "", 0
        counts = Counter(answers)
        answer, support = counts.most_common(1)[0]
        return answer, support


class ExpertParallelTool(CoSightBaseTool):
    """
    Run multiple expert ToolCallingAgents in parallel and collect their findings.
    """

    name = "expert_parallel"
    description = "Spawn multiple experts to solve a task in parallel and gather their findings."
    inputs = {
        "task": {"type": "string", "description": "User question/task"},
        "num_expert": {"type": "integer", "description": "Number of experts, e.g. 1-4"},
        "facts_snapshot": {"type": "string", "description": "Already verified global facts", "nullable": True},
        "failure_context": {"type": "string", "description": "Context from previous failed rounds", "nullable": True},
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(
        self,
        model: Any,
        agents: List[Any],
        *,
        verbose: bool = True,
        prompt_templates: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(model, verbose=verbose, prompt_templates=prompt_templates)
        self.agents = agents

    def _collect_tool_records(self, agent: Any) -> List[Dict[str, Any]]:
        tool_records: List[Dict[str, Any]] = []
        for step in getattr(agent.memory, "steps", []):
            if not isinstance(step, ActionStep):
                continue
            if not getattr(step, "tool_calls", None):
                continue
            for tool_call in step.tool_calls:
                tool_records.append(
                    {
                        "step": getattr(step, "step_number", None),
                        "tool": getattr(tool_call, "name", ""),
                        "arguments": getattr(tool_call, "arguments", {}),
                        "observation": getattr(step, "observations", ""),
                    }
                )
        return tool_records

    def _collect_trace(self, agent: Any) -> Dict[str, Any]:
        trace: Dict[str, Any] = {
            "plan": "",
            "summaries": [],
            "tool_invocations": [],
            "observations": [],
        }
        for step in getattr(agent.memory, "steps", []):
            if isinstance(step, PlanningStep) and step.plan and not trace["plan"]:
                trace["plan"] = self._short(step.plan, 500)
                continue
            if isinstance(step, SummaryStep) and step.summary:
                trace["summaries"].append(self._short(step.summary, 300))
                continue
            if not isinstance(step, ActionStep):
                continue
            if step.tool_calls:
                for tool_call in step.tool_calls[:6]:
                    trace["tool_invocations"].append(
                        {
                            "name": getattr(tool_call, "name", ""),
                            "arguments": getattr(tool_call, "arguments", {}),
                        }
                    )
            if step.observations:
                trace["observations"].append(self._short(step.observations, 350))

        trace["summaries"] = trace["summaries"][-2:]
        trace["tool_invocations"] = trace["tool_invocations"][-8:]
        trace["observations"] = trace["observations"][-4:]
        return trace

    def _extract_notes(self, task: str, tool_records: List[Dict[str, Any]]) -> List[str]:
        template = self._internal_prompt_templates().get("extract_notes", {}).get("prompt")
        if not template:
            return [f"Executed {len(tool_records)} tool calls."]

        prompt = self._populate_template(
            template,
            {
                "task": task,
                "tool_records": json.dumps(tool_records, ensure_ascii=False),
            },
        )
        raw = self._llm(prompt)
        try:
            match = JSON_OBJECT_PATTERN.search(raw)
            data = json.loads(match.group(0)) if match else json.loads(raw)
            notes = data.get("notes", [])
            if isinstance(notes, list) and notes:
                return [str(item) for item in notes]
        except Exception:
            pass
        return [raw.strip()] if raw.strip() else []

    def _extract_answer_and_facts(
        self,
        agent: Any,
        task: str,
        notes: List[str],
        facts_snapshot: Optional[str],
        tool_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        template = self._internal_prompt_templates().get("expert", {}).get("prompt")
        if not template:
            return {
                "expert_id": agent.name,
                "answer": str(getattr(agent.memory.steps[-1], "action_output", "") or "").strip(),
                "facts_local": [],
                "notes": notes,
                "tool_records": tool_records,
            }

        prompt = self._populate_template(
            template,
            {
                "expert_id": agent.name,
                "task": task,
                "facts_snapshot": facts_snapshot or "(none)",
                "notes": json.dumps(notes, ensure_ascii=False),
            },
        )
        raw = self._llm(prompt)
        try:
            match = JSON_OBJECT_PATTERN.search(raw)
            data = json.loads(match.group(0)) if match else json.loads(raw)
            return {
                "expert_id": agent.name,
                "answer": data.get("answer", "").strip(),
                "facts_local": data.get("facts_local", []),
                "notes": notes,
                "tool_records": tool_records,
            }
        except Exception:
            return {
                "expert_id": agent.name,
                "answer": raw.strip(),
                "facts_local": [],
                "notes": notes,
                "tool_records": tool_records,
            }

    def _run_one_agent(
        self,
        agent: Any,
        task: str,
        facts_snapshot: Optional[str],
        failure_context: Optional[str],
    ) -> Dict[str, Any]:
        if hasattr(agent, "memory"):
            agent.memory.reset()

        augmented_task = task
        if failure_context:
            augmented_task = f"{task}\n\nContext from previous attempts: {failure_context}"

        result = agent.run(augmented_task, reset=True)
        tool_records = self._collect_tool_records(agent)
        trace = self._collect_trace(agent)
        notes = self._extract_notes(task, tool_records)
        package = self._extract_answer_and_facts(agent, task, notes, facts_snapshot, tool_records)
        package["trace"] = trace
        if not package.get("answer"):
            package["answer"] = str(result).strip()
        return package

    def forward(
        self,
        task: str,
        num_expert: int = 3,
        facts_snapshot: Optional[str] = None,
        failure_context: Optional[str] = None,
        **_: Any,
    ) -> str:
        active_agents = list(self.agents[: max(1, min(num_expert, len(self.agents)))])
        if not active_agents:
            raise RuntimeError("ExpertParallelTool has no agents configured.")

        self._log(f"[ExpertParallel] Running {len(active_agents)} experts for task: {self._short(task)}")
        packages: List[Dict[str, Any]] = []
        CoSightBaseTool._shared_buffer = []

        with ThreadPoolExecutor(max_workers=len(active_agents)) as executor:
            futures = [
                executor.submit(
                    self._run_one_agent,
                    agent,
                    task,
                    facts_snapshot,
                    failure_context,
                )
                for agent in active_agents
            ]
            for future in as_completed(futures):
                try:
                    packages.append(future.result())
                except Exception as exc:
                    self._log(f"[ExpertParallel] Expert failed: {exc}")

        packages.sort(key=lambda item: str(item.get("expert_id", "")))
        CoSightBaseTool._shared_buffer = packages

        payload = [
            {
                "expert_id": pkg.get("expert_id"),
                "answer": pkg.get("answer", ""),
                "notes": pkg.get("notes", []),
                "trace": pkg.get("trace", {}),
            }
            for pkg in packages
        ]
        return json.dumps(payload, ensure_ascii=False)


class CAMVTool(CoSightBaseTool):
    """
    Conflict-aware synthesis of expert findings.

    This keeps the overall coordination protocol intact, but removes the web/crawl
    verification dependency that does not exist in the current harness codebase.
    """

    name = "camv"
    description = "Verify and synthesize findings from multiple experts using the CAMV pipeline."
    inputs = {
        "task": {"type": "string", "description": "User question/task"},
        "expert_packages": {"type": "string", "description": "JSON string of findings from expert_parallel"},
        "facts_snapshot": {"type": "string", "description": "Already verified global facts to build upon", "nullable": True},
    }
    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(
        self,
        model: Any,
        *,
        theta_default: int = 2,
        verbose: bool = True,
        prompt_templates: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(model, verbose=verbose, prompt_templates=prompt_templates)
        self.theta_default = theta_default

    def _load_packages(self, expert_packages: Any) -> List[Dict[str, Any]]:
        if CoSightBaseTool._shared_buffer:
            return list(CoSightBaseTool._shared_buffer)

        if isinstance(expert_packages, str):
            try:
                payload = json.loads(expert_packages)
            except json.JSONDecodeError as exc:
                raise ValueError(f"expert_packages is not valid JSON: {exc}") from exc
        else:
            payload = expert_packages

        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        raise ValueError(f"Unsupported type for expert_packages: {type(expert_packages)}")

    def _normalize_claims(self, task: str, facts_local: List[Any]) -> List[Dict[str, Any]]:
        template = self._internal_prompt_templates().get("normalization", {}).get("prompt")
        if not template or not facts_local:
            return []

        prompt = self._populate_template(
            template,
            {
                "task": task,
                "claims": json.dumps(facts_local, ensure_ascii=False),
            },
        )
        raw = self._llm(prompt)
        try:
            match = JSON_ARRAY_PATTERN.search(raw)
            data = json.loads(match.group(0)) if match else json.loads(raw)
            normalized = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "key": item.get("key", ""),
                        "value": item.get("value", ""),
                        "confidence": float(item.get("confidence", 0.0)),
                        "source_url": item.get("source_url", ""),
                        "source_snippet": item.get("source_snippet", ""),
                    }
                )
            return normalized
        except Exception:
            return []

    def _vote(
        self,
        norm_packages: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        by_key: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for package in norm_packages:
            expert_id = package.get("expert_id", "unknown")
            for claim in package.get("normalized_claims", []):
                key = str(claim.get("key", "")).strip()
                value = str(claim.get("value", "")).strip()
                if not key or not value:
                    continue
                by_key.setdefault(key, {}).setdefault(value, []).append(
                    {**claim, "expert_id": expert_id}
                )

        anchors: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []
        for key, value_map in by_key.items():
            candidates = []
            for value, entries in value_map.items():
                candidates.append(
                    {
                        "value": value,
                        "support": len(entries),
                        "confidence": sum(float(e.get("confidence", 0.0)) for e in entries) / len(entries),
                        "hint_url": max(entries, key=lambda e: float(e.get("confidence", 0.0))).get("source_url", ""),
                        "hint_snippet": max(entries, key=lambda e: float(e.get("confidence", 0.0))).get("source_snippet", ""),
                    }
                )
            candidates.sort(key=lambda item: (item["support"], item["confidence"]), reverse=True)
            if len(candidates) == 1 or candidates[0]["support"] >= self.theta_default:
                best = candidates[0]
                anchors.append({"key": key, **best})
            else:
                conflicts.append({"key": key, "candidates": candidates})
        return anchors, conflicts

    def _supported_snapshot(
        self,
        anchors: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        packages: List[Dict[str, Any]],
    ) -> str:
        lines: List[str] = []
        if anchors:
            lines.append("Anchors:")
            for anchor in anchors:
                lines.append(
                    f"- {anchor['key']} = {anchor['value']} "
                    f"(support={anchor['support']}, confidence={anchor['confidence']:.2f})"
                )

        if conflicts:
            lines.append("Conflicts:")
            for conflict in conflicts:
                rendered = ", ".join(
                    f"{candidate['value']} (support={candidate['support']})"
                    for candidate in conflict["candidates"]
                )
                lines.append(f"- {conflict['key']}: {rendered}")

        consensus_answer, support = self._consensus_answer(packages)
        if consensus_answer:
            lines.append(f"Consensus answer candidate (support={support}): {consensus_answer}")

        if not lines:
            for package in packages:
                answer = str(package.get("answer", "")).strip()
                if answer:
                    lines.append(f"- {package.get('expert_id', 'expert')}: {answer}")
        return "\n".join(lines).strip()

    def _decision_synthesis(self, task: str, supported_snapshot: str) -> str:
        template = self._internal_prompt_templates().get("decision", {}).get("prompt")
        if not template:
            return ""

        prompt = self._populate_template(
            template,
            {
                "task": task,
                "supported_snapshot": supported_snapshot,
            },
        )
        raw = self._llm(prompt)
        try:
            match = JSON_OBJECT_PATTERN.search(raw)
            data = json.loads(match.group(0)) if match else json.loads(raw)
            if data.get("ready") and data.get("final_answer"):
                return str(data["final_answer"]).strip()
        except Exception:
            return ""
        return ""

    def _fallback_synthesis(self, task: str, supported_snapshot: str) -> str:
        template = self._internal_prompt_templates().get("fallback", {}).get("prompt")
        if not template:
            return supported_snapshot
        prompt = self._populate_template(
            template,
            {
                "task": task,
                "supported_snapshot": supported_snapshot,
            },
        )
        return self._llm(prompt).strip()

    def forward(
        self,
        task: str,
        expert_packages: Any,
        facts_snapshot: Optional[str] = None,
        **_: Any,
    ) -> str:
        packages = self._load_packages(expert_packages)
        if not packages:
            raise RuntimeError("CAMVTool received no expert packages.")

        norm_packages = []
        for package in packages:
            package_copy = dict(package)
            package_copy["normalized_claims"] = self._normalize_claims(
                task,
                list(package.get("facts_local", []) or []),
            )
            norm_packages.append(package_copy)

        anchors, conflicts = self._vote(norm_packages)
        supported_snapshot = self._supported_snapshot(anchors, conflicts, packages)
        if facts_snapshot:
            supported_snapshot = (
                f"Prior verified facts:\n{facts_snapshot}\n\nCurrent round:\n{supported_snapshot}"
            )

        synthesized_answer = self._decision_synthesis(task, supported_snapshot)
        if not synthesized_answer:
            consensus_answer, support = self._consensus_answer(packages)
            if consensus_answer:
                synthesized_answer = consensus_answer
                supported_snapshot += f"\n\nChosen by consensus support={support}."
            else:
                synthesized_answer = self._fallback_synthesis(task, supported_snapshot)

        expert_lines = []
        for package in packages:
            answer = str(package.get("answer", "")).strip()
            if answer:
                expert_lines.append(f"- {package.get('expert_id', 'expert')}: {answer}")

        sections = [
            f"Recommended final answer: {synthesized_answer}".strip(),
            "Evidence summary:",
            supported_snapshot or "(none)",
        ]
        if expert_lines:
            sections.extend(["Expert outputs:"] + expert_lines)
        return "\n".join(section for section in sections if section.strip())


__all__ = ["ExpertParallelTool", "CAMVTool"]
