#!/usr/bin/env python3
"""Job CLI retention GDPR: audio, pazienti, audit_log.

Uso:
  python scripts/gdpr_retention_purge.py           # esegue purge
  python scripts/gdpr_retention_purge.py --dry-run # solo conteggi
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Repo root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gdpr_retention")


def main() -> int:
    parser = argparse.ArgumentParser(description="GDPR retention purge")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Non elimina nulla, stampa solo i conteggi",
    )
    args = parser.parse_args()

    from wsgi import app
    from app.services.gdpr_service import run_retention_job

    with app.app_context():
        stats = run_retention_job(dry_run=args.dry_run)
        logger.info("Retention job completato: %s", stats)
        print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
