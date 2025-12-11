#!/bin/bash

# ========================================
# 🔒 DASHBOARD SICURA MYNUTRIAPP
# Configurazione dashboard protetta
# ========================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[DASHBOARD]${NC} $1"
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
# 🔒 CONFIGURAZIONE DASHBOARD SICURA
# ========================================

setup_secure_dashboard() {
    print_status "Configurazione dashboard sicura..."
    
    # Crea directory per dashboard
    sudo mkdir -p /var/www/mynutriapp-dashboard
    
    # Copia dashboard
    sudo cp dashboard.html /var/www/mynutriapp-dashboard/
    
    # Crea file .htaccess per autenticazione
    sudo tee /var/www/mynutriapp-dashboard/.htaccess > /dev/null << 'EOF'
AuthType Basic
AuthName "MyNutriAPP Dashboard"
AuthUserFile /var/www/mynutriapp-dashboard/.htpasswd
Require valid-user
EOF

    # Crea utente per dashboard
    read -p "Inserisci username per dashboard: " username
    sudo htpasswd -c /var/www/mynutriapp-dashboard/.htpasswd "$username"
    
    # Configura Nginx per dashboard
    sudo tee /etc/nginx/sites-available/mynutriapp-dashboard > /dev/null << 'EOF'
server {
    listen 8081;
    server_name _;
    
    root /var/www/mynutriapp-dashboard;
    index dashboard.html;
    
    location / {
        try_files $uri $uri/ =404;
    }
    
    # Protezione file sensibili
    location ~ /\. {
        deny all;
    }
}
EOF

    # Abilita sito
    sudo ln -sf /etc/nginx/sites-available/mynutriapp-dashboard /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    
    print_success "Dashboard sicura configurata!"
    print_status "Accesso: http://your-server-ip:8081"
    print_status "Username: $username"
}

# ========================================
# 🚀 ESECUZIONE
# ========================================

echo "🔒 DASHBOARD SICURA MYNUTRIAPP"
echo "==============================="
echo ""

setup_secure_dashboard

print_success "Dashboard protetta configurata! 🛡️"
