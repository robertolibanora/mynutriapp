#!/usr/bin/env bash
# MyNutriApp iOS — clean → CocoaPods → build → install → launch
#
# Usa SEMPRE DerivedData di progetto e installa sul simulatore
# esclusivamente la Runner.app appena compilata.
#
# Uso (da repo root o da mobile_app/):
#   ./w.sh              → clean + build + install + launch
#   ./w.sh --no-clean   → skip flutter clean
#   ./w.sh --device ID  → forza simulatore (UDID o nome)
#   ./w.sh --no-pull    → non eseguire git pull
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
  echo "Errore: non trovo mobile_app/ (pubspec.yaml)" >&2
  exit 1
fi

DO_CLEAN=1
DO_PULL=1
DEVICE="${SIM_ID:-}"
EXTRA_ARGS=()
BUNDLE_ID="com.mynutriapp.mynutriApp"
API_BASE_URL="${API_BASE_URL:-https://stage.mynutriapp.cloud}"
USE_MOCK_DATA="${USE_MOCK_DATA:-false}"

# DerivedData dedicata (come da piano): mai la DerivedData globale di Xcode
DERIVED_DATA="$APP_DIR/build/ios/DerivedData"
LOG_DIR="$APP_DIR/build"
BUILD_LOG="$LOG_DIR/w-xcode-build.log"
LAUNCH_LOG="$LOG_DIR/w-launch.log"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-clean) DO_CLEAN=0; shift ;;
    --no-pull) DO_PULL=0; shift ;;
    rebuild|--rebuild|-r) DO_CLEAN=1; shift ;;
    --device|-d)
      DEVICE="${2:-}"
      [[ -n "$DEVICE" ]] || { echo "Errore: --device richiede un nome/id" >&2; exit 1; }
      shift 2
      ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

log() { echo "→ $*"; }
die() { echo "Errore: $*" >&2; exit 1; }

# Rimuove resource fork / xattr che fanno fallire codesign
# ("resource fork, Finder information, or similar detritus not allowed").
strip_xattrs() {
  local p
  for p in "$@"; do
    [[ -e "$p" ]] || continue
    xattr -cr "$p" 2>/dev/null || true
  done
}

export PATH="${FLUTTER_ROOT:+$FLUTTER_ROOT/bin:}$HOME/development/flutter/bin:$PATH"
command -v flutter >/dev/null 2>&1 || die "flutter non trovato nel PATH"
[[ "$(uname -s)" == "Darwin" ]] || die "Questo script richiede macOS + Xcode (simulatore iOS)"
command -v xcrun >/dev/null 2>&1 || die "xcrun/Xcode non trovato"
command -v pod >/dev/null 2>&1 || die "CocoaPods (pod) non trovato — installa con: sudo gem install cocoapods"
command -v xcodebuild >/dev/null 2>&1 || die "xcodebuild non trovato"

