#!/usr/bin/env bash
# MyNutriApp → un solo comando: pull + sim + build + run su iOS.
#
# Uso (da root repo o da mobile_app/):
#   ./w.sh              → pull + run
#   ./w.sh rebuild      → pull + clean completo + run
#   ./w.sh --device ID  → forza device
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
LOG_DIR="$APP_DIR/build"
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/w-flutter-run.log"
BUILD_LOG="$LOG_DIR/w-xcode-build.log"

while [[ $# -gt 0 ]]; do
  case "$1" in
    rebuild|--rebuild|-r) REBUILD=1; shift ;;
    --device|-d)
      DEVICE="${2:-}"
      [[ -n "$DEVICE" ]] || { echo "Errore: --device richiede un nome/id"; exit 1; }
      shift 2
      ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

log() { echo "→ $*"; }
die() { echo "Errore: $*" >&2; exit 1; }

command -v flutter >/dev/null 2>&1 || die "flutter non trovato nel PATH"
[[ "$(uname -s)" == "Darwin" ]] || echo "Avviso: simulatore iOS richiede macOS"

# ── 1) Codice ───────────────────────────────────────────────────────
log "Git pull"
(cd "$REPO_ROOT" && git pull --ff-only)
cd "$APP_DIR"

# ── 2) Dipendenze Flutter / iOS ─────────────────────────────────────
prepare_flutter() {
  log "Flutter pub get"
  flutter pub get
  # Assicura artifact iOS (SPM / engine) dopo clone fresco
  flutter precache --ios >/dev/null 2>&1 || true

  # Verifica che Generated.xcconfig punti a un Flutter reale su QUESTO Mac
  local gen="ios/Flutter/Generated.xcconfig"
  if [[ -f "$gen" ]]; then
    local root
    root="$(grep '^FLUTTER_ROOT=' "$gen" | cut -d= -f2- || true)"
    if [[ -z "$root" || ! -d "$root" ]]; then
      log "Generated.xcconfig non valido — regenero"
      rm -f "$gen" ios/Flutter/flutter_export_environment.sh
      flutter pub get
    fi
  fi
}

deep_clean() {
  log "Clean completo (Flutter + DerivedData Runner)"
  flutter clean
  rm -rf build
  rm -rf ios/Flutter/ephemeral
  rm -f ios/Flutter/Generated.xcconfig ios/Flutter/flutter_export_environment.sh
  rm -rf ~/Library/Developer/Xcode/DerivedData/Runner-* 2>/dev/null || true
  prepare_flutter
}

prepare_flutter
if [[ "$REBUILD" -eq 1 ]]; then
  deep_clean
fi

# ── 3) Simulatore ───────────────────────────────────────────────────
uuid_re='[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}'

pick_available_iphone() {
  xcrun simctl list devices available 2>/dev/null | python3 -c '
import re, sys
text = sys.stdin.read()
runtime = None
best = None
udid_re = re.compile(r"([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})")
for line in text.splitlines():
    m = re.search(r"--\s*(iOS[^-]+)\s*--", line)
    if m:
        runtime = m.group(1).strip()
        continue
    if "unavailable" in line.lower() or "iPhone" not in line or runtime is None:
        continue
    um = udid_re.search(line)
    if not um:
        continue
    name = line.split("(")[0].strip()
    score = 3 if name == "iPhone 17" else (2 if name.startswith("iPhone 17") else 1)
    cand = (score, runtime, um.group(1))
    if best is None or cand > best:
        best = cand
if best:
    print(best[2])
' 2>/dev/null || true
}

is_booted() {
  local id="$1"
  xcrun simctl list devices booted 2>/dev/null | grep -q "$id"
}

wait_until_booted() {
  local id="$1" i
  for i in $(seq 1 60); do
    if is_booted "$id"; then
      # home screen / SpringBoard pronti
      sleep 2
      return 0
    fi
    sleep 1
  done
  return 1
}

