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

# ── 3) Simulatore: uno solo, pronto ─────────────────────────────────
uuid_re='[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}'

pick_available_iphone() {
  # Preferisci iPhone 17 (non Pro/Plus/Max) sull'runtime più recente.
  local id=""
  id="$(
    xcrun simctl list devices available 2>/dev/null | python3 -c '
import re, sys
text = sys.stdin.read()
runtime = None
best = None  # (runtime_name, udid)
udid_re = re.compile(r"([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})")
for line in text.splitlines():
    m = re.search(r"--\s*(iOS[^-]+)\s*--", line)
    if m:
        runtime = m.group(1).strip()
        continue
    if "unavailable" in line.lower():
        continue
    if "iPhone" not in line:
        continue
    um = udid_re.search(line)
    if not um or runtime is None:
        continue
    name = line.split("(")[0].strip()
    # Preferisci "iPhone 17" esatto, poi qualsiasi iPhone 17*, poi altri iPhone
    if name == "iPhone 17":
        score = 3
    elif name.startswith("iPhone 17"):
        score = 2
    else:
        score = 1
    cand = (score, runtime, um.group(1))
    if best is None or cand > best:
        best = cand
if best:
    print(best[2])
' 2>/dev/null || true
  )"
  if [[ -z "$id" ]]; then
    id="$(
      xcrun simctl list devices available 2>/dev/null \
        | grep -E 'iPhone' \
        | grep -vi 'unavailable' \
        | grep -Eo "$uuid_re" \
        | head -n1 || true
    )"
  fi
  printf '%s' "$id"
}

TARGET=""

if [[ -n "$DEVICE" ]]; then
  TARGET="$DEVICE"
elif [[ "$(uname -s)" == "Darwin" ]] && command -v xcrun >/dev/null 2>&1; then
  log "Reset simulatori (ne resta uno solo)"
  xcrun simctl shutdown all 2>/dev/null || true
  osascript -e 'quit app "Simulator"' 2>/dev/null || true
  sleep 1

  TARGET="$(pick_available_iphone)"
  [[ -n "$TARGET" ]] || die "nessun iPhone simulator disponibile (apri Xcode una volta)"

  log "Boot $TARGET"
  xcrun simctl boot "$TARGET" 2>/dev/null || true
  open -a Simulator

  log "Attendo boot completo"
  # bootstatus a volte esce con status strano anche se il sim è ok: non blocchiamo lo script
  xcrun simctl bootstatus "$TARGET" -b || true
  # Piccola pausa UI home screen
  sleep 3

  log "Pulisco app precedente sul sim"
  xcrun simctl terminate "$TARGET" "$BUNDLE_ID" 2>/dev/null || true
  xcrun simctl uninstall "$TARGET" "$BUNDLE_ID" 2>/dev/null || true
else
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
# NON chiamare "flutter devices" in loop: sul Mac può restare appeso sui wireless.
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
    xcrun simctl bootstatus "$TARGET" -b || true
    open -a Simulator 2>/dev/null || true
    sleep 3
  fi
  run_flutter
}

if ! run_flutter; then
  recover_and_retry
fi
