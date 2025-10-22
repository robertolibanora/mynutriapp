#!/bin/bash

# ========================================
# 🚀 SCRIPT INSTALLAZIONE DIPENDENZE - NUTRIAPP
# Ubuntu 22.04 LTS
# ========================================

set -e  # Exit on any error

echo "🚀 Inizio installazione dipendenze per NutriApp..."

# Aggiorna il sistema
echo "📦 Aggiornamento sistema..."
sudo apt update && sudo apt upgrade -y

# Installa dipendenze di sistema
echo "🔧 Installazione dipendenze di sistema..."
sudo apt install -y \
    python3.10 \
    python3.10-venv \
    python3.10-dev \
    python3-pip \
    nginx \
    supervisor \
    redis-server \
    mysql-server \
    mysql-client \
    sqlite3 \
    git \
    curl \
    wget \
    unzip \
    build-essential \
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libxcb1-dev \
    libmysqlclient-dev \
    pkg-config

# Installa Node.js (per eventuali build tools)
echo "📦 Installazione Node.js..."
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Installa Certbot per SSL
echo "🔒 Installazione Certbot per SSL..."
sudo apt install -y certbot python3-certbot-nginx

# Crea utente per l'applicazione
echo "👤 Creazione utente applicazione..."
if ! id "nutriapp" &>/dev/null; then
    sudo useradd -r -s /bin/false -d /opt/nutriapp nutriapp
    echo "✅ Utente 'nutriapp' creato"
else
    echo "ℹ️  Utente 'nutriapp' già esistente"
fi

# Crea directory per l'applicazione
echo "📁 Creazione directory applicazione..."
sudo mkdir -p /opt/nutriapp
sudo mkdir -p /opt/nutriapp/logs
sudo mkdir -p /opt/nutriapp/backups
sudo mkdir -p /var/log/nutriapp

# Imposta permessi
sudo chown -R nutriapp:nutriapp /opt/nutriapp
sudo chown -R nutriapp:nutriapp /var/log/nutriapp

# Nota: MySQL deve essere configurato manualmente
echo "🗄️ MySQL richiesto ma non configurato automaticamente"
echo "   Assicurati che MySQL sia installato e accessibile"
echo "   Database: enrico"
echo "   Host: 127.0.0.1:3306"
echo "   User: root"

# Configura Redis
echo "🔴 Configurazione Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Testa Redis
if redis-cli ping | grep -q "PONG"; then
    echo "✅ Redis funzionante"
else
    echo "❌ Errore Redis"
    exit 1
fi

# Configura firewall base
echo "🔥 Configurazione firewall..."
sudo ufw --force enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

echo "✅ Installazione dipendenze completata!"
echo ""
echo "📋 Prossimi passi:"
echo "1. Esegui: ./deploy/setup_app.sh"
echo "2. Configura il file .env"
echo "3. Esegui: ./deploy/deploy.sh"
