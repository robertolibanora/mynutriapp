#!/usr/bin/env bash
# Wrapper root → mobile_app/w.sh (build iOS su simulatore).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/mobile_app/w.sh" "$@"
