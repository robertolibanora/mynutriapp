#!/bin/bash

# ========================================
# 🗄️ SCRIPT BACKUP AUTOMATICO DATABASE
# MyNutriAPP - Backup giornaliero MySQL
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzione per stampare messaggi colorati
print_status() {
    echo -e "${BLUE}[BACKUP]${NC} $1"
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
# 📁 CONFIGURAZIONE BACKUP
# ========================================

# Directory per i backup
BACKUP_DIR="/var/backups/mynutriapp"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="mynutriapp_backup_${DATE}.sql"
FULL_BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

# Configurazione database
DB_NAME="mynutriapp"
DB_USER="root"

# Carica variabili d'ambiente se disponibili
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

DB_PASSWORD="${MYSQL_ROOT_PASSWORD:-root_password_super_sicura_123!}"

# ========================================
# 🚀 ESECUZIONE BACKUP
# ========================================

print_status "Avvio backup database MyNutriAPP..."

# Crea directory backup se non esiste
mkdir -p "$BACKUP_DIR"

# Controlla se i container sono attivi
# Usa la directory del progetto (parent di scripts/)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

if ! docker-compose ps | grep -q "mynutriapp_db.*Up"; then
    print_error "Container database non attivo!"
    print_status "Tentativo di avvio container..."
    docker-compose up -d db
    sleep 10
fi

# Esegue il backup
print_status "Esecuzione backup database..."
if docker-compose exec -T db mysqldump -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" > "$FULL_BACKUP_PATH"; then
    print_success "Backup completato: $BACKUP_FILE"
else
    print_error "Errore durante il backup!"
    exit 1
fi

# Comprimi il backup per risparmiare spazio
print_status "Compressione backup..."
if gzip "$FULL_BACKUP_PATH"; then
    print_success "Backup compresso: ${BACKUP_FILE}.gz"
    BACKUP_FILE="${BACKUP_FILE}.gz"
    FULL_BACKUP_PATH="${FULL_BACKUP_PATH}.gz"
else
    print_warning "Impossibile comprimere il backup"
fi

# ========================================
# 🧹 PULIZIA BACKUP VECCHI
# ========================================

# Mantieni solo gli ultimi 7 backup
print_status "Pulizia backup vecchi (mantieni ultimi 7 giorni)..."
cd "$BACKUP_DIR"
ls -t mynutriapp_backup_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
print_success "Backup vecchi rimossi"

# ========================================
# 📊 STATISTICHE BACKUP
# ========================================

# Calcola dimensioni
BACKUP_SIZE=$(du -h "$FULL_BACKUP_PATH" | cut -f1)
TOTAL_BACKUPS=$(ls -1 mynutriapp_backup_*.sql.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh . | cut -f1)

print_success "Backup completato con successo!"
echo ""
echo "📊 Statistiche backup:"
echo "   - File: $BACKUP_FILE"
echo "   - Dimensione: $BACKUP_SIZE"
echo "   - Backup totali: $TOTAL_BACKUPS"
echo "   - Spazio totale: $TOTAL_SIZE"
echo "   - Directory: $BACKUP_DIR"
echo ""

# ========================================
# 📧 NOTIFICA (Opzionale)
# ========================================

# Se vuoi ricevere notifiche via email, decommenta e configura:
# echo "Backup MyNutriAPP completato: $BACKUP_FILE ($BACKUP_SIZE)" | mail -s "Backup MyNutriAPP" admin@yourdomain.com

print_success "Backup MyNutriAPP completato! 🎉"
