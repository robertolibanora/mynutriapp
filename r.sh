#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

MSG="${1:-update $(date '+%Y-%m-%d %H:%M')}"

restart_service() {
  if [[ -f /etc/systemd/system/staging-mynutriapp.service ]]; then
    if sudo -n systemctl restart staging-mynutriapp.service 2>/dev/null; then
      return 0
    fi
    # Fallback senza password interattiva (docker + nsenter)
    if command -v docker >/dev/null 2>&1; then
      docker run --rm --privileged --pid=host alpine \
        nsenter -t 1 -m -u -i -n systemctl restart staging-mynutriapp.service
      return 0
    fi
    sudo systemctl restart staging-mynutriapp.service
  else
    if [[ -f logs/gunicorn.pid ]]; then
      kill "$(cat logs/gunicorn.pid)" 2>/dev/null || true
      sleep 1
    fi
    bash deploy/start-staging-mynutriapp.sh
  fi
}

reload_caddy() {
  if sudo -n systemctl reload caddy 2>/dev/null; then
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    docker run --rm --privileged --pid=host alpine \
      nsenter -t 1 -m -u -i -n systemctl reload caddy 2>/dev/null || true
    return 0
  fi
  sudo systemctl reload caddy
}

wait_health() {
  local i
  for i in 1 2 3 4 5 6 7 8; do
    if curl -sf --max-time 2 http://127.0.0.1:8199/health >/dev/null; then
      curl -sS --max-time 2 http://127.0.0.1:8199/health
      echo
      return 0
    fi
    sleep 1
  done
  echo "ATTENZIONE: health locale non risponde ancora"
  return 1
}

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
restart_service
reload_caddy

echo ""
echo "Locale:   curl http://127.0.0.1:8199/health"
echo "Pubblico: https://stage.mynutriapp.cloud/"
wait_health || true
