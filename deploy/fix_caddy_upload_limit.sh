#!/bin/bash
# Alza il limite upload Caddy a 100MB (allineato ad AUDIO_MAX_MB)
set -euo pipefail
sudo sed -i 's/max_size 10MB/max_size 100MB/' /etc/caddy/Caddyfile
grep -n 'max_size' /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
echo "OK: Caddy request_body max_size = 100MB"
