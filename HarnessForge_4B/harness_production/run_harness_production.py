#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import string
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any



SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_PRODUCTION_ROOT = SCRIPT_PATH.parent
DEFAULT_PROJECT_ROOT = DEFAULT_PRODUCTION_ROOT.parent
HARNESSFORGE_ROOT = DEFAULT_PROJECT_ROOT.parent
DEFAULT_PRODUCTION_DIR = DEFAULT_PRODUCTION_ROOT.name
if (DEFAULT_PROJECT_ROOT / "harness_factory").exists():
    DEFAULT_FACTORY_DIR = "harness_factory"
elif (DEFAULT_PROJECT_ROOT / "scaffold_factory").exists():
    DEFAULT_FACTORY_DIR = "scaffold_factory"
else:
    DEFAULT_FACTORY_DIR = "harness_factory"

STAGE_FILE_CANDIDATES = {
    "stage1": ("01_module_localization.yaml",),
    "stage2": ("02_improvement_directions.yaml",),
    "stage3": ("03_harness_generation.yaml", "03_scaffold_generation.yaml"),
}

SNAPSHOT_FILES = (
    "__init__.py",
    "builder.py",
    "Description.md",
    "planning_module/provider.py",
    "action_module/provider.py",
    "memory_module/provider.py",
)

STAGE3_FILE_CONTRACT = """

---
## Machine-Readable Output Contract

After the design summary, output every file in the generated candidate bundle using this exact repeated format:

### FILE: <relative/path/inside/candidate>
```<language>
<complete file content>
```

Rules:
- Paths must be relative to the candidate directory, for example `builder.py` or `planning_module/provider.py`.
- Include all required files: `__init__.py`, `builder.py`, `Description.md`,
  `planning_module/provider.py`, `action_module/provider.py`, and `memory_module/provider.py`.
- Do not use absolute paths.
- Do not omit unchanged files; each file must be complete.
"""


