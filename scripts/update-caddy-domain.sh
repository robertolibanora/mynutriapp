#!/bin/bash
# ========================================
# 🔧 Script per aggiornare il dominio Caddy
# ========================================

set -e

DOMAIN="MyNutriAPP.cloud"
CADDYFILE_PATH="/etc/caddy/Caddyfile"
PROJECT_DIR="/var/www/mynutriapp"

echo "🌐 Aggiornamento configurazione Caddy per dominio: $DOMAIN"

# Backup del Caddyfile esistente
if [ -f "$CADDYFILE_PATH" ]; then
    echo "📦 Creo backup del Caddyfile esistente..."
    sudo cp "$CADDYFILE_PATH" "${CADDYFILE_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Copia il nuovo Caddyfile dal progetto
if [ -f "$PROJECT_DIR/Caddyfile" ]; then
    echo "📋 Copio il nuovo Caddyfile..."
    sudo cp "$PROJECT_DIR/Caddyfile" "$CADDYFILE_PATH"
    sudo chown root:root "$CADDYFILE_PATH"
    sudo chmod 644 "$CADDYFILE_PATH"
else
    echo "❌ Errore: Caddyfile non trovato in $PROJECT_DIR"
    exit 1
fi

# Valida il Caddyfile
echo "✅ Valido la configurazione Caddy..."
if sudo caddy validate --config "$CADDYFILE_PATH"; then
    echo "✅ Caddyfile valido!"
else
    echo "❌ Errore nella validazione del Caddyfile!"
    echo "🔄 Ripristino il backup..."
    sudo cp "${CADDYFILE_PATH}.backup"* "$CADDYFILE_PATH" 2>/dev/null || true
    exit 1
fi

# Riavvia Caddy
echo "🔄 Riavvio Caddy..."
sudo systemctl reload caddy || sudo systemctl restart caddy

# Verifica lo stato
sleep 2
if sudo systemctl is-active --quiet caddy; then
    echo "✅ Caddy riavviato correttamente!"
    echo ""
    echo "🌐 Il dominio $DOMAIN dovrebbe essere ora attivo con HTTPS automatico."
    echo "📝 Assicurati che il DNS punti al VPS:"
    echo "   A record: $DOMAIN -> $(hostname -I | awk '{print $1}')"
else
    echo "❌ Errore: Caddy non è attivo!"
    exit 1
fi
