#!/usr/bin/env bash
# Corregge la porta MyNutriApp in Caddy (8099, non 8999 condivisa con Puttantour)
set -euo pipefail

CADDYFILE="/etc/caddy/Caddyfile"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Esegui: sudo bash $0"
  exit 1
fi

if ! grep -q 'mynutriapp.cloud' "$CADDYFILE"; then
  echo "Blocco mynutriapp.cloud assente. Esegui: sudo bash /var/www/mynutriapp/deploy/fix-caddy.sh"
  exit 1
fi

cp "$CADDYFILE" "${CADDYFILE}.bak.$(date +%Y%m%d%H%M%S)"

python3 <<'PY'
from pathlib import Path
import re

path = Path("/etc/caddy/Caddyfile")
text = path.read_text()
pattern = r'(mynutriapp\.cloud\s*\{.*?handle\s*\{[^}]*reverse_proxy\s*)127\.0\.0\.1:\d+'
new_text, n = re.subn(pattern, r'\g<1>127.0.0.1:8099', text, count=1, flags=re.S)
if n != 1:
    raise SystemExit("Impossibile aggiornare la porta nel blocco mynutriapp.cloud")
path.write_text(new_text)
print("Caddy: mynutriapp.cloud -> 127.0.0.1:8099")
PY

caddy validate --config "$CADDYFILE"
systemctl reload caddy
echo "OK: https://mynutriapp.cloud/"
