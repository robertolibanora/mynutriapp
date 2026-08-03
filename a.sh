#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-update $(date '+%Y-%m-%d %H:%M')}"
export PATH="$HOME/development/flutter/bin:$PATH"

echo "Ciao"

# Git
git add .
git diff --cached --quiet && echo "Nessuna modifica da committare." || git commit -m "$MSG"
git push
echo "Git fatto!"

# Backend
echo "Riavvio staging..."
sudo systemctl restart staging-mynutriapp.service
echo "Backend ok!"

# Mobile
echo "Build mobile..."
cd mobile_app
flutter pub get
flutter build apk --release \
  --dart-define=API_BASE_URL=https://stage.mynutriapp.cloud \
  --dart-define=USE_MOCK_DATA=false
cd ..
echo "APK: mobile_app/build/app/outputs/flutter-apk/app-release.apk"

# Log
echo "Giornale..."
journalctl -u staging-mynutriapp.service -f
