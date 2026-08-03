#!/usr/bin/env bash
# MyNutriApp → pull + simulatore + build + run iOS.
#
# Uso, dalla root del repository oppure da mobile_app/:
#
#   ./w.sh
#       Pull + dipendenze + avvio app
#
#   ./w.sh rebuild
#   ./w.sh --rebuild
#   ./w.sh -r
#       Pulizia completa + avvio app
#
#   ./w.sh --device ID
#   ./w.sh -d ID
#       Forza un simulatore/device specifico
#
# Gli altri argomenti vengono passati direttamente a `flutter run`.
#
set -Eeuo pipefail

# ─────────────────────────────────────────────────────────────────────
# Percorsi
# ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/pubspec.yaml" ]]; then
  # Script eseguito da mobile_app/w.sh
  APP_DIR="$SCRIPT_DIR"
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [[ -f "$SCRIPT_DIR/mobile_app/pubspec.yaml" ]]; then
  # Script eseguito dalla root del repository
  APP_DIR="$SCRIPT_DIR/mobile_app"
  REPO_ROOT="$SCRIPT_DIR"
else
  echo "Errore: non trovo pubspec.yaml né mobile_app/pubspec.yaml" >&2
  exit 1
fi

# I log restano fuori da build/, così flutter clean non li elimina.
LOG_DIR="$APP_DIR/.w_logs"
mkdir -p "$LOG_DIR"

RUN_LOG="$LOG_DIR/flutter-run.log"
VERBOSE_LOG="$LOG_DIR/flutter-run-verbose.log"
BUILD_LOG="$LOG_DIR/flutter-build-ios-verbose.log"

BUNDLE_ID="com.mynutriapp.mynutriApp"

REBUILD=0
DEVICE=""
EXTRA_ARGS=()

# ─────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────

log() {
  echo
  echo "→ $*"
}

warn() {
  echo "Avviso: $*" >&2
}

die() {
  echo
  echo "Errore: $*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

is_uuid() {
  [[ "$1" =~ ^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$ ]]
}

# ─────────────────────────────────────────────────────────────────────
# Argomenti
# ─────────────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    rebuild|--rebuild|-r)
      REBUILD=1
      shift
      ;;

    --device|-d)
      [[ $# -ge 2 ]] || die "$1 richiede un nome o un ID"
      DEVICE="$2"
      shift 2
      ;;

    --device=*)
      DEVICE="${1#*=}"
      [[ -n "$DEVICE" ]] || die "--device richiede un nome o un ID"
      shift
      ;;

    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

# ─────────────────────────────────────────────────────────────────────
# Controlli ambiente
# ─────────────────────────────────────────────────────────────────────

[[ "$(uname -s)" == "Darwin" ]] ||
  die "il simulatore iOS richiede macOS"

command_exists flutter ||
  die "flutter non trovato nel PATH"

command_exists git ||
  die "git non trovato nel PATH"

command_exists xcrun ||
  die "xcrun non trovato. Verifica l'installazione di Xcode"

command_exists xcodebuild ||
  die "xcodebuild non trovato. Verifica l'installazione di Xcode"

command_exists python3 ||
  die "python3 non trovato"

XCODE_PATH="$(xcode-select -p 2>/dev/null || true)"

if [[ "$XCODE_PATH" != "/Applications/Xcode.app/Contents/Developer" ]]; then
  warn "Xcode attivo: ${XCODE_PATH:-non rilevato}"
  warn "Percorso atteso: /Applications/Xcode.app/Contents/Developer"
  warn "Per correggerlo: sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer"
fi

# ─────────────────────────────────────────────────────────────────────
# Git
# ─────────────────────────────────────────────────────────────────────

log "Git pull"

(
  cd "$REPO_ROOT"

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
    die "$REPO_ROOT non è un repository Git"

  git pull --ff-only
)

cd "$APP_DIR"

# ─────────────────────────────────────────────────────────────────────
# Flutter
# ─────────────────────────────────────────────────────────────────────

prepare_flutter() {
  log "Flutter pub get"
  flutter pub get

  log "Verifico gli artifact iOS"
  flutter precache --ios >/dev/null 2>&1 || true

  local generated_config="ios/Flutter/Generated.xcconfig"
  local generated_environment="ios/Flutter/flutter_export_environment.sh"
  local configured_flutter_root=""

  if [[ -f "$generated_config" ]]; then
    configured_flutter_root="$(
      grep '^FLUTTER_ROOT=' "$generated_config" |
        head -n 1 |
        cut -d= -f2- ||
        true
    )"

    if [[ -z "$configured_flutter_root" || ! -d "$configured_flutter_root" ]]; then
      log "Generated.xcconfig non valido: lo rigenero"

      rm -f \
        "$generated_config" \
        "$generated_environment"

      flutter pub get
    fi
  fi
}