# Desktop/iCloud aggiunge spesso xattr → codesign su Flutter.framework fallisce
case "$APP_DIR" in
  */Desktop/*|*/Desktop|*/Library/Mobile\ Documents/*|*/iCloudDrive/*)
    log "Avviso: progetto sotto Desktop/iCloud ($APP_DIR). Se il build fallisce ancora, spostalo fuori da iCloud (es. ~/dev/)."
    ;;
esac

mkdir -p "$LOG_DIR"

# ── 1) Codice ───────────────────────────────────────────────────────
if [[ "$DO_PULL" -eq 1 ]]; then
  log "Git pull"
  (cd "$REPO_ROOT" && git pull --ff-only) || log "Git pull saltato/fallito (continuo)"
fi
cd "$APP_DIR"

# ── 2) Clean ────────────────────────────────────────────────────────
if [[ "$DO_CLEAN" -eq 1 ]]; then
  log "Clean Flutter + DerivedData di progetto + Pods"
  flutter clean
  rm -rf "$DERIVED_DATA" \
         "$APP_DIR/build/ios" \
         "$APP_DIR/ios/Pods" \
         "$APP_DIR/ios/.symlinks" \
         "$APP_DIR/ios/Flutter/ephemeral/Packages" \
         "$APP_DIR/ios/Runner.xcworkspace/xcshareddata/swiftpm" \
         "$APP_DIR/ios/Runner.xcodeproj/project.xcworkspace/xcshareddata/swiftpm"
  rm -f "$APP_DIR/ios/Flutter/Flutter.podspec" \
        "$APP_DIR/ios/Flutter/Generated.xcconfig" \
        "$APP_DIR/ios/Flutter/flutter_export_environment.sh"
fi

# ── 3) Dipendenze Flutter + CocoaPods ───────────────────────────────
log "Flutter pub get"
flutter pub get
flutter precache --ios >/dev/null 2>&1 || true

if ! grep -q 'enable-swift-package-manager: false' "$APP_DIR/pubspec.yaml"; then
  die "pubspec.yaml deve avere flutter.config.enable-swift-package-manager: false"
fi
[[ -f "$APP_DIR/ios/Podfile" ]] || die "ios/Podfile mancante"

log "pod install (CocoaPods — unico gestore dipendenze iOS)"
(
  cd "$APP_DIR/ios"
  pod install
)

[[ -d "$APP_DIR/ios/Pods" ]] || die "Pods/ non generato — pod install fallito"
[[ -f "$APP_DIR/ios/Pods/Target Support Files/Pods-Runner/Pods-Runner.debug.xcconfig" ]] \
  || die "Pods-Runner.debug.xcconfig mancante"

# Verifica che CocoaPods abbia aggiunto la fase di embed
if ! grep -q 'Embed Pods Frameworks' "$APP_DIR/ios/Runner.xcodeproj/project.pbxproj" \
   && ! grep -rq 'Embed Pods Frameworks' "$APP_DIR/ios/Pods" 2>/dev/null; then
  log "Avviso: stringa Embed Pods Frameworks non trovata (verifico comunque Frameworks/ dopo build)"
fi

# ── 4) Simulatore ───────────────────────────────────────────────────
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
  xcrun simctl list devices booted 2>/dev/null | grep -q "$1"
}

wait_until_booted() {
  local id="$1" i
  for i in $(seq 1 60); do
    if is_booted "$id"; then
      sleep 2
      return 0
    fi
    sleep 1
  done
  return 1
}

ensure_simulator() {
  local id="$1" other
  log "Preparo simulator $id"
  open -a Simulator >/dev/null 2>&1 || true

  if ! is_booted "$id"; then
    while IFS= read -r other; do
      [[ -z "$other" || "$other" == "$id" ]] && continue
      log "Shutdown altro sim $other"
      xcrun simctl shutdown "$other" 2>/dev/null || true
    done < <(xcrun simctl list devices booted 2>/dev/null | grep -Eo "$uuid_re" || true)

    log "Boot $id"
    xcrun simctl boot "$id" 2>/dev/null || true
  else
    log "Simulator già Booted"
  fi

  wait_until_booted "$id" || die "simulatore non boota ($id)"

  log "Rimuovo eventuale app precedente dal sim"
  xcrun simctl terminate "$id" "$BUNDLE_ID" 2>/dev/null || true
  xcrun simctl uninstall "$id" "$BUNDLE_ID" 2>/dev/null || true
}

TARGET="${DEVICE:-}"
if [[ -z "$TARGET" ]]; then
  TARGET="$(pick_available_iphone)"
  [[ -n "$TARGET" ]] || die "nessun iPhone simulator disponibile"
fi

if [[ "$TARGET" =~ ^[A-Fa-f0-9-]{36}$ ]]; then
  ensure_simulator "$TARGET"
  DEST="platform=iOS Simulator,id=$TARGET"
  SIM_UDID="$TARGET"
else
  DEST="platform=iOS Simulator,name=$TARGET"
  SIM_UDID=""
fi

# ── 5) Build (DerivedData dedicata) ─────────────────────────────────
log "Preparo config Flutter (dart-define staging)"
flutter build ios --simulator --debug --config-only --no-pub \
  --dart-define="API_BASE_URL=$API_BASE_URL" \
  --dart-define="USE_MOCK_DATA=$USE_MOCK_DATA" \
  ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}

rm -rf "$DERIVED_DATA"
mkdir -p "$DERIVED_DATA"

# Pulisci xattr su engine Flutter + output: evita
# "Failed to codesign Flutter.framework ... resource fork ... not allowed"
FLUTTER_BIN="$(command -v flutter)"
FLUTTER_SDK="$(cd "$(dirname "$FLUTTER_BIN")/.." && pwd)"
log "Rimuovo xattr (codesign-safe)"
strip_xattrs \
  "$FLUTTER_SDK/bin/cache/artifacts/engine" \
  "$APP_DIR/ios" \
  "$APP_DIR/build" \
  "$DERIVED_DATA"

log "xcodebuild → DerivedData=$DERIVED_DATA"
set +e
(
  cd "$APP_DIR/ios"
  # NON disabilitare il code signing: Flutter unpack firma Flutter.framework
  # con identity "-" e CODE_SIGNING_ALLOWED=NO lo fa fallire.
  xcodebuild \
    -workspace Runner.xcworkspace \
    -scheme Runner \
    -configuration Debug \
    -sdk iphonesimulator \
    -destination "$DEST" \
    -derivedDataPath "$DERIVED_DATA" \
    ONLY_ACTIVE_ARCH=YES \
    CODE_SIGN_IDENTITY=- \
    CODE_SIGNING_REQUIRED=YES \
    build
) 2>&1 | tee "$BUILD_LOG"
BUILD_RC=${PIPESTATUS[0]}
set -e

if [[ "$BUILD_RC" -ne 0 ]]; then
  # Retry una volta dopo strip xattr aggressivo (Desktop/iCloud)
  if grep -qiE 'resource fork|Failed to codesign|Failed to copy Flutter framework' "$BUILD_LOG"; then
    log "Retry: strip xattr + rebuild (errore codesign/resource fork)"
    strip_xattrs \
      "$FLUTTER_SDK/bin/cache/artifacts/engine" \
      "$APP_DIR" \
      "$DERIVED_DATA"
    rm -rf "$DERIVED_DATA"
    mkdir -p "$DERIVED_DATA"
    set +e
    (
      cd "$APP_DIR/ios"
      xcodebuild \
        -workspace Runner.xcworkspace \
        -scheme Runner \
        -configuration Debug \
        -sdk iphonesimulator \
        -destination "$DEST" \
        -derivedDataPath "$DERIVED_DATA" \
        ONLY_ACTIVE_ARCH=YES \
        CODE_SIGN_IDENTITY=- \
        CODE_SIGNING_REQUIRED=YES \
        build
    ) 2>&1 | tee "$BUILD_LOG"
    BUILD_RC=${PIPESTATUS[0]}
    set -e
  fi
fi

if [[ "$BUILD_RC" -ne 0 ]]; then
  echo
  echo "======== Errori xcodebuild (anche in $BUILD_LOG) ========"
  grep -E 'error:|fatal error|BUILD FAILED|resource fork|Failed to codesign|Failed to copy Flutter|The following build commands failed' "$BUILD_LOG" \
    | tail -n 40 \
    || tail -n 40 "$BUILD_LOG"
  echo "========================================================"
  if grep -qiE 'resource fork|Failed to codesign' "$BUILD_LOG"; then
    echo "Suggerimento: il progetto è su Desktop/iCloud. Spostalo in ~/dev/mynutriapp e riprova." >&2
  fi
  die "xcodebuild fallito (exit $BUILD_RC)"
fi

# ── 6) Individua SOLO la build appena prodotta ──────────────────────
APP="$DERIVED_DATA/Build/Products/Debug-iphonesimulator/Runner.app"
if [[ ! -d "$APP" ]]; then
  APP="$(find "$DERIVED_DATA" -path '*/Debug-iphonesimulator/Runner.app' -type d 2>/dev/null | head -n 1 || true)"
