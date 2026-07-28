"""Esecuzione job in background (thread oggi, Celery+Redis domani).

Il router usa :class:`BackgroundTasks` (API simile a FastAPI). La scelta del
backend è in ``JOB_BACKEND``; migrare a Celery richiede solo un nuovo runner
qui, senza toccare la logica di trascrizione.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from flask import Flask, current_app

logger = logging.getLogger(__name__)

TaskFunc = Callable[..., Any]


class BackgroundTasks:
    """Coda leggera di task post-response (compatibile con lo stile FastAPI)."""

    def __init__(self) -> None:
        self._tasks: list[tuple[TaskFunc, tuple, dict]] = []

    def add_task(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        self._tasks.append((func, args, kwargs))

    def __iter__(self):
        return iter(self._tasks)


class JobRunner:
    """Interfaccia runner: enqueue di una callable già isolata."""

    def enqueue(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError


class ThreadBackgroundRunner(JobRunner):
    """Esegue i task in thread daemon con app context Flask."""

    def enqueue(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        app: Flask = current_app._get_current_object()  # type: ignore[attr-defined]

        def _run() -> None:
            with app.app_context():
                try:
                    func(*args, **kwargs)
                except Exception:  # noqa: BLE001
                    logger.exception("Background task fallito: %s", getattr(func, "__name__", func))

        thread = threading.Thread(
            target=_run,
            name=f"bg-{getattr(func, '__name__', 'task')}",
            daemon=True,
        )
        thread.start()


class CeleryJobRunner(JobRunner):
    """Placeholder: sostituire con delay Celery quando si introduce Redis worker."""

    def enqueue(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "JOB_BACKEND=celery non ancora configurato. "
            "Usa JOB_BACKEND=thread oppure implementa il task Celery."
        )


class SyncJobRunner(JobRunner):
    """Esegue subito nel thread corrente (test / debug)."""

    def enqueue(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        func(*args, **kwargs)


def get_job_runner() -> JobRunner:
    from app.config.config import Config

    backend = (Config.JOB_BACKEND or "thread").strip().lower()
    if backend in ("thread", "background", "background_tasks"):
        return ThreadBackgroundRunner()
    if backend == "sync":
        return SyncJobRunner()
    if backend == "celery":
        return CeleryJobRunner()
    raise RuntimeError(f"JOB_BACKEND sconosciuto: {backend!r}")


def dispatch_background_tasks(tasks: BackgroundTasks) -> None:
    """Spedisce tutti i task accumulati al runner configurato."""
    runner = get_job_runner()
    for func, args, kwargs in tasks:
        runner.enqueue(func, *args, **kwargs)
