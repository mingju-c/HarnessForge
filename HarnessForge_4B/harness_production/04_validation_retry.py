#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HARNESS_PACKAGE = "harness_factory"
REQUIRED_FILES = (
    "__init__.py",
    "builder.py",
    "Description.md",
    "planning_module/provider.py",
    "action_module/provider.py",
    "memory_module/provider.py",
)
PYTHON_SUFFIXES = {".py"}
FIXABLE_STATUSES = {"failed_static", "failed_import", "failed_build"}
KNOWN_PROJECT_DEPENDENCY_MODULES = {
    "yaml",
    "dotenv",
    "openai",
    "rich",
    "jinja2",
    "tqdm",
    "numpy",
    "sklearn",
    "sentence_transformers",
    "PIL",
    "requests",
    "huggingface_hub",
    "torch",
    "transformers",
    "json_repair",
}


@dataclass
class CheckResult:
    check: str
    status: str
    evidence: str
    blocking: bool = False
    suggested_fix: str = ""


@dataclass
class ValidationReport:
    candidate_name: str
    candidate_path: str
    import_name: str
    verdict: str = "unknown"
    checks: list[CheckResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    traceback: str = ""

    def add(
        self,
        check: str,
        status: str,
        evidence: str,
        *,
        blocking: bool = False,
        suggested_fix: str = "",
    ) -> None:
        self.checks.append(
            CheckResult(
                check=check,
                status=status,
                evidence=evidence,
                blocking=blocking,
                suggested_fix=suggested_fix,
            )
        )
        if blocking:
            self.errors.append(f"{check}: {evidence}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "candidate_path": self.candidate_path,
            "import_name": self.import_name,
            "verdict": self.verdict,
            "checks": [check.__dict__ for check in self.checks],
            "errors": self.errors,
            "traceback": self.traceback,
        }


class DummyModel:
    """Tiny callable model used only for construction smoke checks."""

    def __call__(self, messages: list[dict[str, Any]]) -> Any:
        from Agents.models import ChatMessage, MessageRole

        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Validation smoke response.",
            reasoning_content="",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a generated harness candidate and optionally retry small "
            "LLM-assisted fixes until it imports/builds cleanly."
        )
    )
    parser.add_argument("--candidate-path", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--harness-package", default=DEFAULT_HARNESS_PACKAGE)
    parser.add_argument("--max-fix-attempts", type=int, default=3)
    parser.add_argument("--no-auto-fix", action="store_true")
    parser.add_argument("--dry-run-fixes", action="store_true")
    parser.add_argument(
        "--repair-agent",
        choices=("json_model", "mini_swe"),
        default=os.environ.get("HARNESS_REPAIR_AGENT", "json_model"),
        help="Repair backend: lightweight JSON file replacement or optional mini-swe-agent.",
    )
    parser.add_argument(
        "--fix-model",
        default=(
            os.environ.get("HARNESS_VALIDATION_FIX_MODEL")
            or os.environ.get("PLANNING_MODEL")
            or os.environ.get("EXECUTE_MODEL")
            or "gpt-4.1-mini"
        ),
    )
    parser.add_argument(
        "--model-backend",
        default=os.environ.get("HARNESS_VALIDATION_MODEL_BACKEND")
        or os.environ.get("MODEL_BACKEND")
        or os.environ.get("LLM_BACKEND")
        or "api",
    )
    parser.add_argument("--api-base", default=os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--mini-swe-root", type=Path, default=PROJECT_ROOT.parent / "mini-swe-agent")
    parser.add_argument("--mini-swe-step-limit", type=int, default=int(os.environ.get("MSWEA_STEP_LIMIT", "30")))
    parser.add_argument("--mini-swe-cost-limit", type=float, default=float(os.environ.get("MSWEA_COST_LIMIT", "10.0")))
    parser.add_argument("--report-path", type=Path, default=None)
    return parser.parse_args()


def _safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _safe_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def setup_import_paths(project_root: Path, harness_package: str) -> None:
    project_root = project_root.resolve()
    harness_root = project_root.joinpath(*harness_package.split(".")).resolve()
    for path in (project_root, harness_root, harness_root.parent):
        path_text = str(path)
        while path_text in sys.path:
            sys.path.remove(path_text)
        sys.path.insert(0, path_text)
    importlib.invalidate_caches()


def infer_import_name(candidate_path: Path, project_root: Path, harness_package: str) -> str:
    candidate_path = candidate_path.resolve()
    package_root = project_root.resolve().joinpath(*harness_package.split("."))
    try:
        rel = candidate_path.relative_to(package_root)
        return ".".join([harness_package, *rel.parts])
    except ValueError:
        try:
            rel = candidate_path.relative_to(project_root.resolve())
            return ".".join(rel.parts)
        except ValueError:
            return candidate_path.name


def clear_module_cache(import_name: str) -> None:
    prefixes = (import_name, f"{import_name}.")
    for key in list(sys.modules.keys()):
        if key == import_name or any(key.startswith(prefix) for prefix in prefixes):
            del sys.modules[key]
    importlib.invalidate_caches()


def missing_known_dependency(report: ValidationReport) -> str | None:
    joined = "\n".join(report.errors + [report.traceback])
    match = re.search(r"No module named ['\"]([^'\"]+)['\"]", joined)
    if not match:
        return None
    module_name = match.group(1).split(".", 1)[0]
    if module_name in KNOWN_PROJECT_DEPENDENCY_MODULES:
        return module_name
    return None


def check_required_files(candidate_path: Path, report: ValidationReport) -> bool:
    ok = True
    for rel_path in REQUIRED_FILES:
        path = candidate_path / rel_path
        if path.exists():
            report.add("required_files", "passed", f"{rel_path} exists")
        else:
            ok = False
            report.add(
                "required_files",
                "failed",
                f"{rel_path} is missing",
                blocking=True,
                suggested_fix=f"Create {rel_path} with complete harness-compatible content.",
            )
    return ok


def check_python_syntax(candidate_path: Path, report: ValidationReport) -> bool:
    ok = True
    for path in sorted(candidate_path.rglob("*.py")):
        rel_path = path.relative_to(candidate_path).as_posix()
        try:
            ast.parse(_safe_read(path), filename=str(path))
            report.add("syntax", "passed", f"{rel_path} parses")
        except SyntaxError as exc:
            ok = False
            report.add(
                "syntax",
                "failed",
                f"{rel_path}: {exc}",
                blocking=True,
                suggested_fix="Fix Python syntax while preserving the generated design.",
            )
    return ok


def check_text_contracts(candidate_path: Path, report: ValidationReport) -> bool:
    required_symbols = {
        "builder.py": [
            "HARNESS_NAME",
            "PLANNING_SYSTEM",
            "ACTION_SYSTEM",
            "DEFAULT_MEMORY_SYSTEM",
            "build_agent_from_context",
        ],
        "__init__.py": ["build_agent_from_context", "__all__"],
        "planning_module/provider.py": ["PLANNING_SYSTEM", "PlanningClass"],
        "action_module/provider.py": ["ACTION_SYSTEM", "get_provider"],
        "memory_module/provider.py": ["MemoryProvider"],
    }
    ok = True
    for rel_path, symbols in required_symbols.items():
        path = candidate_path / rel_path
        if not path.exists():
            continue
        text = _safe_read(path)
        missing = [symbol for symbol in symbols if symbol not in text]
        if missing:
            ok = False
            report.add(
                "exports",
                "failed",
                f"{rel_path} missing expected symbol text: {missing}",
                blocking=True,
                suggested_fix=f"Add or export {', '.join(missing)} in {rel_path}.",
            )
        else:
            report.add("exports", "passed", f"{rel_path} contains expected symbols")
    return ok


def import_check(import_name: str, report: ValidationReport) -> Any | None:
    clear_module_cache(import_name)
    try:
        module = importlib.import_module(import_name)
        if not hasattr(module, "build_agent_from_context"):
            report.add(
                "imports",
                "failed",
                f"{import_name} imports but lacks build_agent_from_context",
                blocking=True,
                suggested_fix="Export build_agent_from_context from __init__.py.",
            )
            return None
        report.add("imports", "passed", f"Imported {import_name}")
        return module
    except Exception:
        report.traceback = traceback.format_exc()
        report.add(
            "imports",
            "failed",
            report.traceback.splitlines()[-1],
            blocking=True,
            suggested_fix="Fix import path, missing symbol, or top-level module error.",
        )
        return None


def import_submodules(import_name: str, report: ValidationReport) -> bool:
    ok = True
    for suffix in (
        "builder",
        "planning_module.provider",
        "action_module.provider",
        "memory_module.provider",
    ):
        module_name = f"{import_name}.{suffix}"
        try:
            importlib.import_module(module_name)
            report.add("submodule_imports", "passed", f"Imported {module_name}")
        except Exception:
            ok = False
            report.traceback = traceback.format_exc()
            report.add(
                "submodule_imports",
                "failed",
                f"{module_name}: {report.traceback.splitlines()[-1]}",
                blocking=True,
                suggested_fix=f"Fix imports or top-level definitions in {suffix}.",
            )
    return ok


def build_agent_smoke(module: Any, report: ValidationReport) -> bool:
    try:
        from module_action.base_action import ActionContext

        planning_system = getattr(module, "PLANNING_SYSTEM", "generic_planning")
        action_system = getattr(module, "ACTION_SYSTEM", planning_system)
        context = ActionContext(
            model=DummyModel(),
            summary_interval=None,
            prompts_type=None,
            max_steps=1,
            planning_system=planning_system,
            action_system=action_system,
            bench_type=None,
            db_path=None,
            strict_bench_tools=False,
            kwargs={},
            bench_tools=[],
        )
        agent = module.build_agent_from_context(context)
        if agent is None:
            report.add(
                "build_agent_smoke",
                "failed",
                "build_agent_from_context returned None",
                blocking=True,
                suggested_fix="Return a ToolCallingAgent-compatible object from builder.",
            )
            return False
        missing_attrs = [
            name for name in ("planning_system", "action_system", "harness_name") if not hasattr(agent, name)
        ]
        if missing_attrs:
            report.add(
                "build_agent_smoke",
                "failed",
                f"agent missing expected attrs: {missing_attrs}",
                blocking=True,
                suggested_fix="Set harness metadata fields in build_agent_from_context.",
            )
            return False
        report.add(
            "build_agent_smoke",
            "passed",
            f"Built agent {type(agent).__name__} with harness_name={getattr(agent, 'harness_name', None)}",
        )
        return True
    except Exception:
        report.traceback = traceback.format_exc()
        report.add(
            "build_agent_smoke",
            "failed",
            report.traceback.splitlines()[-1],
            blocking=True,
            suggested_fix="Fix builder/provider wiring, prompt files, constructor signatures, or orchestration setup.",
        )
        return False


def validate_once(candidate_path: Path, project_root: Path, harness_package: str) -> ValidationReport:
    candidate_path = candidate_path.resolve()
    setup_import_paths(project_root, harness_package)
    import_name = infer_import_name(candidate_path, project_root, harness_package)
    report = ValidationReport(
        candidate_name=candidate_path.name,
        candidate_path=candidate_path.as_posix(),
        import_name=import_name,
    )

    files_ok = check_required_files(candidate_path, report)
    syntax_ok = check_python_syntax(candidate_path, report)
    contracts_ok = check_text_contracts(candidate_path, report)
    if not (files_ok and syntax_ok and contracts_ok):
        report.verdict = "failed_static"
        return report

    module = import_check(import_name, report)
    submodules_ok = import_submodules(import_name, report)
    if module is None or not submodules_ok:
        missing_dependency = missing_known_dependency(report)
        if missing_dependency:
            report.verdict = "failed_environment"
            report.add(
                "environment",
                "failed",
                f"Project dependency module is missing in current Python env: {missing_dependency}",
                blocking=True,
                suggested_fix="Install project dependencies, e.g. `pip install -r requirements.txt`, then rerun validation.",
            )
        else:
            report.verdict = "failed_import"
        return report

    if not build_agent_smoke(module, report):
        missing_dependency = missing_known_dependency(report)
        report.verdict = "failed_environment" if missing_dependency else "failed_build"
        return report

    report.verdict = "passed"
    return report


def collect_harness_files(candidate_path: Path, max_chars: int = 80000) -> str:
    parts: list[str] = []
    preferred = list(REQUIRED_FILES)
    extra = [
        path.relative_to(candidate_path).as_posix()
        for path in sorted(candidate_path.rglob("*"))
        if path.is_file()
        and path.suffix in {".py", ".yaml", ".yml", ".md", ".txt"}
        and path.relative_to(candidate_path).as_posix() not in preferred
        and "__pycache__" not in path.parts
    ]
    for rel_path in preferred + extra:
        path = candidate_path / rel_path
        if not path.exists() or not path.is_file():
            continue
        parts.append(f"### FILE: {rel_path}\n```text\n{_safe_read(path).rstrip()}\n```")
        if sum(len(part) for part in parts) > max_chars:
            parts.append("[... clipped for prompt budget ...]")
            break
    return "\n\n".join(parts)


def create_fix_model(args: argparse.Namespace) -> Any:
    from llm_runtime import create_chat_model, resolve_llm_config

    config = resolve_llm_config(
        args.fix_model,
        backend=args.model_backend,
        api_key=args.api_key,
        api_base=args.api_base,
    )
    return create_chat_model(config, max_completion_tokens=32768)


def extract_json_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object found in model response")


def request_fix(
    *,
    model: Any,
    candidate_path: Path,
    report: ValidationReport,
    attempt: int,
    max_attempts: int,
) -> dict[str, Any]:
    prompt = f"""
You are a harness validation repair agent.

Fix only small executability issues. Do not redesign the harness.

Candidate path: {candidate_path}
Repair attempt: {attempt} / {max_attempts}

Validation report:
{json.dumps(report.to_dict(), indent=2, ensure_ascii=False)}

Current harness files:
{collect_harness_files(candidate_path)}

Return strict JSON only:
{{
  "summary": "short explanation",
  "files": [
    {{"path": "relative/path.py", "content": "complete revised file content"}}
  ]
}}

Rules:
- Only include files that need changes.
- Each content value must be the complete file content.
- Do not add external dependencies.
- Do not hard-code benchmark answers or item IDs.
- Preserve the intended harness design; fix imports, exports, wiring, signatures, prompt keys, or small orchestration bugs only.
""".strip()
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    response = model(messages)
    text = getattr(response, "content", str(response)).strip()
    return extract_json_object(text)


def apply_fix_payload(candidate_path: Path, payload: dict[str, Any], *, dry_run: bool) -> list[str]:
    changed: list[str] = []
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("Fix payload must contain a files list")
    for item in files:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path") or "").strip()
        content = item.get("content")
        if not rel_path or not isinstance(content, str):
            continue
        target = (candidate_path / rel_path).resolve()
        if not str(target).startswith(str(candidate_path.resolve())):
            raise ValueError(f"Unsafe fix path outside candidate: {rel_path}")
        changed.append(rel_path)
        if not dry_run:
            _safe_write(target, content)
    return changed


def file_hashes(candidate_path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(candidate_path.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix not in {".py", ".yaml", ".yml", ".md", ".txt"}:
            continue
        rel_path = path.relative_to(candidate_path).as_posix()
        hashes[rel_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    keys = sorted(set(before) | set(after))
    return [key for key in keys if before.get(key) != after.get(key)]


def run_json_model_repair(
    *,
    args: argparse.Namespace,
    candidate_path: Path,
    report: ValidationReport,
    attempt: int,
) -> dict[str, Any]:
    model = create_fix_model(args)
    fix_payload = request_fix(
        model=model,
        candidate_path=candidate_path,
        report=report,
        attempt=attempt,
        max_attempts=args.max_fix_attempts,
    )
    changed = apply_fix_payload(candidate_path, fix_payload, dry_run=args.dry_run_fixes)
    return {
        "repair_agent": "json_model",
        "attempt": attempt,
        "summary": fix_payload.get("summary"),
        "changed_files": changed,
        "dry_run": args.dry_run_fixes,
    }


def build_mini_swe_task(
    *,
    candidate_path: Path,
    project_root: Path,
    report: ValidationReport,
    attempt: int,
    max_attempts: int,
) -> str:
    try:
        candidate_rel = candidate_path.relative_to(project_root).as_posix()
    except ValueError:
        candidate_rel = candidate_path.as_posix()
    validation_command = (
        "python3 harness_production/04_validation_retry.py "
        f"--candidate-path {candidate_rel} --no-auto-fix "
        f"--report-path {candidate_rel}/validation_retry_inner_report.json"
    )
    return f"""
Fix the generated harness so it passes the validation smoke checks.

Candidate harness directory:
`{candidate_rel}`

Repair attempt: {attempt} / {max_attempts}

Validation report:
```json
{json.dumps(report.to_dict(), indent=2, ensure_ascii=False)}
```

Rules:
1. Modify only files under `{candidate_rel}`.
2. Make the smallest repair that fixes the reported validation failure.
3. Do not redesign the harness or replace the Stage 2 design.
4. Do not add external dependencies.
5. Do not hard-code benchmark answers, item IDs, or validation bypasses.
6. Pay special attention to imports, exports, builder wiring, provider signatures, prompt keys, and action orchestration setup.
7. After editing, run:
```bash
{validation_command}
```
8. When validation passes or no further local repair is possible, submit.
""".strip()


def run_mini_swe_repair(
    *,
    args: argparse.Namespace,
    candidate_path: Path,
    project_root: Path,
    report: ValidationReport,
    attempt: int,
) -> dict[str, Any]:
    mini_swe_src = (args.mini_swe_root / "src").resolve()
    if not mini_swe_src.exists():
        raise RuntimeError(f"mini-swe-agent src directory not found: {mini_swe_src}")
    if str(mini_swe_src) not in sys.path:
        sys.path.insert(0, str(mini_swe_src))

    from minisweagent.agents.interactive import InteractiveAgent
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.models.litellm_model import LitellmModel

    model_kwargs: dict[str, Any] = {}
    if args.api_base:
        model_kwargs = {
            "custom_llm_provider": "openai",
            "api_base": args.api_base,
        }
    cost_tracking = os.environ.get("MSWEA_COST_TRACKING", "ignore_errors")
    model = LitellmModel(
        model_name=os.environ.get("MSWEA_MODEL_NAME") or args.fix_model,
        model_kwargs=model_kwargs,
        cost_tracking=cost_tracking,
    )
    env = LocalEnvironment(cwd=str(project_root.resolve()))
    agent = InteractiveAgent(
        model,
        env,
        mode="yolo",
        confirm_exit=False,
        cost_limit=args.mini_swe_cost_limit,
        step_limit=args.mini_swe_step_limit,
    )

    before = file_hashes(candidate_path)
    task = build_mini_swe_task(
        candidate_path=candidate_path,
        project_root=project_root,
        report=report,
        attempt=attempt,
        max_attempts=args.max_fix_attempts,
    )
    exit_status, result = agent.run(task)
    after = file_hashes(candidate_path)

    trajectory_path = candidate_path / f"validation_repair_mini_swe_attempt_{attempt}.json"
    try:
        from minisweagent.run.utils.save import save_traj

        save_traj(
            agent=agent,
            path=trajectory_path,
            exit_status=exit_status,
            result=result,
            print_path=False,
        )
    except Exception:
        trajectory_path.write_text(
            json.dumps(
                {"exit_status": exit_status, "result": str(result)},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    return {
        "repair_agent": "mini_swe",
        "attempt": attempt,
        "exit_status": exit_status,
        "result": str(result),
        "changed_files": changed_files(before, after),
        "trajectory_path": trajectory_path.as_posix(),
        "dry_run": False,
    }


def run_repair_agent(
    *,
    args: argparse.Namespace,
    candidate_path: Path,
    project_root: Path,
    report: ValidationReport,
    attempt: int,
) -> dict[str, Any]:
    if args.repair_agent == "mini_swe":
        if args.dry_run_fixes:
            raise RuntimeError("--dry-run-fixes is only supported with --repair-agent json_model")
        return run_mini_swe_repair(
            args=args,
            candidate_path=candidate_path,
            project_root=project_root,
            report=report,
            attempt=attempt,
        )
    return run_json_model_repair(
        args=args,
        candidate_path=candidate_path,
        report=report,
        attempt=attempt,
    )


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    candidate_path = args.candidate_path.resolve()
    project_root = args.project_root.resolve()
    report_path = args.report_path or candidate_path / "validation_retry_report.json"
    auto_fix = not args.no_auto_fix

    history: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []

    report = validate_once(candidate_path, project_root, args.harness_package)
    history.append(report.to_dict())
    fixes_used = 0

    while report.verdict != "passed" and auto_fix and report.verdict in FIXABLE_STATUSES and fixes_used < args.max_fix_attempts:
        fixes_used += 1
        try:
            fix_result = run_repair_agent(
                args=args,
                candidate_path=candidate_path,
                project_root=project_root,
                report=report,
                attempt=fixes_used,
            )
            fixes.append(fix_result)
            if args.dry_run_fixes or not fix_result.get("changed_files"):
                break
        except Exception as exc:
            fixes.append(
                {
                    "attempt": fixes_used,
                    "repair_agent": args.repair_agent,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            break

        report = validate_once(candidate_path, project_root, args.harness_package)
        history.append(report.to_dict())

    final_verdict = report.verdict
    if report.verdict == "passed" and fixes_used > 0:
        final_verdict = "fixed_after_retry"
    elif report.verdict != "passed" and report.verdict != "failed_environment" and fixes_used >= args.max_fix_attempts:
        final_verdict = "needs_regeneration"

    result = {
        "success": report.verdict == "passed",
        "final_verdict": final_verdict,
        "candidate_path": candidate_path.as_posix(),
        "import_name": report.import_name,
        "auto_fix_enabled": auto_fix,
        "repair_agent": args.repair_agent,
        "max_fix_attempts": args.max_fix_attempts,
        "fixes_used": fixes_used,
        "fixes": fixes,
        "history": history,
    }
    write_report(report_path, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.verdict == "passed" else 1)


if __name__ == "__main__":
    main()
