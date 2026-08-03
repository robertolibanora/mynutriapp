#!/usr/bin/env bash
set -e

SIM_ID="D9C690E1-279C-42FF-B3E4-6859F104FBCE"
BUNDLE_ID="com.mynutriapp.mynutriApp"

cd "$(dirname "$0")/ios"

echo "▶ Avvio simulatore..."
xcrun simctl boot "$SIM_ID" 2>/dev/null || true
open -a Simulator
xcrun simctl bootstatus "$SIM_ID" -b

echo "▶ Compilo..."
xcodebuild \
  -workspace Runner.xcworkspace \
  -scheme Runner \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination "platform=iOS Simulator,id=$SIM_ID" \
  CODE_SIGNING_ALLOWED=NO

APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData \
  -path "*/Build/Products/Debug-iphonesimulator/Runner.app" \
  | head -n1)

if [ -z "$APP_PATH" ]; then
    echo "❌ Runner.app non trovato."
    exit 1
fi

echo "▶ Installo..."
xcrun simctl uninstall "$SIM_ID" "$BUNDLE_ID" >/dev/null 2>&1 || true
xcrun simctl install "$SIM_ID" "$APP_PATH"

echo "▶ Avvio..."
xcrun simctl launch "$SIM_ID" "$BUNDLE_ID"

echo
echo "✅ MyNutriApp avviata."