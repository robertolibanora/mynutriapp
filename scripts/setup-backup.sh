#!/bin/bash

# ========================================
# ⏰ CONFIGURAZIONE BACKUP AUTOMATICO
# MyNutriAPP - Setup backup giornaliero
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[SETUP]${NC} $1"
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

print_status "Configurazione backup automatico MyNutriAPP..."

# Directory per i backup
BACKUP_DIR="/var/backups/mynutriapp"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Crea directory backup
print_status "Creazione directory backup..."
sudo mkdir -p "$BACKUP_DIR"
sudo chown -R $USER:$USER "$BACKUP_DIR"
print_success "Directory backup creata: $BACKUP_DIR"

# Copia script backup
print_status "Configurazione script backup..."
SCRIPT_DIR="$(dirname "$0")"
sudo cp "$SCRIPT_DIR/backup.sh" /usr/local/bin/mynutriapp-backup
sudo chmod +x /usr/local/bin/mynutriapp-backup
print_success "Script backup installato"

# ========================================
# ⏰ CONFIGURAZIONE CRON
# ========================================

print_status "Configurazione backup automatico..."

# Crea job cron per backup giornaliero alle 2:00
CRON_JOB="0 2 * * * cd $PROJECT_ROOT && /usr/local/bin/mynutriapp-backup >> /var/log/mynutriapp-backup.log 2>&1"

# Aggiungi al crontab
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

print_success "Backup automatico configurato!"
print_status "Il backup verrà eseguito ogni giorno alle 2:00"

# ========================================
# 🧪 TEST BACKUP
# ========================================

echo ""
print_status "Esecuzione test backup..."
if /usr/local/bin/mynutriapp-backup; then
    print_success "Test backup completato con successo!"
else
    print_warning "Test backup fallito, controlla i log"
fi

# ========================================
# 📊 INFORMAZIONI BACKUP
# ========================================

echo ""
print_success "Configurazione backup completata!"
echo ""
echo "📊 Informazioni backup:"
echo "   - Directory: $BACKUP_DIR"
echo "   - Script: /usr/local/bin/mynutriapp-backup"
echo "   - Orario: Ogni giorno alle 2:00"
echo "   - Log: /var/log/mynutriapp-backup.log"
echo "   - Backup mantenuti: 7 giorni"
echo ""
echo "🔧 Comandi utili:"
echo "   - Backup manuale: /usr/local/bin/mynutriapp-backup"
echo "   - Vedi log: tail -f /var/log/mynutriapp-backup.log"
echo "   - Lista backup: ls -la $BACKUP_DIR"
echo "   - Rimuovi cron: crontab -e"
echo ""

print_success "Backup automatico MyNutriAPP configurato! 🎉"
