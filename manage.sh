#!/bin/bash

# ========================================
# 🎛️ GESTIONE COMPLETA MYNUTRIAPP
# Script principale per gestire tutto il sistema
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[MANAGE]${NC} $1"
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

print_info() {
    echo -e "${PURPLE}[INFO]${NC} $1"
}

# ========================================
# 📋 MENU PRINCIPALE
# ========================================

show_menu() {
    clear
    echo ""
    echo "🎛️  GESTIONE COMPLETA MYNUTRIAPP"
    echo "=================================="
    echo ""
    echo "🐳 DOCKER & CONTAINER"
    echo "1.  Avvia tutti i servizi"
    echo "2.  Ferma tutti i servizi"
    echo "3.  Riavvia tutti i servizi"
    echo "4.  Stato container"
    echo "5.  Logs in tempo reale"
    echo ""
    echo "🗄️  DATABASE & BACKUP"
    echo "6.  Gestione backup"
    echo "7.  Backup manuale"
    echo "8.  Ripristina backup"
    echo "9.  Accesso database"
    echo ""
    echo "📊 MONITORING & SICUREZZA"
    echo "10. Dashboard monitoring"
    echo "11. Controllo sicurezza"
    echo "12. Test notifiche"
    echo "13. Statistiche sistema"
    echo ""
    echo "🔄 AGGIORNAMENTI"
    echo "14. Aggiorna applicazione"
    echo "15. Aggiorna sistema"
    echo "16. Pulizia sistema"
    echo ""
    echo "🌐 NGINX & SSL"
    echo "17. Riavvia Nginx"
    echo "18. Test configurazione Nginx"
    echo "19. Rinnova certificato SSL"
    echo ""
    echo "📋 UTILITÀ"
    echo "20. Vedi tutti i log"
    echo "21. Spazio disco"
    echo "22. Processi attivi"
    echo "23. Configura notifiche"
    echo "24. Esci"
    echo ""
    read -p "Scegli un'opzione (1-24): " choice
}

# ========================================
# 🐳 FUNZIONI DOCKER
# ========================================

start_services() {
    print_status "Avvio servizi MyNutriAPP..."
    docker-compose up -d
    print_success "Servizi avviati!"
}

stop_services() {
    print_status "Fermata servizi MyNutriAPP..."
    docker-compose down
    print_success "Servizi fermati!"
}

restart_services() {
    print_status "Riavvio servizi MyNutriAPP..."
    docker-compose restart
    print_success "Servizi riavviati!"
}

show_container_status() {
    print_status "Stato container:"
    docker-compose ps
}

show_logs() {
    print_status "Logs in tempo reale (Ctrl+C per uscire):"
    docker-compose logs -f
}

# ========================================
# 🗄️ FUNZIONI DATABASE
# ========================================

manage_backup() {
    ./manage-backup.sh
}

manual_backup() {
    print_status "Backup manuale database..."
    /usr/local/bin/mynutriapp-backup
}

restore_backup() {
    print_status "Ripristino backup..."
    ./manage-backup.sh
}

access_database() {
    print_status "Accesso database MySQL..."
    docker-compose exec db mysql -u root -p
}

# ========================================
# 📊 FUNZIONI MONITORING
# ========================================

show_dashboard() {
    print_status "Apertura dashboard monitoring..."
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open dashboard.html
    elif command -v open >/dev/null 2>&1; then
        open dashboard.html
    else
        print_info "Apri dashboard.html nel browser"
    fi
}

check_security() {
    print_status "Controllo sicurezza..."
    ./security.sh
}

test_notifications() {
    print_status "Test notifiche..."
    ./notifications.sh test
}

show_system_stats() {
    print_status "Statistiche sistema..."
    ./monitoring.sh
}

# ========================================
# 🔄 FUNZIONI AGGIORNAMENTI
# ========================================

update_app() {
    print_status "Aggiornamento applicazione..."
    ./update.sh app
}

update_system() {
    print_status "Aggiornamento sistema..."
    ./update.sh system
}

cleanup_system() {
    print_status "Pulizia sistema..."
    ./update.sh cleanup
}

# ========================================
# 🌐 FUNZIONI NGINX
# ========================================

restart_nginx() {
    print_status "Riavvio Nginx..."
    sudo systemctl restart nginx
    print_success "Nginx riavviato!"
}

test_nginx() {
    print_status "Test configurazione Nginx..."
    sudo nginx -t
    print_success "Configurazione Nginx OK!"
}

renew_ssl() {
    print_status "Rinnovo certificato SSL..."
    sudo certbot renew
    sudo systemctl reload nginx
    print_success "Certificato SSL rinnovato!"
}

# ========================================
# 📋 FUNZIONI UTILITÀ
# ========================================

show_all_logs() {
    print_status "Tutti i log del sistema:"
    echo ""
    echo "=== DOCKER LOGS ==="
    docker-compose logs --tail=50
    echo ""
    echo "=== NGINX LOGS ==="
    sudo tail -20 /var/log/nginx/access.log
    sudo tail -20 /var/log/nginx/error.log
    echo ""
    echo "=== SYSTEM LOGS ==="
    sudo journalctl --no-pager -n 20
}

show_disk_space() {
    print_status "Spazio disco:"
    df -h
    echo ""
    print_status "Spazio Docker:"
    docker system df
}

show_processes() {
    print_status "Processi attivi:"
    ps aux | grep -E "(docker|nginx|mysql|redis)" | grep -v grep
}

configure_notifications() {
    print_status "Configurazione notifiche..."
    echo "Inserisci l'email per le notifiche:"
    read -p "Email: " email
    echo "NOTIFICATION_EMAIL_TO=$email" >> .env
    print_success "Notifiche configurate per: $email"
}

# ========================================
# 🚀 ESECUZIONE PRINCIPALE
# ========================================

while true; do
    show_menu
    
    case $choice in
        1) start_services ;;
        2) stop_services ;;
        3) restart_services ;;
        4) show_container_status ;;
        5) show_logs ;;
        6) manage_backup ;;
        7) manual_backup ;;
        8) restore_backup ;;
        9) access_database ;;
        10) show_dashboard ;;
        11) check_security ;;
        12) test_notifications ;;
        13) show_system_stats ;;
        14) update_app ;;
        15) update_system ;;
        16) cleanup_system ;;
        17) restart_nginx ;;
        18) test_nginx ;;
        19) renew_ssl ;;
        20) show_all_logs ;;
        21) show_disk_space ;;
        22) show_processes ;;
        23) configure_notifications ;;
        24) 
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
