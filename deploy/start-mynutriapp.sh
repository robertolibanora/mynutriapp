#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/mynutriapp"
PID_FILE="$APP_DIR/logs/gunicorn.pid"

cd "$APP_DIR"
mkdir -p logs static/uploads

# Legge la porta attesa da .env (default 8099, come Caddy)
BIND="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d ' \"')"
BIND="${BIND:-127.0.0.1:8099}"
PORT="${BIND##*:}"

health_ok() {
  curl -sf --max-time 2 "http://${BIND}/health" >/dev/null 2>&1
}

port_listening() {
  ss -tln 2>/dev/null | grep -q ":${PORT} " || \
    netstat -tln 2>/dev/null | grep -q ":${PORT} "
}

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    if health_ok; then
      echo "MyNutriApp gia' in esecuzione su ${BIND} (PID ${OLD_PID})"
      exit 0
    fi
    echo "PID ${OLD_PID} presente ma ${BIND}/health non risponde: riavvio..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

# Processo zombie sulla porta senza PID file valido
if port_listening && ! health_ok; then
  echo "ATTENZIONE: porta ${PORT} occupata ma /health non risponde. Verifica con: ss -tlnp | grep ${PORT}"
fi

exec "$APP_DIR/venv/bin/gunicorn" \
  -c deploy/gunicorn.conf.py \
  wsgi:app \
  --daemon \
  --pid "$PID_FILE" \
  --access-logfile "$APP_DIR/logs/access.log" \
  --error-logfile "$APP_DIR/logs/error.log"
