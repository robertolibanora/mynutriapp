#!/usr/bin/env bash
# Configura Caddy per mynutriapp.cloud (richiede root, una tantum)
set -euo pipefail

CADDYFILE="/etc/caddy/Caddyfile"
DOMAIN="mynutriapp.cloud"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Esegui: sudo bash $0"
  exit 1
fi

if grep -q "$DOMAIN" "$CADDYFILE"; then
  echo "Blocco $DOMAIN gia' presente."
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
  echo "Blocco $DOMAIN aggiunto."
fi

caddy validate --config "$CADDYFILE"
systemctl reload caddy
echo "OK: https://${DOMAIN}/"
