#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-update $(date '+%Y-%m-%d %H:%M')}"

echo "1) Git"
git add .
git diff --cached --quiet && echo "   niente da committare" || git commit -m "$MSG"
git push

echo "2) Restart"
sudo systemctl restart staging-mynutriapp.service
echo "   ok → https://stage.mynutriapp.cloud"

echo "3) Log"
journalctl -u staging-mynutriapp.service -f