fi
[[ -n "${APP:-}" && -d "$APP" ]] || die "Runner.app non trovata sotto $DERIVED_DATA"
[[ -f "$APP/Info.plist" ]] || die "Runner.app incompleta: $APP"
case "$APP" in
  "$DERIVED_DATA"*) ;;
  *) die "Rifiuto install: $APP non è sotto la DerivedData dedicata" ;;
esac

log "Build pronta: $APP"

# Verifica post-build obbligatoria (piano): DK deve essere embeddato
DK_FW="$APP/Frameworks/DKImagePickerController.framework"
if [[ ! -d "$DK_FW" ]]; then
  echo "---- Contenuto Frameworks/ ----"
  ls -la "$APP/Frameworks" 2>/dev/null || echo "(nessuna cartella Frameworks)"
  echo "---- otool -L Runner (DK*) ----"
  otool -L "$APP/Runner" 2>/dev/null | grep -i DK || true
  die "Manca $DK_FW — [CP] Embed Pods Frameworks non ha incorporato DKImagePickerController"
fi
log "OK: trovato $DK_FW"

# ── 7) Install + launch (solo questa build) ─────────────────────────
if [[ -z "${SIM_UDID:-}" ]]; then
  SIM_UDID="$(xcrun simctl list devices booted | grep -Eo "$uuid_re" | head -n 1 || true)"
  [[ -n "$SIM_UDID" ]] || die "nessun simulatore booted per install"
