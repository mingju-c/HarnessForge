from __future__ import annotations

from typing import Any

from module_action.base_action import ActionContext, BaseActionProvider


SINGLE_REACT_PROMPT_TEMPLATES = {
    "system_prompt": (
        "You are a SQLite expert solving BIRD Text-to-SQL tasks with tool calls.\n"
        "You must think step by step and call tools to inspect schema and validate SQL.\n"
        "IMPORTANT: YOU SHOULD NEVER ASK FOR HUMAN HELP OR USE THE INTERNET TO SOLVE THIS TASK.\n\n"
        "Output MUST be strict JSON:\n"
        "{\n"
        '  \"think\": \"...\",\n'
        '  \"tools\": [\n'
        "    {\n"
        '      \"name\": \"tool_name\",\n'
        '      \"arguments\": { ... }\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "1. Use valid SQLite SQL only.\n"
        "2. Prefer calling run_sql before final_answer.\n"
        "3. final_answer must contain a single-line SQL in arguments.answer.\n"
        "4. Do not ask human for help.\n"
        "5. If SQL execution fails, revise SQL based on the error and retry.\n"
        "6. When a candidate SQL is already validated and satisfies the task, finish immediately by calling final_answer in the next step.\n"
        "7. The SELECT projection must match the question exactly; never add extra columns unless explicitly requested.\n"
        "8. For rank/sort/limit questions (highest/lowest/top/bottom), ensure ORDER BY direction and LIMIT strictly match the question.\n"
        "9. For categorical filters (county/type/status), verify exact values with tools (e.g., DISTINCT/sample rows) before finalizing SQL.\n"
        "10. Prefer the semantically exact column from schema/question wording; do not substitute a related-but-different column.\n"
        "11. Prefer calling multiple independent tools in one step when it can reduce total steps.\n"
        "12. During SQL debugging, you may call 2-4 run_sql tools with different candidate SQL variants in one step.\n"
        "13. Never combine final_answer with any other tool in the same step.\n"
        "14. Do not finalize with SELECT NULL unless the task explicitly asks for NULL output.\n"
        "15. Do not relax or replace a specific categorical condition with a broader one unless verified equivalent.\n"
        "16. Do not add GROUP BY / AVG / DISTINCT unless required by the question semantics.\n"
        "17. If the question requires rank/top/lowest/extreme, preserve the exact ranking semantics required by wording.\n"
        "18. Do not keep validating forever. After one direct target query succeeds, do at most one additional sanity-check step unless there is a real contradiction.\n"
        "19. If two successful validations agree on the answer shape and key constraints, call final_answer immediately.\n"
        "20. For scalar-value questions, a successful target query plus one consistency check is enough; stop early.\n\n"
        "Available tools:\n"
        "{%- for tool in tools.values() %}\n"
        "- {{ tool.name }}: {{ tool.description }}\n"
        "    Inputs: {{ tool.inputs }}\n"
        "    Output: {{ tool.output_type }}\n"
        "{%- endfor %}"
    ),
    "final_answer": {
        "pre_messages": "You must produce the final SQL answer.",
        "post_messages": (
            "Return JSON only:\n"
            "{\n"
            '  \"think\": \"brief reasoning\",\n'
            '  \"answer\": \"single-line SQLite SQL\"\n'
            "}\n"
            "Task:\n"
            "{{task}}"
        ),
    },
    "step": {
        "pre_messages": (
            "Continue solving the SQL task based on plan/history.\n\n"
            "Tool JSON schema:\n"
            "{{tool_functions_json}}\n\n"
            "Task:\n"
            "{{task}}\n\n"
            "Output format (strict):\n"
            "{\n"
            '  \"think\": \"brief reasoning\",\n'
            '  \"tools\": [\n'
            "    {\n"
            '      \"name\": \"list_tables | describe_table | run_sql | final_answer\",\n'
            '      \"arguments\": {}\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Step policy:\n"
            "1) Call 1 to 5 tools in this step; prefer several tools when exploring/debugging alternatives.\n"
            "2) Tools in the same step must be independent (do not require another same-step tool output).\n"
            "3) If schema is unclear, call list_tables or describe_table.\n"
            "4) If SQL is drafted, call run_sql to validate; when uncertain, try multiple run_sql variants with different filters/projections/order.\n"
            "5) Avoid duplicate tool calls with identical arguments in the same step.\n"
            "6) Only call final_answer when SQL is ready and one-line, and final_answer must be the only tool call in that step.\n"
            "7) Before final_answer, verify SQL output shape matches question requirements (columns/count/order/limit).\n"
            "8) If the question asks only for a metric/list, do not include entity name columns unless explicitly asked.\n"
            "9) Before final_answer, perform a strict constraint coverage self-check in your think:\n"
            "   - all required entities/literals from question are preserved in SQL\n"
            "   - all required categorical filters are present with correct columns\n"
            "   - no extra aggregation changes row granularity\n"
            "   - ORDER BY/LIMIT/rank direction exactly matches wording\n"
            "10) If any self-check item fails, do NOT call final_answer; call run_sql with revised SQL candidates instead.\n"
            "11) If a direct target query already returns the required result and one extra sanity check agrees, your next step must be final_answer.\n"
            "12) Do not spend a step on redundant rephrasing once the SQL has already been validated successfully."
        )
    },
}


class SingleReactActionProvider(BaseActionProvider):
    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=False)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = "single_react"
        self.prompt_templates = self.load_prompt_templates(context, self.prompts_type)
        if not self.prompt_templates:
            self.prompt_templates = SINGLE_REACT_PROMPT_TEMPLATES
        self.organization_planning_system = context.planning_system

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        return self.create_agent(
            context,
            tools=tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )

