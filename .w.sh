#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

MSG="${1:-update $(date '+%Y-%m-%d %H:%M')}"

git add .
git diff --cached --quiet && echo "Nessuna modifica da committare." || git commit -m "$MSG"
git push

clear
clear

# App: systemd se installato, altrimenti gunicorn daemon
if [[ -f /etc/systemd/system/mynutriapp.service ]]; then
  sudo systemctl restart mynutriapp.service
else
  if [[ -f logs/gunicorn.pid ]]; then
    kill "$(cat logs/gunicorn.pid)" 2>/dev/null || true
    sleep 1
  fi
  bash deploy/start-mynutriapp.sh
fi

sudo systemctl reload caddy

echo ""
echo "App locale:  curl http://127.0.0.1:8099/health"
echo "Sito pubblico: https://mynutriapp.cloud/"

if ! grep -q 'mynutriapp.cloud' /etc/caddy/Caddyfile 2>/dev/null; then
  echo ""
  echo "ATTENZIONE: Caddy non ha ancora mynutriapp.cloud. Esegui una volta:"
  echo "  sudo bash deploy/fix-caddy.sh"
fi
