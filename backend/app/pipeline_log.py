"""Small shared file logger for parsing, storage and export."""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "pipeline.log"
_run_id: ContextVar[str] = ContextVar("pipeline_run_id", default="-")
_observer: ContextVar[Callable[[str, dict[str, Any]], None] | None] = ContextVar(
    "pipeline_observer", default=None,
)
_logger = logging.getLogger("hrclient.pipeline")
_logger.setLevel(logging.INFO)
_logger.propagate = False
_lock = RLock()
_log_path: Path | None = None


def log_event(event: str, *, level: int = logging.INFO, exc_info: bool = False, **details) -> None:
    data = {"run_id": _run_id.get(), **details}
    path = Path(os.getenv("PARSE_LOG_PATH") or DEFAULT_LOG_PATH).resolve()
    with _lock:
        global _log_path
        if _log_path != path:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=3,
                                          encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            for previous in _logger.handlers[:]:
                _logger.removeHandler(previous)
                previous.close()
            _logger.addHandler(handler)
            _log_path = path
        _logger.log(level, "%s %s", event, json.dumps(
            data, ensure_ascii=False, default=str,
        ), exc_info=exc_info)
    observer = _observer.get()
    if observer is not None:
        observer(event, data)


@contextmanager
def pipeline_run(
    *, run_id: str | None = None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> Iterator[str]:
    token = _run_id.set(run_id or (_run_id.get() if _run_id.get() != "-" else uuid.uuid4().hex[:12]))
    observer_token = _observer.set(on_event or _observer.get())
    try:
        yield _run_id.get()
    finally:
        _observer.reset(observer_token)
        _run_id.reset(token)
