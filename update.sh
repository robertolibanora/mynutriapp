#!/bin/bash

# ========================================
# 🔄 SISTEMA AUTO-UPDATE MYNUTRIAPP
# Aggiornamento automatico dell'applicazione
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[UPDATE]${NC} $1"
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
# 🔄 AGGIORNAMENTO APPLICAZIONE
# ========================================

update_app() {
    print_status "Aggiornamento MyNutriAPP..."
    
    # Backup database prima dell'aggiornamento
    print_status "Backup database prima dell'aggiornamento..."
    /usr/local/bin/mynutriapp-backup
    
    # Ferma i container
    print_status "Fermata container..."
    docker-compose down
    
    # Pull ultime modifiche
    print_status "Download ultime modifiche..."
    git pull origin main
    
    # Rebuild container
    print_status "Rebuild container..."
    docker-compose build --no-cache
    
    # Avvia container
    print_status "Avvio container..."
    docker-compose up -d
    
    # Attendi che i servizi siano pronti
    print_status "Attesa servizi..."
    sleep 15
    
    # Testa l'applicazione
    print_status "Test applicazione..."
    if curl -f http://localhost:8000 >/dev/null 2>&1; then
        print_success "Applicazione aggiornata e funzionante!"
    else
        print_error "Errore dopo l'aggiornamento!"
        print_status "Ripristino backup..."
        docker-compose down
        git reset --hard HEAD~1
        docker-compose up -d
        print_warning "Ripristinata versione precedente"
    fi
}

# ========================================
# 🔄 AGGIORNAMENTO SISTEMA
# ========================================

update_system() {
    print_status "Aggiornamento sistema operativo..."
    
    # Aggiorna pacchetti
    sudo apt update
    sudo apt upgrade -y
    
    # Pulisci cache
    sudo apt autoremove -y
    sudo apt autoclean
    
    print_success "Sistema aggiornato"
}

# ========================================
# 🔄 AGGIORNAMENTO DOCKER
# ========================================

update_docker() {
    print_status "Aggiornamento Docker..."
    
    # Aggiorna Docker
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    
    # Aggiorna Docker Compose
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    print_success "Docker aggiornato"
}

# ========================================
# 🧹 PULIZIA SISTEMA
# ========================================

cleanup_system() {
    print_status "Pulizia sistema..."
    
    # Pulisci container non utilizzati
    docker system prune -f
    
    # Pulisci immagini non utilizzate
    docker image prune -f
    
    # Pulisci volumi non utilizzati
    docker volume prune -f
    
    # Pulisci log vecchi
    sudo journalctl --vacuum-time=7d
    
    print_success "Sistema pulito"
}

# ========================================
# 📊 STATISTICHE AGGIORNAMENTO
# ========================================

show_update_stats() {
    print_status "Statistiche aggiornamento..."
    
    echo ""
    echo "📊 Informazioni sistema:"
    echo "   - Versione app: $(git rev-parse --short HEAD)"
    echo "   - Data aggiornamento: $(date)"
    echo "   - Uptime: $(uptime -p)"
    echo "   - Spazio disco: $(df -h / | awk 'NR==2 {print $4}') disponibile"
    echo "   - Memoria: $(free -h | awk 'NR==2 {print $7}') disponibile"
    echo ""
}

# ========================================
# 🚀 ESECUZIONE PRINCIPALE
# ========================================

echo "🔄 SISTEMA AUTO-UPDATE MYNUTRIAPP"
echo "=================================="
echo ""

case "${1:-all}" in
    "app")
        update_app
        ;;
    "system")
        update_system
        ;;
    "docker")
        update_docker
        ;;
    "cleanup")
        cleanup_system
        ;;
    "all")
        update_app
        update_system
        cleanup_system
        ;;
    *)
        echo "Uso: $0 [app|system|docker|cleanup|all]"
        exit 1
        ;;
esac

show_update_stats
print_success "Aggiornamento completato! 🎉"
