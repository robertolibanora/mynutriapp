#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/mynutriapp}"
APP_USER="${APP_USER:-mynutriapp}"
SERVICE_NAME="mynutriapp"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Esegui come root: sudo $0"
  exit 1
fi

echo "==> Installazione dipendenze di sistema"
apt-get update
apt-get install -y \
  python3 python3-venv python3-dev \
  default-libmysqlclient-dev pkg-config \
  libmagic1 \
  mysql-server redis-server \
  debian-keyring debian-archive-keyring apt-transport-https curl gnupg

echo "==> Caddy"
if ! command -v caddy &>/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

echo "==> Utente di servizio"
if ! id "$APP_USER" &>/dev/null; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

echo "==> Directory applicazione"
mkdir -p "$APP_DIR"/{logs,static/uploads}
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "ATTENZIONE: copia .env in $APP_DIR/.env prima di avviare il servizio"
fi

echo "==> Virtualenv e dipendenze Python"
if [[ ! -d "$APP_DIR/venv" ]]; then
  sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
fi
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> Unit systemd"
install -m 644 "$APP_DIR/deploy/systemd/mynutriapp.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "==> Caddy (reverse proxy + HTTPS automatico)"
if [[ -f "$APP_DIR/deploy/caddy/Caddyfile" ]]; then
  if [[ -f /etc/caddy/Caddyfile ]]; then
    cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%Y%m%d%H%M%S)"
  fi
  install -m 644 "$APP_DIR/deploy/caddy/Caddyfile" /etc/caddy/Caddyfile
  caddy validate --config /etc/caddy/Caddyfile
  systemctl enable caddy
  systemctl reload caddy
fi

echo ""
echo "Installazione completata."
echo "Prossimi passi:"
echo "  1. Configura $APP_DIR/.env (DB_HOST=127.0.0.1, REDIS_HOST=127.0.0.1)"
echo "  2. Modifica /etc/caddy/Caddyfile con il tuo dominio"
echo "  3. Importa init.sql in MySQL se necessario"
echo "  4. sudo systemctl start $SERVICE_NAME"
echo "  5. sudo systemctl status $SERVICE_NAME caddy"
