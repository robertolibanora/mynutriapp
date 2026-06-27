import os
from datetime import datetime, timedelta

import click

from app import db
from app.models import PositionLog


def _retention_days_from_env_or_arg(days_opt: int | None) -> int:
    if days_opt is not None:
        return days_opt
    return int(os.getenv('POSITION_LOG_RETENTION_DAYS', '7'))


def purge_position_logs_older_than(*, retention_days: int, dry_run: bool = False) -> int:
    """
    Elimina (o conta, se dry_run) i PositionLog con recorded_at antecedente al cutoff UTC.
    Ritorna il numero di righe eliminate o contate.
    """
    if retention_days < 1:
        raise ValueError('retention_days deve essere >= 1')
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    q = db.session.query(PositionLog).filter(PositionLog.recorded_at < cutoff)
    if dry_run:
        return q.count()
    deleted = q.delete(synchronize_session=False)
    db.session.commit()
    return deleted


def register_cli_commands(app):
    @app.cli.command('purge-position-logs')
    @click.option(
        '--days',
        type=int,
        default=None,
        help='Giorni di retention (default: variabile POSITION_LOG_RETENTION_DAYS o 7)',
    )
    @click.option(
        '--dry-run',
        is_flag=True,
        help='Solo conteggio delle righe che verrebbero eliminate',
    )
    def purge_position_logs_command(days, dry_run):
        """Rimuove i punti GPS (PositionLog) con recorded_at più vecchio della retention."""
        n_days = _retention_days_from_env_or_arg(days)
        cutoff = datetime.utcnow() - timedelta(days=n_days)
        if dry_run:
            n = purge_position_logs_older_than(retention_days=n_days, dry_run=True)
            click.echo(
                f'Dry-run: {n} righe (recorded_at < {cutoff.isoformat()} UTC) '
                f'— retention {n_days} giorni'
            )
            return
        n = purge_position_logs_older_than(retention_days=n_days, dry_run=False)
        click.echo(
            f'Eliminate {n} righe PositionLog (cutoff {cutoff.isoformat()} UTC, {n_days} giorni).'
        )
