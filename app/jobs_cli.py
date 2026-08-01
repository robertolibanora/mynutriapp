"""CLI per job pesanti in processo isolato (evita OOM sui worker Gunicorn).

Uso:
    python -m app.jobs_cli transcribe <consultation_id>
    python -m app.jobs_cli extract <consultation_id>
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger("jobs_cli")


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    command, raw_id = args[0], args[1]
    try:
        consultation_id = int(raw_id)
    except ValueError:
        logger.error("consultation_id non valido: %s", raw_id)
        return 2

    # Import lazy dopo dotenv
    from wsgi import app

    with app.app_context():
        if command == "transcribe":
            from app.services.diario_transcription_service import run_transcription_job

            logger.info("Avvio trascrizione consultation=%s", consultation_id)
            run_transcription_job(consultation_id)
            return 0
        if command == "extract":
            from app.services.diario_extraction_service import run_diary_extraction_job

            logger.info("Avvio estrazione diary consultation=%s", consultation_id)
            run_diary_extraction_job(consultation_id)
            return 0

    logger.error("Comando sconosciuto: %s", command)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
