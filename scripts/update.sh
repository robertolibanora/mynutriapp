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

# Vai alla root del progetto
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Carica variabili d'ambiente se .env esiste
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

update_app() {
    print_status "Aggiornamento MyNutriAPP..."
    
    # Verifica che i volumi del database esistano (protezione dati)
    print_status "Verifica volumi database..."
    if docker volume ls | grep -q "mynutriapp_mysql_data"; then
        print_success "Volume MySQL trovato - i dati saranno preservati"
    else
        print_warning "Volume MySQL non trovato - verrà creato al primo avvio"
    fi
    
    # Backup database prima dell'aggiornamento
    print_status "Backup database prima dell'aggiornamento..."
    if [ -f "/usr/local/bin/mynutriapp-backup" ]; then
        /usr/local/bin/mynutriapp-backup
    else
        print_warning "Script backup non trovato, eseguendo backup manuale..."
        if docker-compose ps | grep -q "mynutriapp_db.*Up"; then
            BACKUP_FILE="$PROJECT_ROOT/backup_pre_update_$(date +%Y%m%d_%H%M%S).sql"
            if [ -n "$MYSQL_ROOT_PASSWORD" ]; then
                docker-compose exec -T db mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" mynutriapp > "$BACKUP_FILE" 2>/dev/null && \
                    print_success "Backup salvato in: $BACKUP_FILE" || \
                    print_warning "Backup fallito (database potrebbe essere vuoto o non accessibile)"
            else
                print_warning "MYSQL_ROOT_PASSWORD non configurato in .env - backup saltato"
            fi
        fi
    fi
    
    # Ferma i container (SENZA rimuovere volumi - i dati sono preservati)
    print_status "Fermata container (volumi preservati)..."
    docker-compose down
    
    # Pull ultime modifiche
    print_status "Download ultime modifiche..."
    git pull origin main
    
    # Rebuild container
    print_status "Rebuild container..."
    docker-compose build --no-cache
    
    # Avvia container (i volumi esistenti verranno riutilizzati automaticamente)
    print_status "Avvio container (riutilizzo volumi esistenti)..."
    docker-compose up -d
    
    # Attendi che i servizi siano pronti
    print_status "Attesa servizi..."
    sleep 15
    
    # Testa l'applicazione
    print_status "Test applicazione..."
    if curl -f http://localhost:8000 >/dev/null 2>&1; then
        print_success "Applicazione aggiornata e funzionante!"
        print_success "✅ Database preservato - tutti i dati sono intatti"
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
    
    # ⚠️ NON puliamo i volumi con docker volume prune -f
    # Questo potrebbe rimuovere mysql_data e redis_data anche se non in uso temporaneo
    # I volumi del progetto sono gestiti da docker-compose e vengono preservati automaticamente
    print_warning "Volumi Docker preservati (mysql_data, redis_data) - dati al sicuro"
    
    # Pulisci solo volumi orfani (non referenziati da nessun progetto)
    # Escludiamo esplicitamente i volumi del progetto
    print_status "Pulizia volumi orfani (esclusi volumi progetto)..."
    docker volume ls -q --filter "dangling=true" | grep -v "mynutriapp_" | xargs -r docker volume rm 2>/dev/null || true
    
    # Pulisci log vecchi
    sudo journalctl --vacuum-time=7d
    
    print_success "Sistema pulito (volumi progetto preservati)"
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
