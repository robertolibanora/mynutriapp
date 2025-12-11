#!/bin/bash

# ========================================
# 🚀 SCRIPT DI DEPLOYMENT MYNUTRIAPP
# ========================================

set -e  # Esci se c'è un errore

echo "🚀 Avvio deployment MyNutriAPP..."

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzione per stampare messaggi colorati
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
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

# Controlla se Docker è installato
if ! command -v docker &> /dev/null; then
    print_error "Docker non è installato!"
    print_status "Installazione Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    print_success "Docker installato!"
fi

# Controlla se Docker Compose è installato
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose non è installato!"
    print_status "Installazione Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    print_success "Docker Compose installato!"
fi

# Caddy è containerizzato, gestisce SSL automaticamente
# Non serve installare nulla sul sistema host

# Controlla se il file .env esiste
if [ ! -f ".env" ]; then
    print_error "File .env non trovato!"
    print_status "Crea il file .env con le tue configurazioni prima di continuare."
    print_warning "IMPORTANTE: Configura almeno:"
    print_warning "  - SECRET_KEY (genera con: python3 -c \"import secrets; print(secrets.token_hex(32))\")"
    print_warning "  - MYSQL_ROOT_PASSWORD"
    print_warning "  - MYSQL_PASSWORD"
    print_warning "  - ADMIN_PHONE"
    print_warning "  - ADMIN_PASSWORD"
    exit 1
fi

# Carica variabili d'ambiente da .env per uso nello script
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Crea directory necessarie
print_status "Creazione directory necessarie..."
mkdir -p static/uploads
mkdir -p logs
mkdir -p logs/caddy  # Per i log di Caddy containerizzato
print_success "Directory create!"

# Ferma i container esistenti
print_status "Fermata container esistenti..."
docker-compose down 2>/dev/null || true

# Rimuovi immagini vecchie (opzionale)
if [ "$1" = "--clean" ]; then
    print_status "Rimozione immagini vecchie..."
    docker-compose down --rmi all 2>/dev/null || true
fi

# Costruisci e avvia i container
print_status "Costruzione e avvio container..."
docker-compose up -d --build

# Attendi che i servizi siano pronti
print_status "Attesa servizi..."
sleep 10

# Controlla lo stato dei container
print_status "Controllo stato container..."
docker-compose ps

# Attendi che MySQL sia completamente pronto (healthcheck passa)
print_status "Attesa MySQL completamente pronto..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if docker-compose exec -T db mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASSWORD} >/dev/null 2>&1; then
        if docker-compose exec -T db mysql -h localhost -u root -p${MYSQL_ROOT_PASSWORD} -e "USE mynutriapp; SELECT 1;" >/dev/null 2>&1; then
            print_success "MySQL pronto e database accessibile!"
            break
        fi
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo -n "."
done
echo ""

if [ $WAITED -ge $MAX_WAIT ]; then
    print_warning "MySQL potrebbe non essere ancora pronto, ma continuo..."
fi

# Testa Redis
print_status "Test connessione Redis..."
if docker-compose exec -T redis redis-cli ping >/dev/null 2>&1; then
    print_success "Redis pronto!"
else
    print_warning "Redis non ancora pronto (continuerà in background)"
fi

# ========================================
# 🌐 CADDY (Containerizzato con SSL Automatico)
# ========================================
print_status "Caddy sarà gestito come container Docker..."
print_status "Caddy gestisce SSL automaticamente con Let's Encrypt!"

echo ""
print_status "Configurazione dominio per SSL automatico..."
echo "Vuoi configurare un dominio per HTTPS automatico? (y/n)"
read -p "Risposta: " ssl_choice

if [ "$ssl_choice" = "y" ] || [ "$ssl_choice" = "Y" ]; then
    echo "Inserisci il tuo dominio (es: example.com):"
    read -p "Dominio: " domain_name
    
    if [ ! -z "$domain_name" ]; then
        print_status "Configurazione Caddy per $domain_name..."
        
        # Aggiorna Caddyfile con il dominio
        if [ -f "Caddyfile" ]; then
            # Sostituisci :80 con il dominio nel Caddyfile
            sed -i "s/:80/$domain_name/g" Caddyfile
            # Aggiungi www se non presente
            if ! grep -q "www.$domain_name" Caddyfile; then
                sed -i "s/$domain_name {/$domain_name www.$domain_name {/g" Caddyfile
            fi
            print_success "Caddyfile aggiornato con dominio $domain_name"
            print_warning "Assicurati che il DNS punti al tuo VPS!"
        else
            print_error "Caddyfile non trovato!"
        fi
    else
        print_warning "Dominio non inserito. Caddy userà HTTP sulla porta 80."
    fi