deep_clean() {
  log "Pulizia completa Flutter e Xcode"

  flutter clean || true

  rm -rf \
    "$APP_DIR/build" \
    "$APP_DIR/ios/Flutter/ephemeral"

  rm -f \
    "$APP_DIR/ios/Flutter/Generated.xcconfig" \
    "$APP_DIR/ios/Flutter/flutter_export_environment.sh"

  rm -rf \
    "$HOME/Library/Developer/Xcode/DerivedData/Runner-"* \
    2>/dev/null || true

  # flutter clean può aver rimosso directory necessarie.
  mkdir -p "$LOG_DIR"

  prepare_flutter
}

prepare_flutter

if [[ "$REBUILD" -eq 1 ]]; then
  deep_clean
fi

# ─────────────────────────────────────────────────────────────────────
# Simulatore
# ─────────────────────────────────────────────────────────────────────

UUID_REGEX='[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}'

pick_available_iphone() {
  xcrun simctl list devices available 2>/dev/null |
    python3 -c '
import re
import sys

text = sys.stdin.read()
runtime = None
candidates = []

udid_pattern = re.compile(
    r"([A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-"
    r"[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12})"
)

for line in text.splitlines():
    runtime_match = re.search(r"--\s*(iOS.*?)\s*--", line)

    if runtime_match:
        runtime = runtime_match.group(1).strip()
        continue

    if runtime is None:
        continue

    if "iPhone" not in line:
        continue

    if "unavailable" in line.lower():
        continue

    udid_match = udid_pattern.search(line)

    if not udid_match:
        continue

    name = line.split("(")[0].strip()
    udid = udid_match.group(1)

    if name == "iPhone 17":
        device_score = 100
    elif name.startswith("iPhone 17"):
        device_score = 90
    elif name.startswith("iPhone"):
        device_score = 50
    else:
        device_score = 0

    version_numbers = tuple(
        int(number)
        for number in re.findall(r"\d+", runtime)
    )

    candidates.append(
        (device_score, version_numbers, name, udid)
    )

if candidates:
    candidates.sort(reverse=True)
    print(candidates[0][3])
' || true
}

device_exists() {
  local id="$1"

  xcrun simctl list devices available 2>/dev/null |
    grep -Fq "$id"
}

is_booted() {
  local id="$1"

  xcrun simctl list devices booted 2>/dev/null |
    grep -Fq "$id"
}

wait_until_booted() {
  local id="$1"
  local attempt

  for attempt in $(seq 1 90); do
    if is_booted "$id"; then
      # Lascia il tempo a SpringBoard di terminare l'avvio.
      sleep 3
      return 0
    fi

    sleep 1
  done

  return 1
}

shutdown_other_simulators() {
  local selected_id="$1"
  local other_id

  while IFS= read -r other_id; do
    [[ -z "$other_id" ]] && continue
    [[ "$other_id" == "$selected_id" ]] && continue

    log "Spengo altro simulatore: $other_id"
    xcrun simctl shutdown "$other_id" >/dev/null 2>&1 || true
  done < <(
    xcrun simctl list devices booted 2>/dev/null |
      grep -Eo "$UUID_REGEX" ||
      true
  )
}

ensure_simulator() {
  local id="$1"

  device_exists "$id" ||
    die "simulatore non disponibile: $id"

  log "Preparo simulatore $id"

  open -a Simulator >/dev/null 2>&1 || true

  if is_booted "$id"; then
    log "Simulatore già avviato"
  else
    shutdown_other_simulators "$id"

    log "Avvio simulatore"
    xcrun simctl boot "$id" >/dev/null 2>&1 || true
  fi

  log "Attendo che il simulatore sia pronto"

  if ! wait_until_booted "$id"; then
    warn "Il primo avvio non è riuscito. Provo un riavvio senza cancellare i dati"

    xcrun simctl shutdown "$id" >/dev/null 2>&1 || true
    sleep 2

    xcrun simctl boot "$id" >/dev/null 2>&1 || true
    open -a Simulator >/dev/null 2>&1 || true

    wait_until_booted "$id" ||
      die "il simulatore non completa l'avvio: $id"
  fi

  log "Simulatore pronto"

  # Termina l'app precedente, ma non cancella ogni volta il simulatore.
  xcrun simctl terminate "$id" "$BUNDLE_ID" >/dev/null 2>&1 || true
}

TARGET="$DEVICE"

if [[ -z "$TARGET" ]]; then
  TARGET="$(pick_available_iphone)"
  [[ -n "$TARGET" ]] ||
    die "nessun simulatore iPhone disponibile"
fi

if is_uuid "$TARGET"; then
  ensure_simulator "$TARGET"
else
  log "Device selezionato tramite nome: $TARGET"
fi

