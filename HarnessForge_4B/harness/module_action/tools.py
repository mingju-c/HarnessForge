from __future__ import annotations

from typing import Any


def load_bench_tools(
    bench_type: str | None,
    *,
    db_path: str | None = None,
    context: Any = None,
) -> list[Any]:
    existing_tools = list(getattr(context, "bench_tools", None) or []) if context is not None else []
    if existing_tools:
        return existing_tools

    normalized = (bench_type or "").strip().lower()
    if normalized == "bird":
        return load_bird_tools(db_path)
    if normalized == "toolhop":
        return load_toolhop_tools(context)
    if normalized == "api_bank":
        return load_api_bank_tools(context)
    if normalized == "restbench":
        return load_restbench_tools(context)
    return []


def load_bird_tools(db_path: str | None) -> list[Any]:
    if not db_path:
        raise ValueError(
            "BIRD action tools require db_path via CoreAgent(..., db_path=...)."
        )

    from bird.sql_tools import DescribeTableTool, ListTablesTool, RunSQLTool

    return [
        ListTablesTool(db_path),
        DescribeTableTool(db_path),
        RunSQLTool(db_path),
    ]


def load_toolhop_tools(context: Any = None) -> list[Any]:
    if context is None:
        raise ValueError("ToolHop action tools require ActionContext.")

    kwargs = getattr(context, "kwargs", {}) or {}
    toolhop_mode = getattr(context, "toolhop_mode", None) or kwargs.get("toolhop_mode", "closed")
    toolhop_sample = getattr(context, "toolhop_sample", None) or kwargs.get("toolhop_sample")
    if toolhop_sample is None:
        functions = getattr(context, "toolhop_functions", None) or []
        tool_specs = getattr(context, "toolhop_tool_specs", None) or []
        if functions and tool_specs:
            toolhop_sample = {
                "functions": functions,
                "tools": {
                    str(index): tool_spec
                    for index, tool_spec in enumerate(tool_specs)
                    if isinstance(tool_spec, dict)
                },
            }
    if toolhop_sample is None:
        raise ValueError(
            "ToolHop action tools require toolhop_sample or toolhop_functions/toolhop_tool_specs in ActionContext."
        )

    from runtime.toolhop.runtime import build_toolhop_tools

    return build_toolhop_tools(toolhop_sample, mode=toolhop_mode)


def load_api_bank_tools(context: Any = None) -> list[Any]:
    if context is None:
        raise ValueError("API-Bank action tools require ActionContext.")

    kwargs = getattr(context, "kwargs", {}) or {}
    sample = kwargs.get("api_bank_sample")
    if sample is None:
        raise ValueError("API-Bank action tools require api_bank_sample in ActionContext kwargs.")

    from runtime.api_bank.runtime import build_api_bank_tools

    return build_api_bank_tools(sample)


def load_restbench_tools(context: Any = None) -> list[Any]:
    if context is None:
        raise ValueError("RestBench action tools require ActionContext.")

    kwargs = getattr(context, "kwargs", {}) or {}
    sample = kwargs.get("restbench_sample")
    if not isinstance(sample, dict):
        raise ValueError("RestBench action tools require restbench_sample in ActionContext kwargs.")

    spec_path = sample.get("_restbench_spec_path") or kwargs.get("restbench_spec_path")
    if not spec_path:
        raise ValueError("RestBench action tools require _restbench_spec_path on each sample.")
    dataset_name = sample.get("_restbench_dataset") or kwargs.get("restbench_dataset") or "restbench"

    from runtime.restbench.runtime import build_restbench_tools

    return build_restbench_tools(
        spec_path=str(spec_path),
        dataset_name=str(dataset_name),
    )