else
    print_warning "Caddy userà HTTP sulla porta 80."
    print_warning "Puoi configurare il dominio dopo modificando Caddyfile e riavviando Caddy."
fi

# ========================================
# 🔥 CONFIGURAZIONE FIREWALL
# ========================================
print_status "Configurazione firewall..."
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw --force enable
print_success "Firewall configurato!"

print_success "Deployment completato!"
echo ""
echo "🌐 Servizi disponibili:"
echo "   - App Web (Caddy): http://localhost (porta 80)"
if [ ! -z "$domain_name" ]; then
    echo "   - App Web HTTPS: https://${domain_name} (porta 443, SSL automatico)"
fi
echo "   - App Flask (interno): http://localhost:8000 (solo container)"
echo "   - phpMyAdmin: http://localhost:8080"
echo "   - MySQL: localhost:3306"
echo "   - Redis: localhost:6379"
if command -v curl &> /dev/null; then
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "N/A")
    echo "   - Caddy pubblico: http://${PUBLIC_IP} (se hai un IP pubblico)"
fi
echo ""
echo "📋 Comandi utili:"
echo "   - Vedi i log: docker-compose logs -f"
echo "   - Logs Caddy: docker-compose logs -f caddy"
echo "   - Logs Web: docker-compose logs -f web"
echo "   - Ferma tutto: docker-compose down"
echo "   - Riavvia: docker-compose restart"
echo "   - Riavvia solo Caddy: docker-compose restart caddy"
echo "   - Entra nel container web: docker-compose exec web bash"
echo "   - Entra nel container Caddy: docker-compose exec caddy sh"
echo ""
# ========================================
# 🗄️ CONFIGURAZIONE BACKUP AUTOMATICO
# ========================================
echo ""
print_status "Configurazione backup automatico..."

# Crea directory backup
sudo mkdir -p /var/backups/mynutriapp
sudo chown -R $USER:$USER /var/backups/mynutriapp

# Copia script backup
sudo cp scripts/backup.sh /usr/local/bin/mynutriapp-backup
sudo chmod +x /usr/local/bin/mynutriapp-backup

# Configura cron per backup giornaliero alle 2:00
CRON_JOB="0 2 * * * cd $(pwd) && /usr/local/bin/mynutriapp-backup >> /var/log/mynutriapp-backup.log 2>&1"
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

print_success "Backup automatico configurato! (ogni giorno alle 2:00)"

# ========================================
# 🧪 TEST BACKUP
# ========================================
print_status "Esecuzione test backup..."
if /usr/local/bin/mynutriapp-backup; then
    print_success "Test backup completato!"
else
    print_warning "Test backup fallito, controlla i log"
fi

# ========================================
# 🛠️ INSTALLAZIONE STRUMENTI PROFESSIONALI
# ========================================
print_status "Installazione strumenti professionali..."

# Installa strumenti di monitoring
sudo apt install htop iotop nethogs -y

# Installa bc per calcoli
sudo apt install bc -y

# Configura notifiche email
print_status "Configurazione notifiche..."
if ! grep -q "NOTIFICATION_EMAIL" .env; then
    echo "" >> .env
    echo "# Notifiche" >> .env
    echo "NOTIFICATION_EMAIL_FROM=admin@mynutriapp.com" >> .env
    echo "NOTIFICATION_EMAIL_TO=admin@mynutriapp.com" >> .env
fi

print_success "Strumenti professionali installati!"

# ========================================
# 📊 DASHBOARD MONITORING
# ========================================
print_status "Configurazione dashboard monitoring..."
# La dashboard HTML è già inclusa nel progetto

print_success "Dashboard monitoring configurata!"

print_success "Il tuo MyNutriAPP è ora online! 🚀"
