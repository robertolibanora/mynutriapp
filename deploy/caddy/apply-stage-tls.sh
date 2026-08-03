#!/usr/bin/env bash
# Applica il blocco TLS staging in /etc/caddy/Caddyfile e forza re-issue.
# Richiede sudo. Uso: ./deploy/caddy/apply-stage-tls.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/deploy/caddy/stage.mynutriapp.cloud.caddy"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
CERT_DIR="${CERT_DIR:-/var/lib/caddy/.local/share/caddy/certificates}"

if [[ ! -f "$SRC" ]]; then
  echo "Manca $SRC" >&2
  exit 1
fi

echo "▶ Backup Caddyfile"
sudo cp -a "$CADDYFILE" "${CADDYFILE}.bak.$(date +%Y%m%d%H%M%S)"

echo "▶ Sostituisco blocco stage.mynutriapp.cloud"
sudo python3 - <<PY
from pathlib import Path
src = Path("$SRC").read_text()
path = Path("$CADDYFILE")
text = path.read_text()
start = text.find("stage.mynutriapp.cloud {")
if start < 0:
    raise SystemExit("blocco stage.mynutriapp.cloud non trovato")
# trova inizio sezione commentata sopra se presente
hdr = text.rfind("####################################\n# MYNUTRIAPP STAGING", 0, start)
if hdr >= 0:
    start = hdr
depth = 0
i = text.find("{", start)
end = None
for j, ch in enumerate(text[i:], start=i):
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
        if depth == 0:
            end = j + 1
            break
if end is None:
    raise SystemExit("chiusura blocco non trovata")
# salta newline finali
while end < len(text) and text[end] in "\n":
    end += 1
new = text[:start] + src.rstrip() + "\n" + text[end:]
path.write_text(new)
print("ok, blocco aggiornato")
PY

echo "▶ Validate"
sudo caddy validate --config "$CADDYFILE"

echo "▶ Rimuovo cert cached stage (se presente)"
sudo find "$CERT_DIR" -type d -name 'stage.mynutriapp.cloud' -print -exec rm -rf {} + 2>/dev/null || true

echo "▶ Reload Caddy"
sudo systemctl reload caddy

sleep 2
echo "▶ Issuer attuale:"
echo | openssl s_client -connect stage.mynutriapp.cloud:443 -servername stage.mynutriapp.cloud 2>/dev/null \
  | openssl x509 -noout -issuer -subject
echo "Fatto."
