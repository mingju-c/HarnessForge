from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from Agents.tools import Tool


HTTP_METHODS = {"get", "post", "put", "delete", "patch"}


def normalize_endpoint_tool_name(endpoint: str) -> str:
    name = str(endpoint or "").strip().lower()
    name = name.replace("{", "").replace("}", "")
    name = name.replace(" ", "_").replace("/", "_")
    name = re.sub(r"_+", "_", name).strip("_")
    if name and not name[0].isalpha():
        name = f"rb_{name}"
    return name or "restbench_endpoint"


@lru_cache(maxsize=8)
def load_restbench_spec(spec_path: str) -> dict[str, Any]:
    path = Path(spec_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("paths"), dict):
        raise ValueError(f"RestBench spec must be an OpenAPI JSON object with paths: {path}")
    return payload


def extract_restbench_endpoints(spec_path: str) -> list[dict[str, Any]]:
    spec = load_restbench_spec(spec_path)
    endpoints: list[dict[str, Any]] = []
    for path, path_item in sorted((spec.get("paths") or {}).items()):
        if not isinstance(path_item, dict):
            continue
        path_parameters = [
            deepcopy(param)
            for param in path_item.get("parameters", [])
            if isinstance(param, dict)
        ]
        for method, operation in sorted(path_item.items()):
            normalized_method = str(method).lower()
            if normalized_method not in HTTP_METHODS or not isinstance(operation, dict):
                continue

            endpoint_name = f"{normalized_method.upper()} {path}"
            description = (
                str(operation.get("summary") or "").strip()
                or str(operation.get("description") or "").strip()
                or f"{normalized_method.upper()} request to {path}"
            )
            operation_parameters = [
                deepcopy(param)
                for param in operation.get("parameters", [])
                if isinstance(param, dict)
            ]
            endpoints.append(
                {
                    "endpoint_name": endpoint_name,
                    "tool_name": normalize_endpoint_tool_name(endpoint_name),
                    "method": normalized_method.upper(),
                    "path": path,
                    "description": description,
                    "parameters": path_parameters + operation_parameters,
                    "request_body": deepcopy(operation.get("requestBody")),
                }
            )
    return endpoints


def _json_type(raw_type: Any) -> str:
    if isinstance(raw_type, list):
        non_null = [value for value in raw_type if value != "null"]
        raw_type = non_null[0] if non_null else "string"
    normalized = str(raw_type or "string").strip().lower()
    return {
        "str": "string",
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "array": "array",
        "list": "array",
        "object": "object",
        "dict": "object",
    }.get(normalized, "string")


