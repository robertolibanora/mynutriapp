"""Lock file cross-process per job (trascrizione / estrazione).

Necessari quando ``JOB_BACKEND=subprocess``: i set in-memory non sono
condivisi tra Gunicorn e il processo figlio.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.config.config import Config


def _jobs_dir() -> Path:
    base = Path(Config.AUDIO_STORAGE_PATH).resolve().parent / "jobs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _lock_path(kind: str, consultation_id: int) -> Path:
    return _jobs_dir() / f"{kind}-{int(consultation_id)}.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_job_running(kind: str, consultation_id: int) -> bool:
    path = _lock_path(kind, consultation_id)
    if not path.is_file():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return False
    if _pid_alive(pid):
        return True
    path.unlink(missing_ok=True)
    return False


def acquire_job(kind: str, consultation_id: int) -> bool:
    """Crea il lock. Ritorna False se un job vivo è già in corso."""
    if is_job_running(kind, consultation_id):
        return False
    path = _lock_path(kind, consultation_id)
    path.write_text(str(os.getpid()), encoding="utf-8")
    return True


def claim_job(kind: str, consultation_id: int) -> None:
    """Aggiorna il lock con il PID del processo worker (subprocess)."""
    path = _lock_path(kind, consultation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")


def release_job(kind: str, consultation_id: int) -> None:
    path = _lock_path(kind, consultation_id)
    try:
        if not path.is_file():
            return
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            pid = int(raw)
            # Solo il processo owner (o un lock orfano) può rilasciare
            if pid not in (0, os.getpid()) and _pid_alive(pid):
                return
        path.unlink(missing_ok=True)
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
