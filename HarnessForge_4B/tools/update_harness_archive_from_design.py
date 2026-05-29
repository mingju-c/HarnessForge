#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ARCHIVE = Path("registries/harness_archive.yaml")
SOURCE_FILES = (
    "Description.md",
    "builder.py",
    "__init__.py",
    "planning_module/provider.py",
    "action_module/provider.py",
    "memory_module/provider.py",
)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def project_root_from_archive(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.parent.name == "registries":
        return resolved.parent.parent
    return Path.cwd().resolve()


def read_text(path: Path, limit: int) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]...\n"


def collect_harness_sources(harness_path: Path, max_file_chars: int, max_total_chars: int) -> str:
    chunks: list[str] = []
    total = 0
    for rel in SOURCE_FILES:
        path = harness_path / rel
        if not path.exists() or not path.is_file():
            continue
        body = read_text(path, max_file_chars)
        chunk = f"\n### {rel}\n```text\n{body}\n```\n"
        if total + len(chunk) > max_total_chars:
            remaining = max_total_chars - total
            if remaining > 200:
                chunks.append(chunk[:remaining] + "\n...[source budget exhausted]...\n")
            break
        chunks.append(chunk)
        total += len(chunk)
    if not chunks:
        raise FileNotFoundError(f"No expected harness design files found under {harness_path}")
    return "".join(chunks)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise SystemExit("PyYAML is required. Install requirements.txt before running this script.") from exc
    if not path.exists():
        return {"schema_version": 2, "description": "Compact harness archive.", "harnesses": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Archive must be a YAML mapping: {path}")
    data.setdefault("schema_version", 2)
    data.setdefault("harnesses", {})
    return data


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise SystemExit("PyYAML is required. Install requirements.txt before running this script.") from exc
    remove_key_recursive(data, "updated_at")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False, width=100), encoding="utf-8")


def remove_key_recursive(value: Any, key: str) -> None:
    if isinstance(value, dict):
        value.pop(key, None)
        for child in value.values():
            remove_key_recursive(child, key)
    elif isinstance(value, list):
        for child in value:
            remove_key_recursive(child, key)


def resolve_model(args: argparse.Namespace) -> str:
    candidates = [
        args.model,
        os.environ.get("HARNESS_ARCHIVE_MODEL"),
        os.environ.get("HARNESS_PRODUCTION_MODEL"),
        os.environ.get("HARNESS_GENERATION_MODEL"),
        os.environ.get("PLANNING_MODEL"),
        os.environ.get("EXECUTE_MODEL"),
    ]
    for item in candidates:
        if item and str(item).strip():
            return str(item).strip()
    raise SystemExit("Set --model or HARNESS_ARCHIVE_MODEL/HARNESS_PRODUCTION_MODEL/PLANNING_MODEL.")


def resolve_api_url(args: argparse.Namespace) -> str:
    direct = args.api_url or os.environ.get("OPENAI_API_URL")
    if direct:
        return direct.strip()
    base = args.api_base or os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")
    if not base:
        raise SystemExit("Set --api-base or OPENAI_BASE_URL/OPENAI_API_BASE.")
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def resolve_api_key(args: argparse.Namespace) -> str:
    return args.api_key or os.environ.get("OPENAI_API_KEY") or "EMPTY"


def make_messages(harness_name: str, sources: str, existing_entry: dict[str, Any] | None, metrics_text: str | None) -> list[dict[str, str]]:
    schema = {
        "role": "candidate | seed | baseline | survivor",
        "status": "candidate | active | seed | archived",
        "archive_tier": "strong_seed | diversity_seed | repair_candidate | survivor | candidate",
        "tags": ["short_tag"],
        "design": {
            "summary": "one-sentence design summary",
            "planning": "short planning mechanism name",
            "planning_description": "what planning owns in this harness",
            "action": "short action/orchestration mechanism name",
            "action_description": "what action/tool orchestration owns",
            "memory": "short memory mechanism name",
            "memory_description": "what memory stores/retrieves/exposes",
            "topology": "direct_react | augmented_react | multi_agent | verifier_guarded | other",
            "pairing_reason": "why this harness pairs with the policy",
        },
        "performance": {"status": "not_evaluated or compact metrics supplied by the user"},
        "strengths": ["transferable strength"],
        "issues": ["known or likely risk"],
        "evolution_recommendations": ["future repair direction"],
        "notes": "public, compact note without secrets, private paths, keys, or timestamps",
    }
    user = {
        "harness_name": harness_name,
        "required_output_schema": schema,
        "existing_archive_entry": existing_entry or {},
        "metrics_summary": metrics_text or "",
        "harness_sources": sources,
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a HarnessForge archive curator. Summarize an executable harness bundle "
                "into a compact public YAML-ready JSON entry. Do not include private paths, API keys, "
                "user names, timestamps, or raw trajectory text. Preserve existing factual performance "
                "metrics if they are supplied; otherwise set performance.status to not_evaluated. "
                "Return one JSON object only."
            ),
        },
        {"role": "user", "content": json.dumps(user, ensure_ascii=False, indent=2)},
    ]


