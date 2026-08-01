"""Esecuzione job in background (subprocess / thread / Celery).

Il router usa :class:`BackgroundTasks` (API simile a FastAPI).
Per Whisper su VPS piccole preferire ``JOB_BACKEND=subprocess``: il modello
gira in un processo isolato e un OOM non abbatte i worker Gunicorn (502).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from flask import Flask, current_app

logger = logging.getLogger(__name__)

TaskFunc = Callable[..., Any]

# Job pesanti espposti via ``python -m app.jobs_cli``
_SUBPROCESS_JOBS = {
    "run_transcription_job": "transcribe",
    "run_diary_extraction_job": "extract",
}


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


class SubprocessJobRunner(JobRunner):
    """Esegue job pesanti in un interprete Python separato.

    Se la callable non è mappata (job leggero), fa fallback al thread runner.
    """

    def enqueue(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        name = getattr(func, "__name__", "")
        cli_cmd = _SUBPROCESS_JOBS.get(name)
        if cli_cmd is None or len(args) != 1 or kwargs:
            ThreadBackgroundRunner().enqueue(func, *args, **kwargs)
            return

        root = Path(__file__).resolve().parents[3]
        python = sys.executable
        consultation_id = args[0]
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"job-{cli_cmd}-{consultation_id}.log"

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        try:
            with log_path.open("a", encoding="utf-8") as logf:
                proc = subprocess.Popen(
                    [python, "-m", "app.jobs_cli", cli_cmd, str(consultation_id)],
                    cwd=str(root),
                    env=env,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except Exception:
            # Evita lock orfani se lo spawn fallisce
            try:
                from app.services.job_locks import release_job

                release_job(cli_cmd, int(consultation_id))
            except Exception:  # noqa: BLE001
                pass
            raise
        logger.info(
            "Job subprocess avviato: %s consultation=%s pid=%s log=%s",
            cli_cmd,
            consultation_id,
            proc.pid,
            log_path,
        )


class CeleryJobRunner(JobRunner):
    """Placeholder: sostituire con delay Celery quando si introduce Redis worker."""

    def enqueue(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError(
            "JOB_BACKEND=celery non ancora configurato. "
            "Usa JOB_BACKEND=subprocess oppure implementa il task Celery."
        )


class SyncJobRunner(JobRunner):
    """Esegue subito nel thread corrente (test / debug)."""

    def enqueue(self, func: TaskFunc, *args: Any, **kwargs: Any) -> None:
        func(*args, **kwargs)


def get_job_runner() -> JobRunner:
    from app.config.config import Config

    backend = (Config.JOB_BACKEND or "subprocess").strip().lower()
    if backend in ("subprocess", "process", "isolated"):
        return SubprocessJobRunner()
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
