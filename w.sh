#!/usr/bin/env bash
# Wrapper root → mobile_app/w.sh (clean → pod install → build → install → launch).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/mobile_app/w.sh" "$@"