def call_chat_completion(args: argparse.Namespace, messages: list[dict[str, str]]) -> str:
    payload = {
        "model": resolve_model(args),
        "messages": messages,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        resolve_api_url(args),
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {resolve_api_key(args)}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"API request failed: HTTP {exc.code}: {detail}") from exc
    choices = body.get("choices") or []
    if not choices:
        raise SystemExit(f"API response has no choices: {body}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise SystemExit(f"API response has no message content: {body}")
    return str(content)


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        stripped = fence.group(1).strip()
    if not stripped.startswith("{"):
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(0)
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Generated archive entry must be a JSON object.")
    return payload


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def normalize_entry(args: argparse.Namespace, generated: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    existing = existing or {}
    entry = dict(generated)
    if args.role:
        entry["role"] = args.role
    entry.setdefault("role", existing.get("role") or "candidate")
    entry.setdefault("status", existing.get("status") or "candidate")
    if args.archive_tier:
        entry["archive_tier"] = args.archive_tier
    elif existing.get("archive_tier") and not entry.get("archive_tier"):
        entry["archive_tier"] = existing.get("archive_tier")
    entry["tags"] = sorted(set(normalize_list(existing.get("tags")) + normalize_list(entry.get("tags")) + args.tag))
    entry.setdefault("design", existing.get("design") or {})
    if args.preserve_performance and existing.get("performance"):
        entry["performance"] = existing.get("performance")
    else:
        entry.setdefault("performance", {"status": "not_evaluated"})
    for key in ("strengths", "issues", "evolution_recommendations"):
        entry[key] = normalize_list(entry.get(key))
    entry.setdefault("notes", existing.get("notes") or "")
    remove_key_recursive(entry, "updated_at")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or update a compact harness_archive.yaml entry from harness design files using an OpenAI-compatible API.")
    parser.add_argument("--archive-file", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--harness-path", type=Path, required=True)
    parser.add_argument("--harness-name", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--api-base", type=str, default=None)
    parser.add_argument("--api-url", type=str, default=None)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--metrics-summary-file", type=Path, default=None)
    parser.add_argument("--role", type=str, default=None)
    parser.add_argument("--archive-tier", type=str, default=None)
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-file-chars", type=int, default=12000)
    parser.add_argument("--max-total-chars", type=int, default=50000)
    parser.add_argument("--dry-run", action="store_true", help="Print generated entry without writing the archive.")
    parser.add_argument("--prompt-only", action="store_true", help="Print the API prompt payload without calling the API.")
    parser.add_argument("--no-preserve-performance", dest="preserve_performance", action="store_false")
    parser.set_defaults(preserve_performance=True)
    args = parser.parse_args()

    if args.dotenv:
        load_dotenv(args.dotenv)
    archive_path = args.archive_file.resolve()
    project_root = project_root_from_archive(archive_path)
    harness_path = args.harness_path
    if not harness_path.is_absolute():
        harness_path = (project_root / harness_path).resolve()
    if not harness_path.exists():
        raise SystemExit(f"Harness path not found: {harness_path}")
    harness_name = args.harness_name or harness_path.name

    archive = load_yaml(archive_path)
    remove_key_recursive(archive, "updated_at")
    existing = (archive.get("harnesses") or {}).get(harness_name)
    metrics_text = None
    if args.metrics_summary_file:
        metrics_text = read_text(args.metrics_summary_file, 10000)
    sources = collect_harness_sources(harness_path, args.max_file_chars, args.max_total_chars)
    messages = make_messages(harness_name, sources, existing, metrics_text)

    if args.prompt_only:
        print(json.dumps({"messages": messages}, ensure_ascii=False, indent=2))
        return

    content = call_chat_completion(args, messages)
    generated = extract_json(content)
    entry = normalize_entry(args, generated, existing)

    if args.dry_run:
        print(json.dumps({harness_name: entry}, ensure_ascii=False, indent=2))
        return

    archive.setdefault("harnesses", {})[harness_name] = entry
    save_yaml(archive_path, archive)
    print(f"Updated {harness_name} in {archive_path}")


if __name__ == "__main__":
    main()
