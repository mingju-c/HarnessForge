from __future__ import annotations

import os
import threading
from typing import Any

try:
    from sentence_transformers import SentenceTransformer
    _embedding_import_error = None
except Exception as exc:  # pragma: no cover - optional dependency
    SentenceTransformer = None
    _embedding_import_error = exc

_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()


def _emit(logger: Any, message: str, *, level: str = "info") -> None:
    if logger is not None:
        log_fn = getattr(logger, level, None) or getattr(logger, 'info', None)
        if callable(log_fn):
            log_fn(message)
            return
    print(message)


def get_local_model_path(model_name: str, cache_dir: str = './storage/models') -> str:
    resolved_cache_dir = os.path.abspath(os.fspath(cache_dir or './storage/models'))
    os.makedirs(resolved_cache_dir, exist_ok=True)
    return os.path.join(resolved_cache_dir, model_name.replace('/', '_'))


def load_sentence_transformer(
    model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
    cache_dir: str = './storage/models',
    *,
    logger: Any = None,
    allow_unavailable: bool = False,
    unavailable_message: str | None = None,
):
    if SentenceTransformer is None:
        if allow_unavailable:
            message = unavailable_message or f'sentence-transformers not available: {_embedding_import_error}'
            _emit(logger, message, level='warning')
            return None
        raise RuntimeError(f'sentence-transformers not available: {_embedding_import_error}')

    local_model_path = get_local_model_path(model_name, cache_dir)
    has_local_model = os.path.isdir(local_model_path) and any(os.scandir(local_model_path))
    cache_key = local_model_path if has_local_model else f'remote::{model_name}::{os.path.abspath(os.fspath(cache_dir or "./storage/models"))}'

    with _MODEL_LOCK:
        cached_model = _MODEL_CACHE.get(local_model_path) or _MODEL_CACHE.get(cache_key)
        if cached_model is not None:
            return cached_model

        if has_local_model:
            try:
                model = SentenceTransformer(local_model_path)
                _MODEL_CACHE[local_model_path] = model
                _MODEL_CACHE[cache_key] = model
                return model
            except Exception as exc:
                _emit(logger, f'Local model load failed: {exc}', level='warning')

        _emit(logger, f'Downloading model from Hugging Face: {model_name}')
        try:
            model = SentenceTransformer(model_name)
        except Exception as exc:
            raise RuntimeError(f'Unable to load embedding model {model_name}: {exc}') from exc

        try:
            _emit(logger, f'Saving model to local cache: {local_model_path}')
            model.save(local_model_path)
        except Exception as exc:
            _emit(logger, f'Failed to save model to local cache: {exc}', level='warning')

        _MODEL_CACHE[local_model_path] = model
        _MODEL_CACHE[cache_key] = model
        return model
