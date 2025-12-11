#!/bin/bash

# ========================================
# 📧 SISTEMA NOTIFICHE MYNUTRIAPP
# Notifiche email per eventi critici
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[NOTIFICATIONS]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ========================================
# 📧 CONFIGURAZIONE EMAIL
# ========================================

# Carica configurazioni da .env
if [ -f .env ]; then
    source .env
fi

# Configurazioni email
EMAIL_FROM="${NOTIFICATION_EMAIL_FROM:-admin@mynutriapp.com}"
EMAIL_TO="${NOTIFICATION_EMAIL_TO:-admin@mynutriapp.com}"
SMTP_SERVER="${NOTIFICATION_SMTP_SERVER:-localhost}"
SMTP_PORT="${NOTIFICATION_SMTP_PORT:-587}"
SMTP_USER="${NOTIFICATION_SMTP_USER:-}"
SMTP_PASS="${NOTIFICATION_SMTP_PASS:-}"

# ========================================
# 📧 INVIO EMAIL
# ========================================

send_email() {
    local subject="$1"
    local body="$2"
    local priority="${3:-normal}"
    
    # Crea file temporaneo per email
    local email_file=$(mktemp)
    
    cat > "$email_file" << EOF
To: $EMAIL_TO
From: $EMAIL_FROM
Subject: [MyNutriAPP] $subject
X-Priority: $priority

$body

---
Inviato automaticamente da MyNutriAPP
Data: $(date)
Server: $(hostname)
EOF

    # Invia email
    if command -v mail >/dev/null 2>&1; then
        mail -s "[MyNutriAPP] $subject" "$EMAIL_TO" < "$email_file"
    elif command -v sendmail >/dev/null 2>&1; then
        sendmail "$EMAIL_TO" < "$email_file"
    else
        print_warning "Nessun client email trovato, salvo in log"
        echo "$(date): $subject - $body" >> /var/log/mynutriapp-notifications.log
    fi
    
    rm "$email_file"
    print_success "Notifica inviata: $subject"
}

# ========================================
# 🚨 NOTIFICHE SISTEMA
# ========================================

notify_system_down() {
    local service="$1"
    send_email "CRITICO: Servizio $service non risponde" \
        "Il servizio $service è andato offline.\n\nTempo: $(date)\nServer: $(hostname)\n\nIntervento richiesto!" \
        "1"
}

notify_high_cpu() {
    local cpu_usage="$1"
    send_email "ATTENZIONE: CPU alta ($cpu_usage%)" \
        "L'utilizzo della CPU è al $cpu_usage%.\n\nTempo: $(date)\nServer: $(hostname)\n\nMonitorare il sistema." \
        "2"
}

notify_high_memory() {
    local mem_usage="$1"
    send_email "ATTENZIONE: Memoria alta ($mem_usage%)" \
        "L'utilizzo della memoria è al $mem_usage%.\n\nTempo: $(date)\nServer: $(hostname)\n\nConsiderare l'upgrade o l'ottimizzazione." \
        "2"
}

notify_disk_full() {
    local disk_usage="$1"
    send_email "CRITICO: Disco pieno ($disk_usage%)" \
        "Lo spazio disco è al $disk_usage%.\n\nTempo: $(date)\nServer: $(hostname)\n\nIntervento immediato richiesto!" \
        "1"
}

notify_backup_failed() {
    send_email "ERRORE: Backup fallito" \
        "Il backup automatico del database è fallito.\n\nTempo: $(date)\nServer: $(hostname)\n\nControllare i log per dettagli." \
        "1"
}

notify_backup_success() {
    local backup_size="$1"
    send_email "Backup completato con successo" \
        "Il backup automatico è stato completato.\n\nDimensione: $backup_size\nTempo: $(date)\nServer: $(hostname)" \
        "3"
}

notify_ssl_expiring() {
    local days_left="$1"
    send_email "ATTENZIONE: Certificato SSL in scadenza" \
        "Il certificato SSL scadrà tra $days_left giorni.\n\nTempo: $(date)\nServer: $(hostname)\n\nRinnovare il certificato." \
        "2"
}

# ========================================
# 🔍 MONITORING E NOTIFICHE
# ========================================

# Vai alla root del progetto
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

check_system_health() {
    print_status "Controllo salute sistema..."
    
    # Controlla container
    if ! docker-compose ps | grep -q "Up"; then
        notify_system_down "Docker Containers"
    fi
    
    # Controlla CPU
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')
    if (( $(echo "$CPU_USAGE > 80" | bc -l) )); then
        notify_high_cpu "$CPU_USAGE"
    fi
    
    # Controlla memoria
    MEM_PERCENT=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
    if [ "$MEM_PERCENT" -gt 80 ]; then
        notify_high_memory "$MEM_PERCENT"
    fi
    
    # Controlla disco
    DISK_PERCENT=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
    if [ "$DISK_PERCENT" -gt 80 ]; then
        notify_disk_full "$DISK_PERCENT"
    fi
    
    # Controlla SSL
    if command -v openssl >/dev/null 2>&1; then
        SSL_EXPIRY=$(echo | openssl s_client -servername $(hostname) -connect localhost:443 2>/dev/null | openssl x509 -noout -dates | grep notAfter | cut -d= -f2)
        if [ ! -z "$SSL_EXPIRY" ]; then
            SSL_DAYS=$(( ($(date -d "$SSL_EXPIRY" +%s) - $(date +%s)) / 86400 ))
            if [ "$SSL_DAYS" -lt 30 ]; then
                notify_ssl_expiring "$SSL_DAYS"
            fi
        fi
    fi
}

# ========================================
# 🧪 TEST NOTIFICHE
# ========================================

test_notifications() {
    print_status "Test sistema notifiche..."
    
    send_email "Test Notifiche MyNutriAPP" \
        "Questo è un messaggio di test per verificare il funzionamento del sistema di notifiche.\n\nTempo: $(date)\nServer: $(hostname)" \
        "3"
    
    print_success "Test notifiche completato"
}

# ========================================
# 🚀 ESECUZIONE PRINCIPALE
# ========================================

case "${1:-check}" in
    "test")
        test_notifications
        ;;
    "check")
        check_system_health
        ;;
    "backup-success")
        notify_backup_success "${2:-Unknown}"
        ;;
    "backup-failed")
        notify_backup_failed
        ;;
    *)
        echo "Uso: $0 [test|check|backup-success|backup-failed]"
        exit 1
        ;;
esac

print_success "Sistema notifiche completato! 📧"
