#!/usr/bin/env bash
# MyNutriApp → un solo comando per aggiornare e aprire sul simulatore iOS.
#
# Uso (da mobile_app/ o dalla root del repo):
#   ./w.sh              → pull + build + run
#   ./w.sh rebuild      → pull + clean + pods + build + run
#   ./w.sh --device ID  → forza un device specifico
#
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
BUNDLE_ID="com.mynutriapp.mynutriApp"

while [[ $# -gt 0 ]]; do
  case "$1" in
    rebuild|--rebuild|-r)
      REBUILD=1
      shift
      ;;
    --device|-d)
      DEVICE="${2:-}"
      [[ -n "$DEVICE" ]] || { echo "Errore: --device richiede un nome/id"; exit 1; }
      shift 2
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

log() { echo "→ $*"; }
die() { echo "Errore: $*" >&2; exit 1; }

command -v flutter >/dev/null 2>&1 || die "flutter non trovato nel PATH"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Avviso: il simulatore iOS richiede macOS (ora: $(uname -s))"
fi

# ── 1) Aggiorna codice ──────────────────────────────────────────────
log "Git pull"
(
  cd "$REPO_ROOT"
  git pull --ff-only
)

cd "$APP_DIR"

# ── 2) Dipendenze / rebuild ─────────────────────────────────────────
log "Flutter pub get"
flutter pub get

if [[ "$REBUILD" -eq 1 ]]; then
  log "Clean rebuild"
  flutter clean
  flutter pub get
  if [[ -d ios ]] && command -v pod >/dev/null 2>&1; then
    log "CocoaPods"
    (cd ios && pod install --repo-update)
  fi
fi

# ── 3) Simulatore: uno solo, pulito, pronto ─────────────────────────
uuid_re='[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}'

pick_available_iphone() {
  # Preferisci "iPhone 17" semplice, poi qualsiasi iPhone available.
  local line id
  line="$(
    xcrun simctl list devices available 2>/dev/null \
      | grep -E 'iPhone' \
      | grep -vi 'unavailable' \
      | grep -E 'iPhone 17 \(' \
      | head -n1 || true
  )"
  if [[ -z "$line" ]]; then
    line="$(
      xcrun simctl list devices available 2>/dev/null \
        | grep -E 'iPhone' \
        | grep -vi 'unavailable' \
        | head -n1 || true
    )"
  fi
  id="$(printf '%s' "$line" | grep -Eo "$uuid_re" | head -n1 || true)"
  printf '%s' "$id"
}

wait_flutter_device() {
  local want="$1" found=""
  local i
  for i in $(seq 1 30); do
    if flutter devices 2>/dev/null | grep -q "$want"; then
      found="$want"
      break
    fi
    sleep 1
  done
  printf '%s' "$found"
}

TARGET=""

if [[ -n "$DEVICE" ]]; then
  TARGET="$DEVICE"
elif [[ "$(uname -s)" == "Darwin" ]] && command -v xcrun >/dev/null 2>&1; then
  log "Reset simulatori (ne resta uno solo)"
  # Chiudi tutto per evitare il bug "No such process" su sim appena creati/secondari
  xcrun simctl shutdown all 2>/dev/null || true
  # Chiudi anche l'app Simulator se aperta (stato pulito)
  osascript -e 'quit app "Simulator"' 2>/dev/null || true
  sleep 1

  TARGET="$(pick_available_iphone)"
  [[ -n "$TARGET" ]] || die "nessun iPhone simulator disponibile (apri Xcode una volta)"

  log "Boot $TARGET"
  open -a Simulator --args -CurrentDeviceUDID "$TARGET" 2>/dev/null || open -a Simulator
  xcrun simctl boot "$TARGET" 2>/dev/null || true

  log "Attendo boot completo"
  xcrun simctl bootstatus "$TARGET" -b

  log "Pulisco app precedente sul sim"
  xcrun simctl terminate "$TARGET" "$BUNDLE_ID" 2>/dev/null || true
  xcrun simctl uninstall "$TARGET" "$BUNDLE_ID" 2>/dev/null || true

  log "Attendo che Flutter veda il device"
  if [[ -z "$(wait_flutter_device "$TARGET")" ]]; then
    echo "Avviso: Flutter non elenca ancora $TARGET, provo comunque..."
  fi
else
  # Fallback non-Darwin / senza xcrun
  TARGET="$(
    flutter devices 2>/dev/null \
      | grep -E 'iPhone|simulator' \
      | grep -Eo "$uuid_re" \
      | head -n1 || true
  )"
  [[ -n "$TARGET" ]] || TARGET="iphone"
fi

[[ -n "$TARGET" ]] || die "nessun simulatore iOS trovato"

# ── 4) Build + run (con retry) ──────────────────────────────────────
run_flutter() {
  log "Run su iOS simulator (device: $TARGET)"
  if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    flutter run -d "$TARGET" --no-pub "${EXTRA_ARGS[@]}"
  else
    flutter run -d "$TARGET" --no-pub
  fi
}

recover_and_retry() {
  log "Launch fallito — recovery e secondo tentativo"
  if command -v xcrun >/dev/null 2>&1 && [[ "$TARGET" =~ ^[A-Fa-f0-9-]{36}$ ]]; then
    xcrun simctl terminate "$TARGET" "$BUNDLE_ID" 2>/dev/null || true
    xcrun simctl uninstall "$TARGET" "$BUNDLE_ID" 2>/dev/null || true
    xcrun simctl shutdown "$TARGET" 2>/dev/null || true
    sleep 1
    xcrun simctl boot "$TARGET" 2>/dev/null || true
    xcrun simctl bootstatus "$TARGET" -b
    open -a Simulator 2>/dev/null || true
    sleep 2
  fi
  run_flutter
}

if ! run_flutter; then
  recover_and_retry
fi