# ─────────────────────────────────────────────────────────────────────
# Run Flutter
# ─────────────────────────────────────────────────────────────────────

run_flutter() {
  local verbose="${1:-0}"
  local output_log="$RUN_LOG"
  local command_args=(
    flutter
    run
    -d "$TARGET"
    --no-pub
  )

  if [[ "$verbose" -eq 1 ]]; then
    output_log="$VERBOSE_LOG"
    command_args+=("-v")
    log "Run Flutter dettagliato su $TARGET"
  else
    log "Run Flutter su $TARGET"
  fi

  if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    command_args+=("${EXTRA_ARGS[@]}")
  fi

  mkdir -p "$LOG_DIR"
  : >"$output_log"

  set +e
  "${command_args[@]}" 2>&1 | tee "$output_log"
  local flutter_status=${PIPESTATUS[0]}
  set -e

  return "$flutter_status"
}

# ─────────────────────────────────────────────────────────────────────
# Diagnostica
# ─────────────────────────────────────────────────────────────────────

print_error_context() {
  local log_file="$1"

  echo
  echo "================================================================"
  echo "DIAGNOSTICA XCODE"
  echo "Log completo: $log_file"
  echo "================================================================"

  if [[ ! -s "$log_file" ]]; then
    echo "Il file di log è vuoto o non esiste."
    return 0
  fi

  echo
  echo "── Fasi Xcode e codice 255 ─────────────────────────────────────"

  grep -n -B 35 -A 35 -Ei \
    'PhaseScriptExecution|Command PhaseScriptExecution failed|status code 255|exit code 255|Exited with status code 255|BUILD FAILED' \
    "$log_file" |
    tail -n 300 ||
    true

  echo
  echo "── Errori rilevati ──────────────────────────────────────────────"

  grep -n -B 12 -A 20 -Ei \
    'error:|fatal error|exception|permission denied|operation not permitted|sandbox|rsync|flutter_assemble|thin binary|embed frameworks|unable to load|could not build|failed with exit code|the following build commands failed' \
    "$log_file" |
    tail -n 300 ||
    true

  echo
  echo "── Ultime 100 righe ─────────────────────────────────────────────"

  tail -n 100 "$log_file" || true

  echo
  echo "================================================================"
}

collect_xcode_build_log() {
  log "Eseguo una build iOS verbose per raccogliere l'errore completo"

  mkdir -p "$LOG_DIR"
  : >"$BUILD_LOG"

  set +e
  flutter build ios \
    --simulator \
    --debug \
    --no-pub \
    -v \
    >"$BUILD_LOG" 2>&1
  local build_status=$?
  set -e

  print_error_context "$BUILD_LOG"

  return "$build_status"
}

# ─────────────────────────────────────────────────────────────────────
# Recovery leggera
# ─────────────────────────────────────────────────────────────────────

recover_build_environment() {
  log "Recovery Xcode senza cancellare il simulatore"

  # Chiude solo i servizi di build eventualmente rimasti bloccati.
  killall XCBBuildService >/dev/null 2>&1 || true

  rm -rf \
    "$APP_DIR/build/ios" \
    "$APP_DIR/ios/Flutter/ephemeral" \
    "$HOME/Library/Developer/Xcode/DerivedData/Runner-"* \
    2>/dev/null || true

  rm -f \
    "$APP_DIR/ios/Flutter/Generated.xcconfig" \
    "$APP_DIR/ios/Flutter/flutter_export_environment.sh"

  mkdir -p "$LOG_DIR"

  log "Rigenero la configurazione Flutter"
  flutter pub get

  flutter precache --ios >/dev/null 2>&1 || true

  if is_uuid "$TARGET"; then
    log "Riavvio il simulatore"

    xcrun simctl shutdown "$TARGET" >/dev/null 2>&1 || true
    sleep 2

    xcrun simctl boot "$TARGET" >/dev/null 2>&1 || true
    open -a Simulator >/dev/null 2>&1 || true

    wait_until_booted "$TARGET" ||
      die "simulatore non pronto dopo la recovery"
  fi
}

# ─────────────────────────────────────────────────────────────────────
# Esecuzione
# ─────────────────────────────────────────────────────────────────────

if run_flutter 0; then
  exit 0
fi

warn "Il primo avvio è fallito"
recover_build_environment

if run_flutter 1; then
  exit 0
fi

warn "Anche il secondo avvio è fallito"
print_error_context "$VERBOSE_LOG"

# La build separata può evidenziare meglio l'errore Xcode.
collect_xcode_build_log || true

echo
echo "Log disponibili:"
echo "  $RUN_LOG"
echo "  $VERBOSE_LOG"
echo "  $BUILD_LOG"
echo
echo "Per aprire il progetto direttamente in Xcode:"
echo "  open \"$APP_DIR/ios/Runner.xcworkspace\""
echo

die "build/run iOS fallito"