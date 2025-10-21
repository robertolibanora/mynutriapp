#!/bin/bash

# ========================================
# 🔒 SISTEMA SICUREZZA MYNUTRIAPP
# Hardening e sicurezza avanzata
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[SECURITY]${NC} $1"
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
# 🔐 HARDENING SISTEMA
# ========================================

update_system() {
    print_status "Aggiornamento sistema per sicurezza..."
    sudo apt update && sudo apt upgrade -y
    print_success "Sistema aggiornato"
}

configure_firewall() {
    print_status "Configurazione firewall avanzata..."
    
    # Reset firewall
    sudo ufw --force reset
    
    # Regole base
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    
    # Servizi essenziali
    sudo ufw allow 22/tcp comment 'SSH'
    sudo ufw allow 80/tcp comment 'HTTP'
    sudo ufw allow 443/tcp comment 'HTTPS'
    
    # Rate limiting per SSH
    sudo ufw limit 22/tcp comment 'SSH rate limit'
    
    # Abilita firewall
    sudo ufw --force enable
    
    print_success "Firewall configurato"
}

install_security_tools() {
    print_status "Installazione strumenti sicurezza..."
    
    # Fail2ban per protezione SSH
    sudo apt install fail2ban -y
    
    # Configura fail2ban
    sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3
bantime = 3600
EOF

    sudo systemctl enable fail2ban
    sudo systemctl start fail2ban
    
    # ClamAV per antivirus
    sudo apt install clamav clamav-daemon -y
    sudo systemctl enable clamav-daemon
    sudo systemctl start clamav-daemon
    
    print_success "Strumenti sicurezza installati"
}

configure_ssl_hardening() {
    print_status "Configurazione SSL avanzata..."
    
    # Backup configurazione Nginx
    sudo cp /etc/nginx/sites-available/mynutriapp /etc/nginx/sites-available/mynutriapp.backup
    
    # Aggiorna configurazione SSL
    sudo tee -a /etc/nginx/sites-available/mynutriapp > /dev/null << 'EOF'

    # SSL Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';" always;
    
    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
EOF

    # Test e ricarica Nginx
    sudo nginx -t && sudo systemctl reload nginx
    
    print_success "SSL hardening configurato"
}

configure_docker_security() {
    print_status "Configurazione sicurezza Docker..."
    
    # Crea utente non-root per Docker
    sudo groupadd docker 2>/dev/null || true
    sudo usermod -aG docker $USER
    
    # Configura Docker daemon per sicurezza
    sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "live-restore": true,
    "userland-proxy": false,
    "no-new-privileges": true
}
EOF

    sudo systemctl restart docker
    
    print_success "Docker security configurato"
}

# ========================================
# 🔍 SCAN SICUREZZA
# ========================================

security_scan() {
    print_status "Esecuzione scan sicurezza..."
    
    # Scan porte aperte
    echo "Porte aperte:"
    sudo netstat -tulpn | grep LISTEN
    
    # Controlla processi sospetti
    echo ""
    echo "Processi con connessioni di rete:"
    sudo netstat -tulpn | grep ESTABLISHED
    
    # Controlla permessi file sensibili
    echo ""
    echo "Permessi file .env:"
    ls -la .env 2>/dev/null || echo "File .env non trovato"
    
    # Controlla log di sicurezza
    echo ""
    echo "Tentativi di accesso falliti:"
    sudo grep "Failed password" /var/log/auth.log | tail -5
    
    print_success "Scan sicurezza completato"
}

# ========================================
# 🚀 ESECUZIONE PRINCIPALE
# ========================================

echo "🔒 HARDENING SICUREZZA MYNUTRIAPP"
echo "=================================="
echo ""

update_system
configure_firewall
install_security_tools
configure_ssl_hardening
configure_docker_security
security_scan

print_success "Hardening sicurezza completato! 🛡️"
