#!/bin/bash

# ========================================
# 🔐 SCRIPT RINNOVO CERTIFICATI SSL
# Rinnova certificati Let's Encrypt usando Certbot containerizzato
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[SSL]${NC} $1"
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

# Vai alla root del progetto
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Carica variabili d'ambiente se .env esiste
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# ========================================
# 🔄 RINNOVO CERTIFICATI
# ========================================

renew_certificates() {
    print_status "Rinnovo certificati SSL..."
    
    # Verifica che Certbot container sia in esecuzione
    if ! docker-compose ps certbot | grep -q "Up"; then
        print_warning "Container Certbot non è in esecuzione. Avvio..."
        docker-compose up -d certbot
        sleep 5
    fi
    
    # Esegui rinnovo
    print_status "Esecuzione rinnovo certificati..."
    if docker-compose run --rm certbot renew --webroot --webroot-path=/var/www/certbot; then
        print_success "Rinnovo completato!"
        
        # Riavvia Nginx solo se i certificati sono stati rinnovati
        if docker-compose exec certbot certbot certificates | grep -q "Certificate Name"; then
            print_status "Riavvio Nginx per applicare nuovi certificati..."
            docker-compose restart nginx
            print_success "Nginx riavviato con successo!"
        else
            print_warning "Nessun certificato trovato. Nessun rinnovo necessario."
        fi
    else
        print_error "Errore durante il rinnovo dei certificati!"
        exit 1
    fi
}

# ========================================
# 📋 OTTIENI NUOVO CERTIFICATO
# ========================================

obtain_certificate() {
    if [ -z "$1" ] || [ -z "$2" ]; then
        print_error "Uso: $0 obtain <dominio> <email>"
        print_status "Esempio: $0 obtain example.com admin@example.com"
        exit 1
    fi
    
    DOMAIN="$1"
    EMAIL="$2"
    
    print_status "Ottenimento certificato SSL per $DOMAIN..."
    
    # Verifica che Nginx sia in esecuzione (necessario per webroot)
    if ! docker-compose ps nginx | grep -q "Up"; then
        print_warning "Nginx non è in esecuzione. Avvio..."
        docker-compose up -d nginx
        sleep 5
    fi
    
    # Ottieni certificato
    print_status "Richiesta certificato a Let's Encrypt..."
    if docker-compose run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN" \
        -d "www.$DOMAIN"; then
        print_success "Certificato ottenuto con successo!"
        print_status "Aggiorna nginx.conf per usare HTTPS e riavvia Nginx"
        print_status "Vedi nginx-ssl.conf.example per configurazione completa"
    else
        print_error "Errore durante l'ottenimento del certificato!"
        print_warning "Verifica che:"
        print_warning "  - Il dominio punti al tuo VPS (DNS A record)"
        print_warning "  - La porta 80 sia aperta sul firewall"
        print_warning "  - Nginx serva correttamente /.well-known/acme-challenge/"
        exit 1
    fi
}

# ========================================
# 📊 STATO CERTIFICATI
# ========================================

show_certificates() {
    print_status "Stato certificati SSL..."
    
    if docker-compose ps certbot | grep -q "Up"; then
        docker-compose exec certbot certbot certificates
    else
        print_warning "Container Certbot non è in esecuzione."
        print_status "Avvio container..."
        docker-compose up -d certbot
        sleep 3
        docker-compose exec certbot certbot certificates
    fi
}

# ========================================
# 🧪 TEST CONFIGURAZIONE
# ========================================

test_ssl() {
    if [ -z "$1" ]; then
        print_error "Uso: $0 test <dominio>"
        exit 1
    fi
    
    DOMAIN="$1"
    
    print_status "Test configurazione SSL per $DOMAIN..."
    
    # Verifica certificato
    if command -v openssl >/dev/null 2>&1; then
        echo ""
        echo "=== Informazioni Certificato ==="
        echo | openssl s_client -connect "$DOMAIN:443" -servername "$DOMAIN" 2>/dev/null | openssl x509 -noout -dates -subject -issuer
        echo ""
        echo "=== Test Connessione ==="
        curl -I "https://$DOMAIN" 2>&1 | head -5
    else
        print_warning "openssl non installato. Test limitato."
        curl -I "https://$DOMAIN" 2>&1 | head -5
    fi
}

# ========================================
# 🚀 ESECUZIONE PRINCIPALE
# ========================================

case "${1:-renew}" in
    "renew")
        renew_certificates
        ;;
    "obtain")
        obtain_certificate "$2" "$3"
        ;;
    "status")
        show_certificates
        ;;
    "test")
        test_ssl "$2"
        ;;
    *)
        echo "🔐 Gestione Certificati SSL - MyNutriApp"
        echo "========================================"
        echo ""
        echo "Uso: $0 [comando] [argomenti]"
        echo ""
        echo "Comandi disponibili:"
        echo "  renew              - Rinnova certificati esistenti (default)"
        echo "  obtain <dom> <email> - Ottieni nuovo certificato"
        echo "  status             - Mostra stato certificati"
        echo "  test <dominio>     - Test configurazione SSL"
        echo ""
        echo "Esempi:"
        echo "  $0 renew"
        echo "  $0 obtain example.com admin@example.com"
        echo "  $0 status"
        echo "  $0 test example.com"
        exit 1
        ;;
esac

print_success "Operazione completata! 🎉"
