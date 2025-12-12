#!/bin/bash

# ========================================
# 📊 SETUP MONITORING AUTOMATICO
# Configura health check e alerting
# ========================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[SETUP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

print_status "Configurazione monitoring automatico..."

# Health check ogni ora
CRON_HEALTH="0 * * * * cd $PROJECT_ROOT && bash scripts/health-check.sh >> /var/log/mynutriapp-health.log 2>&1"

# Backup già configurato alle 2:00
# Aggiungi health check
(crontab -l 2>/dev/null | grep -v "health-check.sh"; echo "$CRON_HEALTH") | crontab -

print_success "Monitoring automatico configurato!"
print_status "Health check eseguito ogni ora"
print_status "Log disponibili in: /var/log/mynutriapp-health.log"

echo ""
print_status "Per testare ora:"
echo "  bash scripts/health-check.sh"
