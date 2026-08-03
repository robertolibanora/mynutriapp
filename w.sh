#!/usr/bin/env bash
# Avvia MyNutriApp sul simulatore iOS puntando allo staging.
# Uso (da root repo o da mobile_app/): ./w.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/pubspec.yaml" ]]; then
  APP_DIR="$SCRIPT_DIR"
elif [[ -f "$SCRIPT_DIR/mobile_app/pubspec.yaml" ]]; then
  APP_DIR="$SCRIPT_DIR/mobile_app"
else
  echo "Errore: non trovo mobile_app/" >&2
  exit 1
fi

SIM_ID="${SIM_ID:-D9C690E1-279C-42FF-B3E4-6859F104FBCE}"
API_BASE_URL="${API_BASE_URL:-https://stage.mynutriapp.cloud}"

cd "$APP_DIR"

echo "▶ Check API staging..."
if ! curl -fsS --max-time 8 "$API_BASE_URL/api/v1/health" >/dev/null; then
  echo "Avviso: $API_BASE_URL/api/v1/health non risponde. Continuo comunque." >&2
else
  echo "   OK $API_BASE_URL/api/v1/health"
fi

echo "▶ Avvio simulatore $SIM_ID..."
xcrun simctl boot "$SIM_ID" 2>/dev/null || true
open -a Simulator >/dev/null 2>&1 || true
xcrun simctl bootstatus "$SIM_ID" -b

echo "▶ flutter pub get..."
flutter pub get

echo "▶ flutter run (API_BASE_URL=$API_BASE_URL)..."
exec flutter run \
  -d "$SIM_ID" \
  --dart-define="API_BASE_URL=$API_BASE_URL" \
  --dart-define=USE_MOCK_DATA=false \
  "$@"
