#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

MSG="${1:-update $(date '+%Y-%m-%d %H:%M')}"

echo "==> Push"
git add .
git diff --cached --quiet && echo "Nessuna modifica da committare." || git commit -m "$MSG"
git push

echo ""
echo "==> Rebuild (dipendenze)"
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt

echo ""
echo "==> Restart"
if [[ -f /etc/systemd/system/staging-mynutriapp.service ]]; then
  sudo systemctl restart staging-mynutriapp.service
else
  if [[ -f logs/gunicorn.pid ]]; then
    kill "$(cat logs/gunicorn.pid)" 2>/dev/null || true
    sleep 1
  fi
  bash deploy/start-staging-mynutriapp.sh
fi

sudo systemctl reload caddy

echo ""
echo "Locale:   curl http://127.0.0.1:8199/health"
echo "Pubblico: https://stage.mynutriapp.cloud/"
curl -sf --max-time 5 http://127.0.0.1:8199/health && echo || echo "ATTENZIONE: health locale non risponde ancora"