fi

log "Install esclusivo della build appena compilata"
xcrun simctl uninstall "$SIM_UDID" "$BUNDLE_ID" 2>/dev/null || true
xcrun simctl install "$SIM_UDID" "$APP"

log "Launch $BUNDLE_ID"
: >"$LAUNCH_LOG"
set +e
LAUNCH_OUT="$(xcrun simctl launch "$SIM_UDID" "$BUNDLE_ID" 2>&1)"
LAUNCH_RC=$?
printf '%s\n' "$LAUNCH_OUT" | tee "$LAUNCH_LOG"
set -e

if [[ "$LAUNCH_RC" -ne 0 ]]; then
  die "simctl launch fallito: $LAUNCH_OUT"
fi

sleep 3
APP_PID="$(printf '%s\n' "$LAUNCH_OUT" | awk '{print $NF}' | tr -cd '0-9')"
STILL_ALIVE=0
if [[ -n "$APP_PID" ]] && xcrun simctl spawn "$SIM_UDID" launchctl print "pid/$APP_PID" >/dev/null 2>&1; then
  STILL_ALIVE=1
fi
if [[ "$STILL_ALIVE" -eq 0 ]]; then
  if xcrun simctl spawn "$SIM_UDID" ps -A 2>/dev/null | grep -E 'Runner\.app/Runner' | grep -vq grep; then
    STILL_ALIVE=1
  fi
fi

if [[ "$STILL_ALIVE" -eq 0 ]]; then
  echo "---- Diagnostica crash (log sim, ultimi 15s) ----" | tee -a "$LAUNCH_LOG"
  xcrun simctl spawn "$SIM_UDID" log show --style compact --last 15s \
    --predicate 'eventMessage CONTAINS "DKImagePicker" OR eventMessage CONTAINS "Library not loaded" OR eventMessage CONTAINS "Terminated"' \
    2>/dev/null | tee -a "$LAUNCH_LOG" || true
  die "App non in esecuzione dopo il launch (probabile crash dyld). Vedi $LAUNCH_LOG"
fi

log "OK — app in esecuzione (pid=${APP_PID:-?})"
log "Installata da: $APP"
log "DerivedData: $DERIVED_DATA"
log "Log build: $BUILD_LOG"
