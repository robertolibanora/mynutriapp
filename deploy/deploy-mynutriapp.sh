#!/usr/bin/env bash
#
# Deploy MyNutriApp su questo VPS (operazioni privilegiate).
# Esegui:  sudo bash /var/www/mynutriapp/deploy/deploy-mynutriapp.sh
#
set -euo pipefail

APP_DIR="/var/www/mynutriapp"
APP_USER="noira"
APP_GROUP="noira"
DOMAIN="mynutriapp.cloud"
CADDYFILE="/etc/caddy/Caddyfile"
SYSTEMD_DIR="/etc/systemd/system"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Esegui come root:  sudo bash $0"
  exit 1
fi

echo "==> 1/5  Directory di stato (logs)"
mkdir -p "$APP_DIR/logs"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR/logs" "$APP_DIR/static/uploads"

echo "==> 2/5  Database MySQL (crea DB + utente + import schema)"
# Carica le credenziali applicative dal .env
set -a
# shellcheck disable=SC1091
source <(grep -E '^(DB_NAME|DB_USER|DB_PASSWORD)=' "$APP_DIR/.env")
set +a

mysql <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

echo "    -> import init.sql (idempotente: CREATE TABLE IF NOT EXISTS)"
mysql "${DB_NAME}" < "$APP_DIR/init.sql"

echo "==> 3/5  Unit systemd"
install -m 644 "$APP_DIR/deploy/systemd/mynutriapp.service"          "$SYSTEMD_DIR/mynutriapp.service"
install -m 644 "$APP_DIR/deploy/systemd/mynutriapp-scadenze.service" "$SYSTEMD_DIR/mynutriapp-scadenze.service"
install -m 644 "$APP_DIR/deploy/systemd/mynutriapp-scadenze.timer"   "$SYSTEMD_DIR/mynutriapp-scadenze.timer"
systemctl daemon-reload
systemctl enable --now mynutriapp.service
systemctl enable --now mynutriapp-scadenze.timer

echo "==> 4/5  Caddy (${DOMAIN})"
if grep -q "${DOMAIN}" "$CADDYFILE"; then
  echo "    -> blocco ${DOMAIN} gia' presente in $CADDYFILE, salto"
else
  cp "$CADDYFILE" "${CADDYFILE}.bak.$(date +%Y%m%d%H%M%S)"
  cat >> "$CADDYFILE" <<'CADDY'

####################################
# MYNUTRIAPP
####################################
mynutriapp.cloud {
	encode gzip zstd

	@static path /static/*
	handle @static {
		root * /var/www/mynutriapp/static
		uri strip_prefix /static
		file_server
	}

	handle {
		reverse_proxy 127.0.0.1:8099
	}

	request_body {
		max_size 10MB
	}
}

www.mynutriapp.cloud {
	redir https://mynutriapp.cloud{uri} permanent
}
CADDY
  echo "    -> blocco aggiunto"
fi
caddy validate --config "$CADDYFILE"
systemctl reload caddy

echo "==> 5/5  Verifica"
systemctl --no-pager --lines=0 status mynutriapp.service || true
systemctl list-timers mynutriapp-scadenze.timer --no-pager || true
echo ""
echo "Fatto. Test rapido:"
echo "  curl -i http://127.0.0.1:8099/health"
echo "  curl -i https://${DOMAIN}/health"
