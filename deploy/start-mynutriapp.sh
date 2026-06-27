#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/mynutriapp"
PID_FILE="$APP_DIR/logs/gunicorn.pid"

cd "$APP_DIR"
mkdir -p logs static/uploads

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "MyNutriApp gia' in esecuzione (PID $(cat "$PID_FILE"))"
  exit 0
fi

set -a
# shellcheck disable=SC1091
source "$APP_DIR/.env"
set +a

exec "$APP_DIR/venv/bin/gunicorn" \
  -c deploy/gunicorn.conf.py \
  wsgi:app \
  --daemon \
  --pid "$PID_FILE" \
  --access-logfile "$APP_DIR/logs/access.log" \
  --error-logfile "$APP_DIR/logs/error.log"
