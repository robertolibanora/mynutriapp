#!/bin/bash

# ========================================
# 🗄️ GESTIONE BACKUP MYNUTRIAPP
# Script per gestire i backup del database
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Directory backup
BACKUP_DIR="/var/backups/mynutriapp"

# Vai alla root del progetto
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# ========================================
# 📋 MENU PRINCIPALE
# ========================================

show_menu() {
    echo ""
    echo "🗄️  GESTIONE BACKUP MYNUTRIAPP"
    echo "================================"
    echo "1. Esegui backup manuale"
    echo "2. Lista backup disponibili"
    echo "3. Ripristina backup"
    echo "4. Pulisci backup vecchi"
    echo "5. Mostra statistiche"
    echo "6. Testa backup"
    echo "7. Configura backup automatico"
    echo "8. Disabilita backup automatico"
    echo "9. Esci"
    echo ""
    read -p "Scegli un'opzione (1-9): " choice
}

# ========================================
# 🔧 FUNZIONI BACKUP
# ========================================

backup_manual() {
    print_status "Esecuzione backup manuale..."
    if /usr/local/bin/mynutriapp-backup; then
        print_success "Backup manuale completato!"
    else
        print_error "Errore durante il backup!"
    fi
}

list_backups() {
    print_status "Backup disponibili:"
    echo ""
    if [ -d "$BACKUP_DIR" ] && [ "$(ls -A $BACKUP_DIR 2>/dev/null)" ]; then
        ls -lah "$BACKUP_DIR" | grep mynutriapp_backup
        echo ""
        echo "📊 Totale backup: $(ls -1 $BACKUP_DIR/mynutriapp_backup_*.sql.gz 2>/dev/null | wc -l)"
        echo "💾 Spazio totale: $(du -sh $BACKUP_DIR | cut -f1)"
    else
        print_warning "Nessun backup trovato"
    fi
}

restore_backup() {
    print_status "Backup disponibili per il ripristino:"
    echo ""
    if [ -d "$BACKUP_DIR" ] && [ "$(ls -A $BACKUP_DIR 2>/dev/null)" ]; then
        ls -lah "$BACKUP_DIR" | grep mynutriapp_backup | nl
        echo ""
        read -p "Inserisci il numero del backup da ripristinare: " backup_num
        
        BACKUP_FILE=$(ls -1 $BACKUP_DIR/mynutriapp_backup_*.sql.gz | sed -n "${backup_num}p")
        
        if [ -z "$BACKUP_FILE" ]; then
            print_error "Backup non trovato!"
            return
        fi
        
        print_warning "ATTENZIONE: Questa operazione sovrascriverà il database attuale!"
        read -p "Sei sicuro di voler continuare? (y/N): " confirm
        
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            print_status "Ripristino backup: $BACKUP_FILE"
            # Carica variabili d'ambiente se disponibili
            if [ -f "$PROJECT_ROOT/.env" ]; then
                set -a
                source "$PROJECT_ROOT/.env"
                set +a
            fi
            if docker-compose exec -T db mysql -u root -p${MYSQL_ROOT_PASSWORD:-root_password_super_sicura_123!} mynutriapp < "$BACKUP_FILE"; then
                print_success "Backup ripristinato con successo!"
            else
                print_error "Errore durante il ripristino!"
            fi
        else
            print_status "Ripristino annullato"
        fi
    else
        print_warning "Nessun backup disponibile"
    fi
}

clean_old_backups() {
    print_status "Pulizia backup vecchi..."
    cd "$BACKUP_DIR"
    OLD_COUNT=$(ls -1 mynutriapp_backup_*.sql.gz 2>/dev/null | wc -l)
    ls -t mynutriapp_backup_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
    NEW_COUNT=$(ls -1 mynutriapp_backup_*.sql.gz 2>/dev/null | wc -l)
    REMOVED=$((OLD_COUNT - NEW_COUNT))
    print_success "Rimossi $REMOVED backup vecchi"
}

show_stats() {
    print_status "Statistiche backup:"
    echo ""
    if [ -d "$BACKUP_DIR" ]; then
        echo "📁 Directory: $BACKUP_DIR"
        echo "📊 Backup totali: $(ls -1 $BACKUP_DIR/mynutriapp_backup_*.sql.gz 2>/dev/null | wc -l)"
        echo "💾 Spazio utilizzato: $(du -sh $BACKUP_DIR | cut -f1)"
        echo "📅 Ultimo backup: $(ls -t $BACKUP_DIR/mynutriapp_backup_*.sql.gz 2>/dev/null | head -1 | xargs -I {} basename {})"
        echo ""
        echo "⏰ Backup automatico:"
        if crontab -l 2>/dev/null | grep -q "mynutriapp-backup"; then
            echo "   ✅ Attivo (ogni giorno alle 2:00)"
        else
            echo "   ❌ Disattivo"
        fi
    else
        print_warning "Directory backup non trovata"
    fi
}

test_backup() {
    print_status "Test backup..."
    if /usr/local/bin/mynutriapp-backup; then
        print_success "Test backup completato con successo!"
    else
        print_error "Test backup fallito!"
    fi
}

setup_auto_backup() {
    print_status "Configurazione backup automatico..."
    SCRIPT_DIR="$(dirname "$0")"
    if [ -f "$SCRIPT_DIR/setup-backup.sh" ]; then
        "$SCRIPT_DIR/setup-backup.sh"
    else
        print_error "Script setup-backup.sh non trovato!"
    fi
}

disable_auto_backup() {
    print_status "Disabilitazione backup automatico..."
    crontab -l 2>/dev/null | grep -v "mynutriapp-backup" | crontab -
    print_success "Backup automatico disabilitato"
}

# ========================================
# 🚀 ESECUZIONE PRINCIPALE
# ========================================

while true; do
    show_menu
    
    case $choice in
        1)
            backup_manual
            ;;
        2)
            list_backups
            ;;
        3)
            restore_backup
            ;;
        4)
            clean_old_backups
            ;;
        5)
            show_stats
            ;;
        6)
            test_backup
            ;;
        7)
            setup_auto_backup
            ;;
        8)
            disable_auto_backup
            ;;
        9)
            print_success "Arrivederci! 👋"
            exit 0
            ;;
        *)
            print_error "Opzione non valida!"
            ;;
    esac
    
    echo ""
    read -p "Premi INVIO per continuare..."
done
