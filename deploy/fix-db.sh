#!/usr/bin/env bash
# Crea database, utente MySQL e importa init.sql
# Esegui: sudo bash /var/www/mynutriapp/deploy/fix-db.sh
set -euo pipefail

APP_DIR="/var/www/mynutriapp"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Esegui: sudo bash $0"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source <(grep -E '^(DB_NAME|DB_USER|DB_PASSWORD)=' "$APP_DIR/.env")
set +a

echo "==> Database ${DB_NAME}, utente ${DB_USER}"

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

echo "==> Import schema (init.sql)"
mysql "${DB_NAME}" < "$APP_DIR/init.sql"

echo "==> Test connessione app"
mysql -h127.0.0.1 -u"${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" -e "SHOW TABLES;" | head -10

echo ""
echo "OK. Riavvia l'app:"
echo "  kill \$(cat $APP_DIR/logs/gunicorn.pid) 2>/dev/null; bash $APP_DIR/deploy/start-mynutriapp.sh"
