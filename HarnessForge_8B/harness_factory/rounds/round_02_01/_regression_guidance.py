from __future__ import annotations

from typing import Any


_MARKER = "Round02.01 regression fixes from trajectory audit"


SYSTEM_GUIDANCE = f"""

{_MARKER}:
- ToolHop slot discipline: for relation-chain questions, never run string/date/math tools on the original question phrase, source entity, placeholder, or unresolved relation. First bind the exact intermediate entity/value from an observation. If a lookup returns empty/unknown, try one schema-valid repair such as canonical capitalization, full-name variant, observed alias, singular/plural enum repair, or a different listed lookup before declaring unavailable.
- ToolHop transformation discipline: before/after dates must move in the requested direction; winter timezone means standard-time/dated-winter arguments when the schema permits it; date answers should use the requested granularity. If a calculator returns an ISO datetime for a date question, the final answer should be the YYYY-MM-DD date part.
- SearchQA discipline: stop after decisive evidence; do not drift into broad era/entity searches after a direct result supports the requested answer. Return the shortest raw span matching the requested type, preserving the evidence surface form for names, years, titles, and word-numbers.
- EnvScaler discipline: complete_task is part of the task. After all high-value required writes are observed successful, call complete_task promptly. If step budget is getting tight, prefer a partial-but-terminal complete_task over extra reads, optional checker calls, or repeated unavailable helpers.
- Checker discipline: non-environment checker tools cannot create evidence or complete state. Use the harness checker at most once for the same uncertainty, then either repair with a real schema-listed tool, finalize, or complete_task.
"""


STEP_GUIDANCE = """

Round02.01 high-yield step checks:
- If this is ToolHop and the next call is a transformation/extraction/calculation, verify in think that the input is an observed slot from the intended chain, not the task wording or a parent/source entity.
- If a person/publication/royal/sports lookup says Unknown or not found, try one canonical name variant already implied by observations before unavailable prose. Do not spend the rest of the run looping on the same miss.
- For date arithmetic, sanity-check direction: "before" must produce an earlier date, "after" a later date. Repair arguments if the observation contradicts that direction.
- For SearchQA, avoid repeating the same query more than twice. When evidence supports a short raw answer, call final_answer instead of expanding the search space.
- For EnvScaler/stateful tasks, keep a tiny checklist of required writes. Unknown tool or success:false does not close a row; switch to another listed tool or repair the ID. Once the main rows are done, call complete_task. Near the last few steps, call complete_task rather than leaving the task unterminated.
"""


FINAL_GUIDANCE = """

Round02.01 final-answer fixes:
- Return only the requested value. No explanations, no "cannot determine" prose if a supported raw candidate exists.
- Normalize granularity, not meaning: date question -> YYYY-MM-DD when an ISO/date-calculator value is available; year question -> bare year; count/ASCII/math question -> bare number; title/name question -> shortest exact title/name span.
- Strip harmless machine time suffixes for date-only questions, e.g. 1463-02-23T00:00:00 -> 1463-02-23. Do not convert YYYY-MM-DD into prose dates.
- If the task asks for a word-number and the evidence contains the word form, prefer that exact word form over digits.
- For stateful tasks, if complete_task is available and required writes have succeeded, use complete_task rather than a natural-language final answer.
"""


def _append_once(text: Any, addition: str) -> str:
    current = "" if text is None else str(text)
    if _MARKER in current or addition.strip() in current:
        return current
    return current.rstrip() + addition


def apply_round02_01_regression_fixes(
    prompt_templates: dict[str, Any],
    *,
    checker_name: str | None = None,
) -> dict[str, Any]:
    """Append shared cross-benchmark fixes without overwriting candidate-specific prompts."""

    if not isinstance(prompt_templates, dict):
        return prompt_templates

    checker_line = ""
    if checker_name:
        checker_line = (
            f"\n- The optional checker for this harness is {checker_name}. "
            "Do not call it repeatedly for the same uncertainty; after one checker result, use a real tool or terminate when ready."
        )

    prompt_templates["system_prompt"] = _append_once(
        prompt_templates.get("system_prompt", ""),
        SYSTEM_GUIDANCE + checker_line,
    )

    step = prompt_templates.get("step")
    if isinstance(step, dict):
        step["pre_messages"] = _append_once(step.get("pre_messages", ""), STEP_GUIDANCE)

    final_answer = prompt_templates.get("final_answer")
    if isinstance(final_answer, dict):
        final_answer["post_messages"] = _append_once(
            final_answer.get("post_messages", ""),
            FINAL_GUIDANCE,
        )

    return prompt_templates