@dataclass
class ModelConfig:
    model: str
    api_key: str | None
    base_url: str | None
    temperature: float | None
    max_tokens: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the HarnessForge three-stage harness production prompts through "
            "an OpenAI-compatible API."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=DEFAULT_PROJECT_ROOT,
        help="HarnessForge subproject root. Defaults to the parent directory of this production script.",
    )
    parser.add_argument("--production-dir", default=DEFAULT_PRODUCTION_DIR)
    parser.add_argument("--factory-dir", default=DEFAULT_FACTORY_DIR)
    parser.add_argument(
        "--stage",
        choices=("stage1", "stage2", "stage3", "all"),
        default="all",
        help="Which phase to run.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Output directory for prompts, reports, state, and raw generations.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Backward-compatible alias for --round-id when --round-id is omitted.",
    )
    parser.add_argument(
        "--round-id",
        default=None,
        help="Production output folder under harness_production, e.g. round3_4.",
    )
    parser.add_argument("--winner-harness-name", required=True)
    parser.add_argument(
        "--winner-harness-path",
        type=Path,
        default=None,
        help="Directory or file used to build the winner harness snapshot/template.",
    )
    parser.add_argument("--target-round", default="round_XX")
    parser.add_argument("--candidate-name", default="harness_candidate_api")
    parser.add_argument("--example-path", action="append", default=[])
    parser.add_argument("--selected-example-path", action="append", default=[])
    parser.add_argument("--max-snapshot-chars", type=int, default=120_000)
    parser.add_argument("--max-example-chars", type=int, default=160_000)
    parser.add_argument("--write-candidate", action="store_true")
    parser.add_argument("--overwrite-candidate", action="store_true")
    parser.add_argument(
        "--candidate-output-dir",
        type=Path,
        default=None,
        help="Where parsed Stage 3 files should be written. Defaults to factory/rounds/<target>/<candidate>.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Render prompts without calling the model.")

    add_text_arg(parser, "module-files-info")
    add_text_arg(parser, "metrics-summary")
    add_text_arg(parser, "answer-type-breakdown")
    add_text_arg(parser, "failure-summary")
    add_text_arg(parser, "trajectory-overview")
    add_text_arg(parser, "failure-trajectory-samples")
    add_text_arg(parser, "success-trajectory-samples")
    add_text_arg(parser, "module-localization-report")
    add_text_arg(parser, "improvement-direction-brief")
    add_text_arg(parser, "harness-pool-overview")
    add_text_arg(parser, "harness-examples")
    add_text_arg(parser, "selected-harness-examples")
    add_text_arg(parser, "existing-harness-names")
    add_text_arg(parser, "winner-harness-snapshot")
    add_text_arg(parser, "winner-harness-template")

    parser.add_argument("--analysis-model", default=None)
    parser.add_argument("--direction-model", default=None)
    parser.add_argument("--generation-model", default=None)
    parser.add_argument(
        "--model",
        default=None,
        help="Fallback model for any stage without a stage-specific model.",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    return parser.parse_args()


def add_text_arg(parser: argparse.ArgumentParser, name: str) -> None:
    flag = f"--{name}"
    dest = name.replace("-", "_")
    parser.add_argument(flag, dest=dest, default=None, help=f"Literal text or existing path for {name}.")
    parser.add_argument(f"{flag}-file", dest=f"{dest}_file", type=Path, default=None)


def read_source(value: str | None, file_path: Path | None, base_dir: Path) -> str:
    if file_path:
        return safe_read(resolve_path(file_path, base_dir))
    if not value:
        return ""
    try:
        possible = resolve_path(Path(value), base_dir)
        if possible.exists() and possible.is_file():
            return safe_read(possible)
    except OSError:
        pass
    return value


def resolve_path(path: Path, base_dir: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def safe_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def load_prompt_template(path: Path) -> str:
    text = safe_read(path)
    try:
        import yaml
    except ImportError:
        return load_literal_prompt_template(text, path)
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("prompt_template"), str):
        raise ValueError(f"{path} must contain a string prompt_template field")
    return data["prompt_template"]


def load_literal_prompt_template(text: str, path: Path) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "prompt_template: |":
            start = index + 1
            break
    if start is None:
        raise ValueError(f"{path} must contain `prompt_template: |` or install PyYAML")
    body = lines[start:]
    non_empty = [line for line in body if line.strip()]
    indent = min((len(line) - len(line.lstrip(" ")) for line in non_empty), default=0)
    return "\n".join(line[indent:] if len(line) >= indent else "" for line in body).rstrip() + "\n"


def template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key in sorted(values, key=len, reverse=True):
        rendered = rendered.replace("{" + key + "}", values[key])
    return rendered


def snapshot_path(path: Path | None, *, max_chars: int) -> str:
    if path is None:
        return ""
    path = path.resolve()
    if path.is_file():
        return clip(safe_read(path), max_chars, str(path))
    if not path.exists():
        raise FileNotFoundError(path)

    chunks: list[str] = []
    for rel in SNAPSHOT_FILES:
        file_path = path / rel
        if file_path.exists() and file_path.is_file():
            chunks.append(format_file_block(rel, safe_read(file_path)))

    if not chunks:
        for file_path in sorted(path.rglob("*")):
            if not file_path.is_file() or file_path.suffix not in {".py", ".md", ".yaml", ".yml"}:
                continue
            if "__pycache__" in file_path.parts:
                continue
            rel = file_path.relative_to(path).as_posix()
            chunks.append(format_file_block(rel, safe_read(file_path)))

    return clip("\n\n".join(chunks), max_chars, str(path))


def snapshot_many(paths: list[str], base_dir: Path, *, max_chars: int) -> str:
    chunks: list[str] = []
    for item in paths:
        path = resolve_path(Path(item), base_dir).resolve()
        if not path.exists():
            chunks.append(f"## Missing example path\n{item}")
            continue
        chunks.append(f"## Example: {path.name}\n\n{snapshot_path(path, max_chars=max_chars)}")
    return clip("\n\n---\n\n".join(chunks), max_chars, "examples")


def format_file_block(rel_path: str, content: str) -> str:
    return f"### {rel_path}\n```text\n{content.rstrip()}\n```"


def clip(text: str, max_chars: int, label: str) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[TRUNCATED {label}: kept first {max_chars} chars]"


def detect_stage_files(production_dir: Path) -> dict[str, str]:
    detected: dict[str, str] = {}
    for stage, candidates in STAGE_FILE_CANDIDATES.items():
        for filename in candidates:
            if (production_dir / filename).exists():
                detected[stage] = filename
                break
        if stage not in detected:
            expected = ", ".join(candidates)
            raise FileNotFoundError(f"Missing {stage} template in {production_dir}; expected one of: {expected}")
    return detected


def collect_existing_harness_names(project_root: Path, factory_dir: str) -> str:
    rounds_dir = project_root / factory_dir / "rounds"
    if not rounds_dir.exists():
        return ""
    names: list[str] = []
    for path in sorted(rounds_dir.glob("*/*")):
        if path.is_dir() and not path.name.startswith("__"):
            names.append(path.name)
    return "\n".join(f"- {name}" for name in names)


def make_work_dir(args: argparse.Namespace) -> Path:
    if args.work_dir:
        return resolve_path(args.work_dir, args.project_root).resolve()
    output_folder = args.round_id or args.run_id or datetime.now().strftime("round_api_%Y%m%d_%H%M%S")
    return (args.project_root / args.production_dir / output_folder).resolve()


def load_env(project_root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for env_path in (HARNESSFORGE_ROOT / ".env", project_root / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=True)


def apply_env_defaults(args: argparse.Namespace) -> None:
    args.api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    args.api_base = (
        args.api_base
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_API_URL")
    )
    args.model = (
        args.model
        or os.getenv("HARNESS_PRODUCTION_MODEL")
        or os.getenv("DEFAULT_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-5"
    )
    args.analysis_model = (
        args.analysis_model
        or os.getenv("HARNESS_ANALYSIS_MODEL")
        or os.getenv("ANALYSIS_MODEL")
    )
    args.direction_model = (
        args.direction_model
        or os.getenv("HARNESS_DIRECTION_MODEL")
        or os.getenv("GENERATION_MODEL")
    )
    args.generation_model = (
        args.generation_model
        or os.getenv("HARNESS_GENERATION_MODEL")
        or os.getenv("GENERATION_MODEL")
    )


def model_config(args: argparse.Namespace, model: str) -> ModelConfig:
    return ModelConfig(
        model=model,
        api_key=args.api_key or os.getenv("OPENAI_API_KEY"),
        base_url=args.api_base
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_API_URL"),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )


def call_model(prompt: str, config: ModelConfig) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("openai is required; install project requirements first") from exc
    if not config.api_key:
        raise ValueError("OPENAI_API_KEY or --api-key is required unless your endpoint ignores it.")
    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    messages = [
        {
            "role": "system",
            "content": "You are a careful harness-production assistant. Follow the user prompt exactly.",
        },
        {"role": "user", "content": prompt},
    ]
    kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
    }
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if config.max_tokens is None:
            raise
        kwargs.pop("max_tokens", None)
        kwargs["max_completion_tokens"] = config.max_tokens
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception:
            raise exc

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Model returned an empty response")
    return content


def text_inputs(args: argparse.Namespace) -> dict[str, str]:
    base_dir = args.project_root
    values = {
        "module_files_info": read_source(args.module_files_info, args.module_files_info_file, base_dir),
        "metrics_summary": read_source(args.metrics_summary, args.metrics_summary_file, base_dir),
        "answer_type_breakdown": read_source(args.answer_type_breakdown, args.answer_type_breakdown_file, base_dir),
        "failure_summary": read_source(args.failure_summary, args.failure_summary_file, base_dir),
        "trajectory_overview": read_source(args.trajectory_overview, args.trajectory_overview_file, base_dir),
        "failure_trajectory_samples": read_source(
            args.failure_trajectory_samples, args.failure_trajectory_samples_file, base_dir
        ),
        "success_trajectory_samples": read_source(
            args.success_trajectory_samples, args.success_trajectory_samples_file, base_dir
        ),
        "module_localization_report": read_source(
            args.module_localization_report, args.module_localization_report_file, base_dir
        ),
        "improvement_direction_brief": read_source(
            args.improvement_direction_brief, args.improvement_direction_brief_file, base_dir
        ),
        "harness_pool_overview": read_source(args.harness_pool_overview, args.harness_pool_overview_file, base_dir),
        "harness_examples": read_source(args.harness_examples, args.harness_examples_file, base_dir),
        "selected_harness_examples": read_source(
            args.selected_harness_examples, args.selected_harness_examples_file, base_dir
        ),
        "existing_harness_names": read_source(
            args.existing_harness_names, args.existing_harness_names_file, base_dir
        ),
        "winner_harness_snapshot": read_source(
            args.winner_harness_snapshot, args.winner_harness_snapshot_file, base_dir
        ),
        "winner_harness_template": read_source(
            args.winner_harness_template, args.winner_harness_template_file, base_dir
        ),
    }
    return values


def build_values(args: argparse.Namespace, work_dir: Path) -> dict[str, str]:
    values = text_inputs(args)
    winner_path = resolve_path(args.winner_harness_path, args.project_root) if args.winner_harness_path else None
    winner_snapshot = snapshot_path(winner_path, max_chars=args.max_snapshot_chars)

    if not values["winner_harness_snapshot"]:
        values["winner_harness_snapshot"] = winner_snapshot
    if not values["winner_harness_template"]:
        values["winner_harness_template"] = winner_snapshot
    if not values["module_files_info"]:
        values["module_files_info"] = "\n".join(SNAPSHOT_FILES)
    if not values["existing_harness_names"]:
        values["existing_harness_names"] = collect_existing_harness_names(args.project_root, args.factory_dir)
    if not values["harness_examples"] and args.example_path:
        values["harness_examples"] = snapshot_many(args.example_path, args.project_root, max_chars=args.max_example_chars)
    if not values["selected_harness_examples"] and args.selected_example_path:
        values["selected_harness_examples"] = snapshot_many(
            args.selected_example_path, args.project_root, max_chars=args.max_example_chars
        )
    if not values["selected_harness_examples"] and values["harness_examples"]:
        values["selected_harness_examples"] = values["harness_examples"]

    values.update(
        {
            "winner_harness_name": args.winner_harness_name,
            "winner_scaffold_name": args.winner_harness_name,
            "winner_scaffold_snapshot": values["winner_harness_snapshot"],
            "winner_scaffold_template": values["winner_harness_template"],
            "scaffold_pool_overview": values["harness_pool_overview"],
            "scaffold_examples": values["harness_examples"],
            "selected_scaffold_examples": values["selected_harness_examples"],
            "existing_scaffold_names": values["existing_harness_names"],
            "target_round": args.target_round,
            "candidate_name": args.candidate_name,
            "run_work_dir": str(work_dir),
        }
    )
    return values


def stage_model(args: argparse.Namespace, stage: str) -> str:
    if stage == "stage1":
        return args.analysis_model or args.model
    if stage == "stage2":
        return args.direction_model or args.model
    if stage == "stage3":
        return args.generation_model or args.model
    return args.model


def stage3_kind(args: argparse.Namespace) -> str:
    production_dir = args.project_root / args.production_dir
    stage3_file = detect_stage_files(production_dir)["stage3"]
    return "scaffold" if "scaffold" in stage3_file else "harness"


def response_path_for(args: argparse.Namespace, work_dir: Path, stage: str) -> Path:
    kind = stage3_kind(args)
    filenames = {
        "stage1": "module_localization_report.md",
        "stage2": "improvement_direction_brief.md",
        "stage3": f"{kind}_generation.raw.md",
    }
    return work_dir / filenames[stage]


def run_stage(
    *,
    args: argparse.Namespace,
    stage: str,
    values: dict[str, str],
    work_dir: Path,
    state: dict[str, Any],
) -> str:
    production_dir = args.project_root / args.production_dir
    stage_files = detect_stage_files(production_dir)
    template_path = production_dir / stage_files[stage]
    template = load_prompt_template(template_path)
    prompt = render_template(template, values)
    if stage == "stage3":
        prompt += STAGE3_FILE_CONTRACT

    safe_write(work_dir / f"{stage}_prompt.md", prompt)
    if args.dry_run:
        response = f"[DRY RUN] Prompt rendered for {stage}; no model call was made."
    else:
        response = call_model(prompt, model_config(args, stage_model(args, stage)))
    response_path = response_path_for(args, work_dir, stage)
    safe_write(response_path, response)

    state["phases"][stage] = {
        "completed": not args.dry_run,
        "model": stage_model(args, stage),
        "prompt": str(work_dir / f"{stage}_prompt.md"),
        "template": str(template_path),
        "response": str(response_path),
        "timestamp": datetime.now().isoformat(),
    }
    safe_write(work_dir / "state.json", json.dumps(state, indent=2, ensure_ascii=False))
    return response


def extract_stage3_files(
    response: str,
    *,
    candidate_dir: Path,
    target_round: str,
    candidate_name: str,
    overwrite: bool,
) -> list[str]:
    matches = list(re.finditer(r"^### FILE:\s*(.+?)\s*$", response, re.MULTILINE))
    if not matches:
        raise ValueError("No `### FILE:` blocks found in Stage 3 response")
    if candidate_dir.exists() and any(candidate_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"{candidate_dir} exists and is not empty; pass --overwrite-candidate to replace files")

    written: list[str] = []
    for index, match in enumerate(matches):
        raw_path = match.group(1).strip().strip("`").strip()
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(response)
        section = response[block_start:block_end]
        fence = re.search(r"```[A-Za-z0-9_+-]*\n(.*?)\n```", section, re.DOTALL)
        if not fence:
            continue
        rel_path = normalize_candidate_relpath(raw_path, target_round, candidate_name)
        output_path = candidate_dir / rel_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(fence.group(1).rstrip() + "\n", encoding="utf-8")
        written.append(rel_path.as_posix())
    if not written:
        raise ValueError("Stage 3 response had file headers but no fenced file contents")
    return written


def normalize_candidate_relpath(raw_path: str, target_round: str, candidate_name: str) -> PurePosixPath:
    raw_path = raw_path.replace("\\", "/").strip()
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe generated file path: {raw_path}")

    parts = list(path.parts)
    if candidate_name in parts:
        idx = parts.index(candidate_name)
        parts = parts[idx + 1 :]
    elif "rounds" in parts and target_round in parts:
        idx = parts.index(target_round)
        if idx + 2 <= len(parts) and idx + 1 < len(parts) and parts[idx + 1] == candidate_name:
            parts = parts[idx + 2 :]
    if not parts:
        raise ValueError(f"Generated file path does not name a file: {raw_path}")
    rel = PurePosixPath(*parts)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe generated file path: {raw_path}")
    return rel


def main() -> int:
    args = parse_args()
    args.project_root = args.project_root.resolve()
    load_env(args.project_root)
    apply_env_defaults(args)
    work_dir = make_work_dir(args)
    work_dir.mkdir(parents=True, exist_ok=True)

    state: dict[str, Any] = {
        "created_at": datetime.now().isoformat(),
        "project_root": str(args.project_root),
        "production_dir": args.production_dir,
        "round_id": args.round_id or args.run_id,
        "work_dir": str(work_dir),
        "winner_harness_name": args.winner_harness_name,
        "target_round": args.target_round,
        "candidate_name": args.candidate_name,
        "phases": {},
    }

    values = build_values(args, work_dir)
    stages = ("stage1", "stage2", "stage3") if args.stage == "all" else (args.stage,)

    for stage in stages:
        if stage == "stage2" and not values["module_localization_report"]:
            stage1_path = response_path_for(args, work_dir, "stage1")
            if stage1_path.exists():
                values["module_localization_report"] = safe_read(stage1_path)
        if stage == "stage3":
            stage1_path = response_path_for(args, work_dir, "stage1")
            stage2_path = response_path_for(args, work_dir, "stage2")
            if not values["module_localization_report"] and stage1_path.exists():
                values["module_localization_report"] = safe_read(stage1_path)
            if not values["improvement_direction_brief"] and stage2_path.exists():
                values["improvement_direction_brief"] = safe_read(stage2_path)

        print(f"[{stage}] rendering and running prompt")
        response = run_stage(args=args, stage=stage, values=values, work_dir=work_dir, state=state)

        if stage == "stage1":
            values["module_localization_report"] = response
        elif stage == "stage2":
            values["improvement_direction_brief"] = response
        elif stage == "stage3" and args.write_candidate:
            candidate_dir = (
                resolve_path(args.candidate_output_dir, args.project_root)
                if args.candidate_output_dir
                else args.project_root / args.factory_dir / "rounds" / args.target_round / args.candidate_name
            )
            written = extract_stage3_files(
                response,
                candidate_dir=candidate_dir,
                target_round=args.target_round,
                candidate_name=args.candidate_name,
                overwrite=args.overwrite_candidate,
            )
            state["phases"][stage]["candidate_dir"] = str(candidate_dir)
            state["phases"][stage]["written_files"] = written
            safe_write(work_dir / "state.json", json.dumps(state, indent=2, ensure_ascii=False))
            print(f"[stage3] wrote {len(written)} files to {candidate_dir}")

    print(f"[done] outputs saved under {work_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
