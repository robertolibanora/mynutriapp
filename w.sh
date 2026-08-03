#!/usr/bin/env bash
# Avvio app paziente su simulatore iOS (Mac) contro staging.
# Usa flutter run (non solo xcodebuild) così i --dart-define e le
# dipendenze Dart (es. native_dio_adapter) entrano nel build.
set -euo pipefail

SIM_ID="${SIM_ID:-D9C690E1-279C-42FF-B3E4-6859F104FBCE}"
API_BASE_URL="${API_BASE_URL:-https://stage.mynutriapp.cloud}"
USE_MOCK_DATA="${USE_MOCK_DATA:-false}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT/mobile_app"

cd "$APP_DIR"

echo "▶ Dipendenze..."
flutter pub get

echo "▶ Simulatore $SIM_ID..."
xcrun simctl boot "$SIM_ID" 2>/dev/null || true
open -a Simulator
xcrun simctl bootstatus "$SIM_ID" -b

echo "▶ flutter run → $API_BASE_URL (mock=$USE_MOCK_DATA)"
exec flutter run \
  -d "$SIM_ID" \
  --dart-define="API_BASE_URL=$API_BASE_URL" \
  --dart-define="USE_MOCK_DATA=$USE_MOCK_DATA"
