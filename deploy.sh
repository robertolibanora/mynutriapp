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

# Controlla se Nginx è installato
if ! command -v nginx &> /dev/null; then
    print_error "Nginx non è installato!"
    print_status "Installazione Nginx..."
    sudo apt update
    sudo apt install nginx -y
    sudo systemctl enable nginx
    sudo systemctl start nginx
    print_success "Nginx installato!"
fi

# Controlla se Certbot è installato
if ! command -v certbot &> /dev/null; then
    print_error "Certbot non è installato!"
    print_status "Installazione Certbot..."
    sudo apt install certbot python3-certbot-nginx -y
    print_success "Certbot installato!"
fi

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

# Crea directory necessarie
print_status "Creazione directory necessarie..."
mkdir -p static/uploads
mkdir -p logs
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

# Testa la connessione al database
print_status "Test connessione database..."
sleep 5
docker-compose exec -T db mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASSWORD:-root_password_super_sicura_123!} || print_warning "Database non ancora pronto"

# Testa Redis
print_status "Test connessione Redis..."
docker-compose exec -T redis redis-cli ping || print_warning "Redis non ancora pronto"

# ========================================
# 🌐 CONFIGURAZIONE NGINX
# ========================================
print_status "Configurazione Nginx..."

# Copia configurazione Nginx
sudo cp nginx.conf /etc/nginx/sites-available/mynutriapp

# Abilita il sito
sudo ln -sf /etc/nginx/sites-available/mynutriapp /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Testa configurazione Nginx
sudo nginx -t
if [ $? -eq 0 ]; then
    sudo systemctl reload nginx
    print_success "Nginx configurato!"
else
    print_error "Errore nella configurazione Nginx!"
    exit 1
fi

# ========================================
# 🔒 CONFIGURAZIONE SSL (Opzionale)
# ========================================
echo ""
print_status "Configurazione SSL..."
echo "Per configurare SSL, hai bisogno di un dominio."
echo "Vuoi configurare SSL ora? (y/n)"
read -p "Risposta: " ssl_choice

if [ "$ssl_choice" = "y" ] || [ "$ssl_choice" = "Y" ]; then
    echo "Inserisci il tuo dominio (es: example.com):"
    read -p "Dominio: " domain_name
    
    if [ ! -z "$domain_name" ]; then
        print_status "Configurazione SSL per $domain_name..."
        
        # Aggiorna configurazione Nginx con il dominio
        sudo sed -i "s/server_name _;/server_name $domain_name www.$domain_name;/" /etc/nginx/sites-available/mynutriapp
        
        # Testa e ricarica Nginx
        sudo nginx -t && sudo systemctl reload nginx
        
        # Ottieni certificato SSL
        sudo certbot --nginx -d $domain_name -d www.$domain_name --non-interactive --agree-tos --email admin@$domain_name
        
        if [ $? -eq 0 ]; then
            print_success "SSL configurato per $domain_name!"
        else
            print_warning "Errore nella configurazione SSL. Configura manualmente con:"
            print_warning "sudo certbot --nginx -d $domain_name"
        fi
    else
        print_warning "Dominio non inserito. Salto configurazione SSL."
    fi
else
    print_warning "SSL non configurato. Puoi configurarlo dopo con:"
    print_warning "sudo certbot --nginx -d your-domain.com"
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
echo "   - App Flask: http://localhost:8000"
echo "   - phpMyAdmin: http://localhost:8080"
echo "   - MySQL: localhost:3306"
echo "   - Redis: localhost:6379"
echo "   - Nginx: http://$(curl -s ifconfig.me) (se hai un IP pubblico)"
echo ""
echo "📋 Comandi utili:"
echo "   - Vedi i log: docker-compose logs -f"
echo "   - Ferma tutto: docker-compose down"
echo "   - Riavvia: docker-compose restart"
echo "   - Entra nel container: docker-compose exec web bash"
echo "   - Logs Nginx: sudo tail -f /var/log/nginx/access.log"
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
sudo cp backup.sh /usr/local/bin/mynutriapp-backup
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
