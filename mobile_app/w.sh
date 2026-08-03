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

pick_ios_simulator() {
  # Usa JSON di flutter (affidabile); fallback su UUID nel testo.
  local id=""
  if command -v python3 >/dev/null 2>&1; then
    id="$(
      flutter devices --machine 2>/dev/null | python3 -c '
import json, sys
try:
    devices = json.load(sys.stdin)
except Exception:
    sys.exit(0)
# Preferisci iPhone simulator
for d in devices:
    if d.get("targetPlatform") != "ios":
        continue
    if not d.get("emulator", False):
        continue
    name = d.get("name") or ""
    if "iPhone" in name:
        print(d.get("id", ""))
        sys.exit(0)
for d in devices:
    if d.get("targetPlatform") == "ios" and d.get("emulator", False):
        print(d.get("id", ""))
        sys.exit(0)
' 2>/dev/null || true
    )"
  fi
  if [[ -z "$id" ]]; then
    id="$(
      flutter devices 2>/dev/null \
        | grep -E 'iPhone|simulator' \
        | grep -Eo '[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}' \
        | head -n1 || true
    )"
  fi
  printf '%s' "$id"
}

# Avvia il Simulator se disponibile
if command -v open >/dev/null 2>&1 && [[ "$(uname -s)" == "Darwin" ]]; then
  open -a Simulator 2>/dev/null || true
  # Se nessun sim è booted, avvia un iPhone di default
  if command -v xcrun >/dev/null 2>&1; then
    if ! xcrun simctl list devices booted 2>/dev/null | grep -q 'Booted'; then
      BOOT_UDID="$(
        xcrun simctl list devices available 2>/dev/null \
          | grep -E 'iPhone' \
          | grep -Eo '[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}' \
          | head -n1 || true
      )"
      if [[ -n "${BOOT_UDID:-}" ]]; then
        echo "→ Boot simulator $BOOT_UDID"
        xcrun simctl boot "$BOOT_UDID" 2>/dev/null || true
      fi
    fi
  fi
fi

# Scegli device iOS (attendi che Flutter lo veda)
TARGET=""
if [[ -n "$DEVICE" ]]; then
  TARGET="$DEVICE"
else
  echo "→ Cerco simulatore iOS..."
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    TARGET="$(pick_ios_simulator)"
    [[ -n "$TARGET" ]] && break
    sleep 1
  done
fi

if [[ -z "$TARGET" ]]; then
  echo "Errore: nessun simulatore iOS trovato."
  echo "Apri Xcode → Open Developer Tool → Simulator, poi riprova."
  flutter devices || true
  exit 1
fi

echo "→ Run su iOS simulator (device: $TARGET)"
# macOS bash + set -u: array vuoto → unbound variable
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  exec flutter run -d "$TARGET" "${EXTRA_ARGS[@]}"
else
  exec flutter run -d "$TARGET"
fi
