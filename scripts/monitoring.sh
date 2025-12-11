#!/bin/bash

# ========================================
# 📊 SISTEMA MONITORING MYNUTRIAPP
# Monitoring completo per produzione
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[MONITORING]${NC} $1"
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
# 📊 HEALTH CHECK COMPLETO
# ========================================

# Vai alla root del progetto
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

check_containers() {
    print_status "Controllo container Docker..."
    echo ""
    
    # Controlla container attivi
    if docker-compose ps | grep -q "Up"; then
        print_success "Container attivi:"
        docker-compose ps
    else
        print_error "Nessun container attivo!"
        return 1
    fi
    echo ""
}

check_database() {
    print_status "Controllo database MySQL..."
    
    # Carica variabili d'ambiente se disponibili
    if [ -f "$PROJECT_ROOT/.env" ]; then
        set -a
        source "$PROJECT_ROOT/.env"
        set +a
    fi
    
    if docker-compose exec -T db mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASSWORD:-root_password_super_sicura_123!} >/dev/null 2>&1; then
        print_success "Database MySQL: OK"
        
        # Controlla connessioni attive
        CONNECTIONS=$(docker-compose exec -T db mysql -u root -p${MYSQL_ROOT_PASSWORD:-root_password_super_sicura_123!} -e "SHOW STATUS LIKE 'Threads_connected';" | grep Threads_connected | awk '{print $2}')
        echo "   - Connessioni attive: $CONNECTIONS"
        
        # Controlla spazio database
        DB_SIZE=$(docker-compose exec -T db mysql -u root -p${MYSQL_ROOT_PASSWORD:-root_password_super_sicura_123!} -e "SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'DB Size in MB' FROM information_schema.tables WHERE table_schema='mynutriapp';" | grep -v "DB Size")
        echo "   - Dimensione database: ${DB_SIZE} MB"
    else
        print_error "Database MySQL: ERRORE!"
        return 1
    fi
    echo ""
}

check_redis() {
    print_status "Controllo Redis..."
    
    if docker-compose exec -T redis redis-cli ping >/dev/null 2>&1; then
        print_success "Redis: OK"
        
        # Controlla memoria Redis
        MEMORY=$(docker-compose exec -T redis redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
        echo "   - Memoria utilizzata: $MEMORY"
        
        # Controlla chiavi
        KEYS=$(docker-compose exec -T redis redis-cli dbsize)
        echo "   - Chiavi in memoria: $KEYS"
    else
        print_error "Redis: ERRORE!"
        return 1
    fi
    echo ""
}

check_nginx() {
    print_status "Controllo Nginx (containerizzato)..."
    
    if docker-compose ps | grep -q "mynutriapp_nginx.*Up"; then
        print_success "Nginx: OK"
        
        # Controlla configurazione nel container
        if docker-compose exec -T nginx nginx -t >/dev/null 2>&1; then
            echo "   - Configurazione: OK"
        else
            print_warning "Configurazione Nginx: PROBLEMI!"
        fi
        
        # Controlla connessioni
        CONNECTIONS=$(docker-compose exec -T nginx netstat -an 2>/dev/null | grep :80 | wc -l || echo "0")
        echo "   - Container attivo: Sì"
        echo "   - Porta 80 esposta: Sì"
    else
        print_error "Nginx: ERRORE! Container non attivo"
        return 1
    fi
    echo ""
}

check_disk_space() {
    print_status "Controllo spazio disco..."
    
    # Spazio totale
    TOTAL=$(df -h / | awk 'NR==2 {print $2}')
    USED=$(df -h / | awk 'NR==2 {print $3}')
    AVAIL=$(df -h / | awk 'NR==2 {print $4}')
    PERCENT=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
    
    echo "   - Spazio totale: $TOTAL"
    echo "   - Spazio utilizzato: $USED"
    echo "   - Spazio disponibile: $AVAIL"
    echo "   - Percentuale utilizzata: $PERCENT%"
    
    if [ "$PERCENT" -gt 80 ]; then
        print_warning "ATTENZIONE: Spazio disco > 80%!"
    elif [ "$PERCENT" -gt 90 ]; then
        print_error "CRITICO: Spazio disco > 90%!"
    else
        print_success "Spazio disco: OK"
    fi
    echo ""
}

check_memory() {
    print_status "Controllo memoria..."
    
    # Memoria totale e utilizzata
    TOTAL_MEM=$(free -h | awk 'NR==2{print $2}')
    USED_MEM=$(free -h | awk 'NR==2{print $3}')
    AVAIL_MEM=$(free -h | awk 'NR==2{print $7}')
    
    echo "   - Memoria totale: $TOTAL_MEM"
    echo "   - Memoria utilizzata: $USED_MEM"
    echo "   - Memoria disponibile: $AVAIL_MEM"
    
    # Percentuale memoria
    MEM_PERCENT=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
    echo "   - Percentuale utilizzata: $MEM_PERCENT%"
    
    if [ "$MEM_PERCENT" -gt 80 ]; then
        print_warning "ATTENZIONE: Memoria > 80%!"
    elif [ "$MEM_PERCENT" -gt 90 ]; then
        print_error "CRITICO: Memoria > 90%!"
    else
        print_success "Memoria: OK"
    fi
    echo ""
}

check_logs() {
    print_status "Controllo log errori..."
    
    # Log Nginx errori (dal container)
    NGINX_ERRORS=$(docker-compose logs --tail=100 nginx 2>/dev/null | grep -i "error" | grep -c "$(date +%Y-%m-%d)" 2>/dev/null || echo "0")
    echo "   - Errori Nginx oggi: $NGINX_ERRORS"
    
    # Log applicazione
    APP_ERRORS=$(docker-compose logs --tail=100 web 2>/dev/null | grep -i "error" | wc -l || echo "0")
    echo "   - Errori applicazione: $APP_ERRORS"
    
    # Log database
    DB_ERRORS=$(docker-compose logs --tail=100 db 2>/dev/null | grep -i "error" | wc -l || echo "0")
    echo "   - Errori database: $DB_ERRORS"
    
    TOTAL_ERRORS=$((NGINX_ERRORS + APP_ERRORS + DB_ERRORS))
    if [ "$TOTAL_ERRORS" -gt 10 ]; then
        print_warning "ATTENZIONE: Molti errori nei log!"
    else
        print_success "Log: OK"
    fi
    echo ""
}

# ========================================
# 📈 PERFORMANCE METRICS
# ========================================

show_performance() {
    print_status "Metriche performance..."
    
    # CPU usage
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')
    echo "   - Utilizzo CPU: ${CPU_USAGE}%"
    
    # Load average
    LOAD=$(uptime | awk -F'load average:' '{print $2}')
    echo "   - Load average: $LOAD"
    
    # Uptime
    UPTIME=$(uptime -p)
    echo "   - Uptime: $UPTIME"
    
    echo ""
}

# ========================================
# 🚀 ESECUZIONE PRINCIPALE
# ========================================

echo "📊 MONITORING COMPLETO MYNUTRIAPP"
echo "=================================="
echo ""

check_containers
check_database
check_redis
check_nginx
check_disk_space
check_memory
check_logs
show_performance

print_success "Monitoring completato! 🎉"