def _parameter_properties(parameters: list[dict[str, Any]]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for param in parameters:
        name = str(param.get("name") or "").strip()
        if not name:
            continue
        schema = param.get("schema") if isinstance(param.get("schema"), dict) else {}
        entry: dict[str, Any] = {
            "type": _json_type(schema.get("type")),
            "description": str(param.get("description") or f"Parameter '{name}'."),
        }
        if entry["type"] == "array":
            entry["items"] = {"type": "string"}
        properties[name] = entry
    return properties


def _endpoint_inputs(endpoint: dict[str, Any]) -> dict[str, dict[str, Any]]:
    param_props = _parameter_properties(endpoint.get("parameters") or [])
    inputs: dict[str, dict[str, Any]] = dict(param_props)
    inputs["params"] = {
        "type": "object",
        "description": "Path or query parameters for this endpoint. You may also pass parameters directly by name.",
        "properties": param_props,
        "additionalProperties": True,
        "nullable": True,
    }
    if endpoint.get("request_body"):
        inputs["data"] = {
            "type": "object",
            "description": "JSON request body for this endpoint.",
            "additionalProperties": True,
            "nullable": True,
        }
    return inputs


def _endpoint_forward_args(
    endpoint: dict[str, Any],
    kwargs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    params = kwargs.get("params") if isinstance(kwargs.get("params"), dict) else {}
    data = kwargs.get("data") if isinstance(kwargs.get("data"), dict) else {}
    params = dict(params)
    data = dict(data)

    parameter_names = {
        str(param.get("name") or "").strip()
        for param in endpoint.get("parameters") or []
        if isinstance(param, dict) and str(param.get("name") or "").strip()
    }
    for key, value in kwargs.items():
        if key in {"params", "data"}:
            continue
        if not parameter_names or key in parameter_names:
            params.setdefault(key, value)
        elif endpoint.get("request_body"):
            data.setdefault(key, value)
        else:
            params.setdefault(key, value)
    return params, data

def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _tmdb_access_token() -> str | None:
    return (
        os.environ.get("RESTBENCH_TMDB_ACCESS_TOKEN")
        or os.environ.get("TMDB_ACCESS_TOKEN")
        or os.environ.get("TMDB_BEARER_TOKEN")
    )


def _tmdb_api_key() -> str | None:
    return os.environ.get("RESTBENCH_TMDB_API_KEY") or os.environ.get("TMDB_API_KEY")


def _live_api_enabled(dataset_name: str | None) -> bool:
    dataset = str(dataset_name or "").strip().lower()
    explicit = os.environ.get("RESTBENCH_LIVE_API")
    if explicit is not None:
        return _truthy(explicit)
    return dataset == "tmdb" and bool(_tmdb_access_token() or _tmdb_api_key())


def _base_url(dataset_name: str | None) -> str | None:
    dataset = str(dataset_name or "").strip().lower()
    if dataset == "tmdb":
        # Match DeepAgent's TMDB runner; api.themoviedb.org can produce SSL EOFs here.
        return os.environ.get("RESTBENCH_TMDB_BASE_URL") or "https://api.tmdb.org/3"
    if dataset == "spotify":
        return os.environ.get("RESTBENCH_SPOTIFY_BASE_URL") or "https://api.spotify.com/v1"
    return None


def _headers(dataset_name: str | None) -> dict[str, str]:
    dataset = str(dataset_name or "").strip().lower()
    headers = {"Accept": "application/json"}
    if dataset == "tmdb":
        token = _tmdb_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def _compact_response(value: Any, depth: int = 0) -> Any:
    max_depth = int(os.environ.get("RESTBENCH_MAX_RESPONSE_DEPTH", "4"))
    max_items = int(os.environ.get("RESTBENCH_MAX_LIST_ITEMS", "5"))
    max_keys = int(os.environ.get("RESTBENCH_MAX_DICT_KEYS", "28"))
    max_string = int(os.environ.get("RESTBENCH_MAX_STRING_CHARS", "300"))
    important_keys = {
        "id",
        "name",
        "title",
        "original_title",
        "media_type",
        "character",
        "job",
        "department",
        "known_for_department",
        "release_date",
        "first_air_date",
        "vote_average",
        "vote_count",
        "popularity",
        "runtime",
        "page",
        "total_pages",
        "total_results",
        "status",
        "success",
        "overview",
        "results",
        "cast",
        "crew",
        "genres",
        "seasons",
        "episodes",
    }

    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return value[:max_string] + f"... <truncated {len(value) - max_string} chars>"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if depth >= max_depth:
        if isinstance(value, list):
            return f"<list len={len(value)} truncated at depth {max_depth}>"
        if isinstance(value, dict):
            return f"<dict keys={len(value)} truncated at depth {max_depth}>"
        return str(value)
    if isinstance(value, list):
        compacted = [_compact_response(item, depth + 1) for item in value[:max_items]]
        if len(value) > max_items:
            compacted.append({"_truncated_items": len(value) - max_items})
        return compacted
    if isinstance(value, dict):
        keys = list(value.keys())
        selected: list[Any] = []
        for key in keys:
            if key in important_keys:
                selected.append(key)
        for key in keys:
            if key not in selected:
                selected.append(key)
            if len(selected) >= max_keys:
                break
        compacted = {
            key: _compact_response(value[key], depth + 1)
            for key in selected
            if key in value
        }
        skipped = len(keys) - len(compacted)
        if skipped > 0:
            compacted["_truncated_keys"] = skipped
        return compacted
    return str(value)


def _split_path_params(path: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    remaining = dict(params or {})

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in remaining:
            return match.group(0)
        value = remaining.pop(key)
        return str(value)

    return re.sub(r"\{([^}]+)\}", replace, path), remaining


def _live_call(
    *,
    dataset_name: str | None,
    endpoint_name: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not _live_api_enabled(dataset_name):
        return None

    base = _base_url(dataset_name)
    if not base:
        return None

    method = str(method or "GET").upper()
    resolved_path, query_params = _split_path_params(str(path or ""), params or {})
    if str(dataset_name or "").strip().lower() == "tmdb" and _tmdb_api_key() and not _tmdb_access_token():
        query_params.setdefault("api_key", _tmdb_api_key())

    try:
        import requests

        timeout = float(os.environ.get("RESTBENCH_HTTP_TIMEOUT", "30"))
        response = requests.request(
            method,
            f"{base.rstrip('/')}/{resolved_path.lstrip('/')}",
            headers=_headers(dataset_name),
            params=query_params or None,
            json=data or None,
            timeout=timeout,
        )
        try:
            body: Any = response.json()
        except Exception:
            body = response.text
        compact_body = body
        if _truthy(os.environ.get("RESTBENCH_COMPACT_RESPONSE", "true")):
            compact_body = _compact_response(body)
        return {
            "dataset": dataset_name,
            "endpoint": endpoint_name,
            "method": method,
            "path": resolved_path,
            "status": "called",
            "live_api": True,
            "status_code": response.status_code,
            "ok": response.ok,
            "response": compact_body,
            "response_compacted": compact_body is not body,
        }
    except Exception as exc:
        return {
            "dataset": dataset_name,
            "endpoint": endpoint_name,
            "method": method,
            "path": path,
            "status": "error",
            "live_api": True,
            "error": str(exc),
        }


def _placeholder_call(
    *,
    dataset_name: str | None,
    endpoint_name: str,
    tool_name: str,
    method: str,
    path: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dataset": dataset_name or "restbench",
        "endpoint": endpoint_name,
        "tool_name": tool_name,
        "method": method,
        "path": path,
        "arguments": arguments,
        "status": "called",
        "live_api": False,
        "note": "RestBench endpoint-selection mode; set TMDB_ACCESS_TOKEN or TMDB_API_KEY to enable live TMDB calls.",
    }


class RestBenchEndpointTool(Tool):
    skip_forward_signature_validation = True
    output_type = "any"

    def __init__(self, endpoint: dict[str, Any], dataset_name: str | None = None) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.dataset_name = dataset_name or "restbench"
        self.name = str(endpoint["tool_name"])
        self.description = (
            f"{endpoint['endpoint_name']} - {endpoint.get('description') or ''}".strip()
        )
        self.inputs = _endpoint_inputs(endpoint)

    def forward(self, **kwargs):
        params, data = _endpoint_forward_args(self.endpoint, kwargs)
        live_result = _live_call(
            dataset_name=self.dataset_name,
            endpoint_name=self.endpoint["endpoint_name"],
            method=self.endpoint["method"],
            path=self.endpoint["path"],
            params=params,
            data=data,
        )
        if live_result is not None:
            live_result["tool_name"] = self.name
            return live_result
        return _placeholder_call(
            dataset_name=self.dataset_name,
            endpoint_name=self.endpoint["endpoint_name"],
            tool_name=self.name,
            method=self.endpoint["method"],
            path=self.endpoint["path"],
            arguments=kwargs,
        )


class RestBenchAPIDetailsTool(Tool):
    name = "get_api_details"
    description = "Get endpoint details such as method, path, description, and parameters."
    inputs = {
        "endpoint_name": {
            "type": "string",
            "description": "Endpoint name, for example 'GET /search/movie'.",
        }
    }
    output_type = "any"

    def __init__(self, endpoints: list[dict[str, Any]]) -> None:
        super().__init__()
        self.endpoints = {endpoint["endpoint_name"]: endpoint for endpoint in endpoints}

    def forward(self, endpoint_name: str):
        endpoint = self.endpoints.get(str(endpoint_name or "").strip())
        if endpoint is None:
            return {
                "error": f"Endpoint '{endpoint_name}' not found.",
                "available_endpoints": sorted(self.endpoints)[:100],
            }
        return {
            "endpoint": endpoint["endpoint_name"],
            "tool_name": endpoint["tool_name"],
            "method": endpoint["method"],
            "path": endpoint["path"],
            "description": endpoint.get("description"),
            "parameters": endpoint.get("parameters") or [],
            "has_request_body": bool(endpoint.get("request_body")),
        }


class RestBenchCallAPITool(Tool):
    name = "call_api"
    description = "Call a RestBench endpoint by explicit endpoint name, method, and path."
    inputs = {
        "endpoint_name": {"type": "string", "description": "Endpoint name, e.g. 'GET /search/movie'."},
        "method": {"type": "string", "description": "HTTP method such as GET, POST, PUT, DELETE, or PATCH."},
        "path": {"type": "string", "description": "API path such as '/search/movie'."},
        "params": {"type": "object", "description": "Path or query parameters.", "nullable": True},
        "data": {"type": "object", "description": "JSON request body.", "nullable": True},
    }
    output_type = "any"
    skip_forward_signature_validation = True

    def __init__(self, endpoints: list[dict[str, Any]], dataset_name: str | None = None) -> None:
        super().__init__()
        self.dataset_name = dataset_name or "restbench"
        self.endpoints = {endpoint["endpoint_name"]: endpoint for endpoint in endpoints}

    def forward(self, endpoint_name: str, method: str, path: str, params=None, data=None):
        endpoint_name = str(endpoint_name or "").strip()
        expected = self.endpoints.get(endpoint_name)
        tool_name = normalize_endpoint_tool_name(endpoint_name)
        live_result = _live_call(
            dataset_name=self.dataset_name,
            endpoint_name=endpoint_name,
            method=method,
            path=path,
            params=params if isinstance(params, dict) else {},
            data=data if isinstance(data, dict) else {},
        )
        if live_result is not None:
            live_result["tool_name"] = tool_name
            live_result["known_endpoint"] = expected is not None
            return live_result
        result = _placeholder_call(
            dataset_name=self.dataset_name,
            endpoint_name=endpoint_name,
            tool_name=tool_name,
            method=str(method or "").upper(),
            path=path,
            arguments={"params": params or {}, "data": data or {}},
        )
        result["known_endpoint"] = expected is not None
        return result


def build_restbench_tools(
    *,
    spec_path: str,
    dataset_name: str | None = None,
    include_generic_tools: bool = True,
) -> list[Tool]:
    endpoints = extract_restbench_endpoints(spec_path)
    tools: list[Tool] = []
    if include_generic_tools:
        tools.extend(
            [
                RestBenchAPIDetailsTool(endpoints),
                RestBenchCallAPITool(endpoints, dataset_name=dataset_name),
            ]
        )
    tools.extend(
        RestBenchEndpointTool(endpoint, dataset_name=dataset_name)
        for endpoint in endpoints
    )
    return tools


def count_restbench_endpoints(spec_path: str) -> int:
    return len(extract_restbench_endpoints(spec_path))