ensure_simulator() {
  local id="$1"
  log "Preparo simulator $id"
  open -a Simulator >/dev/null 2>&1 || true

  if ! is_booted "$id"; then
    # Non spegnere TUTTI i sim se quello giusto è già su; spegni solo gli altri
    xcrun simctl list devices booted 2>/dev/null \
      | grep -Eo "$uuid_re" \
      | while read -r other; do
          [[ "$other" == "$id" ]] && continue
          xcrun simctl shutdown "$other" 2>/dev/null || true
        done
    xcrun simctl boot "$id" 2>/dev/null || true
  fi

  # bootstatus è rumoroso e a volte buggato (4294967295): usiamo lo stato Booted
  log "Attendo che il sim sia Booted"
  if ! wait_until_booted "$id"; then
    log "Boot lento — erase + reboot"
    xcrun simctl shutdown "$id" 2>/dev/null || true
    xcrun simctl erase "$id" 2>/dev/null || true
    xcrun simctl boot "$id" 2>/dev/null || true
    open -a Simulator >/dev/null 2>&1 || true
    wait_until_booted "$id" || die "simulatore non boota ($id)"
  fi

  xcrun simctl terminate "$id" "$BUNDLE_ID" 2>/dev/null || true
  xcrun simctl uninstall "$id" "$BUNDLE_ID" 2>/dev/null || true
}

TARGET="${DEVICE:-}"
if [[ -z "$TARGET" ]]; then
  command -v xcrun >/dev/null 2>&1 || die "xcrun/Xcode non trovato"
  TARGET="$(pick_available_iphone)"
  [[ -n "$TARGET" ]] || die "nessun iPhone simulator disponibile"
fi

if [[ "$TARGET" =~ ^[A-Fa-f0-9-]{36}$ ]]; then
  ensure_simulator "$TARGET"
fi

# ── 4) Run ──────────────────────────────────────────────────────────
run_flutter() {
  log "Run su iOS simulator (device: $TARGET)"
  # Log completo per capire exit 255
  set +e
  if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    flutter run -d "$TARGET" --no-pub "${EXTRA_ARGS[@]}" 2>&1 | tee "$RUN_LOG"
  else
    flutter run -d "$TARGET" --no-pub 2>&1 | tee "$RUN_LOG"
  fi
  local rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

dump_xcode_error() {
  log "Raccolgo errore Xcode dettagliato…"
  set +e
  flutter build ios --simulator --debug --no-pub -v >"$BUILD_LOG" 2>&1
  set -e
  echo
  echo "======== Ultime righe errore (anche in $BUILD_LOG) ========"
  # Mostra errori tipici, non tutto il verbose
  grep -E 'error:|fatal error|❌|The following build commands failed|BUILD FAILED|Could not|Unable to|Exit|xcodebuild' "$BUILD_LOG" \
    | tail -n 40 \
    || tail -n 40 "$BUILD_LOG"
  echo "=========================================================="
}

recover() {
  log "Recovery: clean iOS + DerivedData e riprovo"
  rm -rf build/ios
  rm -rf ~/Library/Developer/Xcode/DerivedData/Runner-* 2>/dev/null || true
  rm -rf ios/Flutter/ephemeral
  rm -f ios/Flutter/Generated.xcconfig ios/Flutter/flutter_export_environment.sh
  flutter pub get
  if [[ "$TARGET" =~ ^[A-Fa-f0-9-]{36}$ ]]; then
    xcrun simctl shutdown "$TARGET" 2>/dev/null || true
    xcrun simctl erase "$TARGET" 2>/dev/null || true
    ensure_simulator "$TARGET"
  fi
}

if ! run_flutter; then
  recover
  if ! run_flutter; then
    dump_xcode_error
    die "build/run fallito due volte. Apri $BUILD_LOG oppure esegui: flutter run -d $TARGET -v"
  fi
fi
