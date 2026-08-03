#!/usr/bin/env bash
# Avvia / rebuilda MyNutriApp sul simulatore Apple (iOS).
# Uso:
#   ./w.sh              → git pull + pub get + run sul simulator
#   ./w.sh rebuild      → pull + clean + pods + rebuild + run
#   ./w.sh --device "iPhone 16"   → device specifico
#
# Funziona dalla root del repo o da mobile_app/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/pubspec.yaml" ]]; then
  APP_DIR="$SCRIPT_DIR"
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [[ -f "$SCRIPT_DIR/mobile_app/pubspec.yaml" ]]; then
  APP_DIR="$SCRIPT_DIR/mobile_app"
  REPO_ROOT="$SCRIPT_DIR"
else
  echo "Errore: non trovo mobile_app/ (pubspec.yaml)"
  exit 1
fi

REBUILD=0
DEVICE=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    rebuild|--rebuild|-r)
      REBUILD=1
      shift
      ;;
    --device|-d)
      DEVICE="${2:-}"
      [[ -n "$DEVICE" ]] || { echo "Errore: --device richiede un nome"; exit 1; }
      shift 2
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if ! command -v flutter >/dev/null 2>&1; then
  echo "Errore: flutter non trovato nel PATH"
  exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Avviso: il simulatore iOS richiede macOS (ora: $(uname -s))"
fi

echo "→ Git pull"
(
  cd "$REPO_ROOT"
  git pull --ff-only
)

cd "$APP_DIR"

echo "→ Flutter pub get"
flutter pub get

if [[ "$REBUILD" -eq 1 ]]; then
  echo "→ Clean rebuild"
  flutter clean
  flutter pub get
  if [[ -d ios ]]; then
    echo "→ CocoaPods"
    (
      cd ios
      if command -v pod >/dev/null 2>&1; then
        pod install --repo-update
      else
        echo "Avviso: pod non trovato, salto pod install"
      fi
    )
  fi
fi

# Avvia il Simulator se disponibile
if command -v open >/dev/null 2>&1 && [[ "$(uname -s)" == "Darwin" ]]; then
  open -a Simulator 2>/dev/null || true
fi

# Scegli device iOS
TARGET=""
if [[ -n "$DEVICE" ]]; then
  TARGET="$DEVICE"
else
  # Preferisci un simulator iPhone già booted, altrimenti il primo iPhone disponibile
  TARGET="$(
    flutter devices 2>/dev/null \
      | awk -F'•' '
          /ios.*simulator|simulator.*ios/ {
            gsub(/^[ \t]+|[ \t]+$/, "", $1)
            gsub(/^[ \t]+|[ \t]+$/, "", $2)
            name=$1; id=$2
            if (name ~ /iPhone/) { print id; exit }
          }
        '
  )"
  if [[ -z "$TARGET" ]]; then
    TARGET="iphone"
  fi
fi

echo "→ Run su iOS simulator (device: $TARGET)"
exec flutter run -d "$TARGET" "${EXTRA_ARGS[@]}"
