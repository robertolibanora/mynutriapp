#!/bin/bash

# ========================================
# 🏥 HEALTH CHECK COMPLETO MYNUTRIAPP
# Script per verificare lo stato dell'applicazione
# ========================================

set -e

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[CHECK]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

ERRORS=0
WARNINGS=0

echo ""
echo "🏥 HEALTH CHECK MYNUTRIAPP"
echo "=========================="
echo ""

# 1. Verifica container Docker
print_status "Verifica container Docker..."
if docker compose ps | grep -q "Up"; then
    print_success "Container attivi"
    docker compose ps | grep -E "NAME|Up"
else
    print_error "Alcuni container non sono attivi!"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 2. Verifica web container
print_status "Verifica container web..."
if docker compose ps web | grep -q "Up"; then
    print_success "Container web attivo"
    
    # Verifica risposta HTTP
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null | grep -q "200\|404"; then
        print_success "Web container risponde"
    else
        print_warning "Web container potrebbe non rispondere correttamente"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    print_error "Container web non attivo!"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 3. Verifica database
print_status "Verifica database MySQL..."
if docker compose exec -T db mysqladmin ping -h localhost -u root -p"${MYSQL_ROOT_PASSWORD:-N0ira2026!}" 2>/dev/null | grep -q "alive"; then
    print_success "Database MySQL attivo"
    
    # Verifica connessioni
    CONNECTIONS=$(docker compose exec -T db mysql -u root -p"${MYSQL_ROOT_PASSWORD:-N0ira2026!}" -e "SHOW STATUS LIKE 'Threads_connected';" 2>/dev/null | tail -1 | awk '{print $2}')
    if [ "$CONNECTIONS" -lt 50 ]; then
        print_success "Connessioni database: $CONNECTIONS"
    else
        print_warning "Molte connessioni database: $CONNECTIONS"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    print_error "Database MySQL non risponde!"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 4. Verifica Redis
print_status "Verifica Redis..."
if docker compose exec -T redis redis-cli -a "${REDIS_PASSWORD:-I0E6TjyZ4wMBqkXNsUsQXBHCZQWf8rfpeyM-X2KQ7lA}" ping 2>/dev/null | grep -q "PONG"; then
    print_success "Redis attivo"
else
    print_error "Redis non risponde!"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 5. Verifica spazio disco
print_status "Verifica spazio disco..."
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    print_success "Spazio disco: ${DISK_USAGE}% utilizzato"
elif [ "$DISK_USAGE" -lt 90 ]; then
    print_warning "Spazio disco: ${DISK_USAGE}% utilizzato (attenzione!)"
    WARNINGS=$((WARNINGS + 1))
else
    print_error "Spazio disco: ${DISK_USAGE}% utilizzato (CRITICO!)"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 6. Verifica memoria
print_status "Verifica memoria..."
MEM_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USAGE" -lt 85 ]; then
    print_success "Memoria: ${MEM_USAGE}% utilizzata"
else
    print_warning "Memoria: ${MEM_USAGE}% utilizzata"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 7. Verifica log errori recenti
print_status "Verifica errori recenti nei log..."
RECENT_ERRORS=$(docker compose logs web --since 1h 2>&1 | grep -i "error\|exception\|traceback" | wc -l)
if [ "$RECENT_ERRORS" -eq 0 ]; then
    print_success "Nessun errore recente nei log"
else
    print_warning "Trovati $RECENT_ERRORS errori nelle ultime ore"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 8. Verifica backup recenti
print_status "Verifica backup recenti..."
BACKUP_DIR="/var/backups/mynutriapp"
if [ -d "$BACKUP_DIR" ]; then
    LAST_BACKUP=$(find "$BACKUP_DIR" -name "*.sql" -type f -mtime -1 2>/dev/null | head -1)
    if [ -n "$LAST_BACKUP" ]; then
        BACKUP_SIZE=$(du -h "$LAST_BACKUP" | cut -f1)
        print_success "Ultimo backup: $(basename "$LAST_BACKUP") ($BACKUP_SIZE)"
    else
        print_warning "Nessun backup nelle ultime 24 ore!"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    print_warning "Directory backup non trovata"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 9. Verifica certificati SSL
print_status "Verifica certificati SSL..."
if curl -s -I https://mynutriapp.cloud 2>&1 | grep -q "HTTP/2 200\|HTTP/2 302"; then
    print_success "HTTPS funzionante"
    
    # Verifica scadenza certificato (se possibile)
    CERT_EXPIRY=$(echo | openssl s_client -servername mynutriapp.cloud -connect mynutriapp.cloud:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null | grep notAfter | cut -d= -f2)
    if [ -n "$CERT_EXPIRY" ]; then
        print_success "Certificato SSL valido fino a: $CERT_EXPIRY"
    fi
else
    print_error "HTTPS non funzionante!"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 10. Verifica endpoint pubblici
print_status "Verifica endpoint pubblici..."
ENDPOINTS=("https://mynutriapp.cloud/listino" "https://mynutriapp.cloud/presentazione")
for endpoint in "${ENDPOINTS[@]}"; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$endpoint" 2>/dev/null)
    if [ "$STATUS" = "200" ]; then
        print_success "$endpoint: OK ($STATUS)"
    else
        print_warning "$endpoint: $STATUS"
        WARNINGS=$((WARNINGS + 1))
    fi
done
echo ""

# Riepilogo
echo "=========================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    print_success "Tutto OK! Nessun problema rilevato."
    exit 0
elif [ $ERRORS -eq 0 ]; then
    print_warning "Completato con $WARNINGS avvisi"
    exit 0
else
    print_error "Trovati $ERRORS errori e $WARNINGS avvisi!"
    exit 1
fi
