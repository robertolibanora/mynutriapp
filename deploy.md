# 🚀 Guida Completa Deploy MyNutriApp su VPS Hostinger

**Guida definitiva** per deploy completo su VPS Hostinger con tutti i dettagli, comandi e configurazioni.

---

## 📋 Indice

1. [Prerequisiti](#prerequisiti)
2. [Deploy Completo](#deploy-completo)
3. [Configurazione .env](#configurazione-env)
4. [Script Disponibili](#script-disponibili)
5. [Gestione Quotidiana](#gestione-quotidiana)
6. [MySQL in Produzione](#mysql-in-produzione)
7. [Troubleshooting](#troubleshooting)
8. [SSL e Sicurezza](#ssl-e-sicurezza)

---

## ✅ Prerequisiti

### Requisiti VPS

- **VPS Hostinger** con Ubuntu 20.04+ o Debian 11+
- **RAM minima**: 2GB (consigliato 4GB)
- **Storage**: 20GB minimo
- **Accesso SSH** configurato
- **Dominio** (opzionale per SSL)

### Connessione al VPS

```bash
# Connettiti al tuo VPS
ssh root@your-vps-ip
# oppure
ssh your-username@your-vps-ip
```

---

## 🚀 Deploy Completo

### Passo 1: Clona il Repository

```bash
# Installa git se non presente
sudo apt update && sudo apt install -y git

# Clona il repository
git clone https://github.com/robertolibanora/mynutriapp.git
cd mynutriapp

# Verifica struttura
ls -la
```

### Passo 2: Configura File .env

```bash
# Crea file .env
nano .env
```

**Copia e modifica questo template completo:**

```env
# ========================================
# 🔐 SECRET KEY (OBBLIGATORIO)
# ========================================
# Genera con: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-secret-key-here-minimo-64-caratteri

# ========================================
# 🗄️ DATABASE MYSQL
# ========================================
MYSQL_ROOT_PASSWORD=your-secure-root-password-here
MYSQL_PASSWORD=your-secure-app-password-here

# Ottimizzazioni MySQL (opzionale - default già ottimizzato)
# MYSQL_INNODB_BUFFER_POOL_SIZE=1G  # 70% della RAM disponibile
# MYSQL_MAX_CONNECTIONS=200         # Default: 200

# ========================================
# 👤 ADMIN ACCOUNT
# ========================================
ADMIN_PHONE=+39XXXXXXXXXX
ADMIN_PASSWORD=your-admin-password-here

# ========================================
# 🌐 FLASK CONFIGURATION
# ========================================
FLASK_ENV=production
FLASK_HOST=0.0.0.0
FLASK_PORT=9091
FLASK_DEBUG=False

# ========================================
# 🗄️ DATABASE URL (Auto-generato)
# ========================================
# Non modificare, viene generato automaticamente da docker-compose.yml

# ========================================
# 🔴 REDIS
# ========================================
REDIS_HOST=redis
REDIS_PORT=6379

# ========================================
# 🚦 RATE LIMITING
# ========================================
RATELIMIT_ENABLED=True
RATELIMIT_STORAGE_URL=redis://redis:6379/0
RATELIMIT_DEFAULT_PER_DAY=200
RATELIMIT_DEFAULT_PER_HOUR=50
RATELIMIT_LOGIN_LIMIT=5 per 15 minutes
RATELIMIT_CREATE_LIMIT=20 per hour
RATELIMIT_UPLOAD_LIMIT=10 per hour

# ========================================
# 📱 WHATSAPP (Opzionale)
# ========================================
WHATSAPP_ACCESS_TOKEN=your-token-here
WHATSAPP_PHONE_NUMBER_ID=your-phone-id-here

# ========================================
# 📧 NOTIFICHE (Opzionale)
# ========================================
NOTIFICATION_EMAIL_FROM=admin@mynutriapp.com
NOTIFICATION_EMAIL_TO=your-email@example.com
```

**Salva e esci:** `Ctrl+X`, poi `Y`, poi `Enter`

**Genera SECRET_KEY:**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Passo 3: Esegui Deploy Automatico

```bash
# Rendi eseguibile lo script deploy
chmod +x deploy.sh

# Esegui il deploy (FA TUTTO AUTOMATICAMENTE!)
./deploy.sh
```

**Cosa fa `deploy.sh` automaticamente:**

1. ✅ **Installa Docker** (se non presente)
2. ✅ **Installa Docker Compose** (se non presente)
3. ✅ **Verifica file .env** (esce se mancante)
4. ✅ **Crea directory necessarie** (`static/uploads`, `logs`, `logs/nginx`)
5. ✅ **Ferma container esistenti** (se presenti)
6. ✅ **Costruisce e avvia container** (`docker-compose up -d --build`)
7. ✅ **Attende MySQL pronto** (healthcheck passa)
8. ✅ **Testa connessioni** (MySQL e Redis)
9. ✅ **Configura firewall** (porte 22, 80, 443)
10. ✅ **Configura backup automatico** (cron ogni giorno alle 2:00)
11. ✅ **Installa strumenti monitoring** (htop, iotop, nethogs)

**Tempo stimato:** 5-10 minuti

**Opzioni deploy.sh:**

```bash
# Deploy normale
./deploy.sh

# Deploy con pulizia completa (rimuove immagini vecchie)
./deploy.sh --clean
```

### Passo 4: Verifica Deploy

```bash
# Verifica stato container
docker-compose ps
```

**Output atteso:**

```
NAME                    STATUS
mynutriapp_web          Up
mynutriapp_nginx        Up
mynutriapp_db           Up (healthy)
mynutriapp_redis        Up
mynutriapp_phpmyadmin   Up
```

**Se MySQL non è "(healthy)":**

```bash
# Attendi qualche secondo e riprova
sleep 30
docker-compose ps db

# Vedi log MySQL
docker-compose logs db
```

---

## 🌐 Accesso all'Applicazione

### HTTP (Porta 80)

```
http://your-vps-ip
```

### HTTPS (Porta 443) - Se configurato SSL

```
https://your-domain.com
```

### phpMyAdmin (Porta 8080)

```
http://your-vps-ip:8080
```

**Credenziali phpMyAdmin:**

- **Server**: `db`
- **Username**: `root`
- **Password**: `[MYSQL_ROOT_PASSWORD dal tuo .env]`

---

## 📜 Script Disponibili

Tutti gli script sono nella cartella `scripts/` e possono essere eseguiti dalla root del progetto.

### 🚀 `deploy.sh` (Root) - Script Deploy Principale

**Percorso:** `./deploy.sh`

**Cosa fa:**

- Installa Docker e Docker Compose
- Verifica `.env`
- Avvia tutti i container
- Configura firewall
- Configura backup automatico

**Comando:**

```bash
chmod +x deploy.sh
./deploy.sh
```

**Quando usarlo:**

- Primo deploy sul VPS
- Dopo modifiche a `.env`
- Dopo aggiornamenti codice

---

### 🗄️ `scripts/backup.sh` - Backup Database

**Percorso:** `./scripts/backup.sh`

**Cosa fa:**

- Esegue backup completo MySQL
- Comprime backup (.gz)
- Mantiene ultimi 7 backup
- Salva in `/var/backups/mynutriapp/`

**Comando:**

```bash
# Backup manuale
./scripts/backup.sh

# O tramite comando installato (dopo deploy.sh)
/usr/local/bin/mynutriapp-backup
```

**Quando usarlo:**

- Prima di aggiornamenti importanti
- Backup manuale su richiesta
- Eseguito automaticamente ogni giorno alle 2:00

**Output:**

```
[BACKUP] Avvio backup database MyNutriAPP...
[BACKUP] Esecuzione backup database...
[SUCCESS] Backup completato: mynutriapp_backup_20241211_140530.sql
[BACKUP] Compressione backup...
[SUCCESS] Backup compresso: mynutriapp_backup_20241211_140530.sql.gz
```

---

### 🎛️ `scripts/manage.sh` - Menu Interattivo Completo

**Percorso:** `./scripts/manage.sh`

**Cosa fa:**

- Menu interattivo per gestire tutto
- Controlla container Docker
- Gestisce backup
- Mostra statistiche
- Gestisce aggiornamenti

**Comando:**

```bash
./scripts/manage.sh
```

**Menu disponibile:**

```
🐳 DOCKER & CONTAINER
1.  Avvia tutti i servizi
2.  Ferma tutti i servizi
3.  Riavvia tutti i servizi
4.  Stato container
5.  Logs in tempo reale

🗄️  DATABASE & BACKUP
6.  Gestione backup
7.  Backup manuale
8.  Ripristina backup
9.  Accesso database

📊 MONITORING & SICUREZZA
10. Dashboard monitoring
11. Controllo sicurezza
12. Test notifiche
13. Statistiche sistema

🔄 AGGIORNAMENTI
14. Aggiorna applicazione
15. Aggiorna sistema
16. Pulizia sistema

🌐 NGINX & SSL
17. Riavvia Nginx
18. Test configurazione Nginx
19. Rinnova certificato SSL

📋 UTILITÀ
20. Vedi tutti i log
21. Spazio disco
22. Processi attivi
23. Configura notifiche
24. Esci
```

**Quando usarlo:**

- Gestione quotidiana
- Monitoraggio rapido
- Operazioni di manutenzione

---

### 📊 `scripts/monitoring.sh` - Monitoring Sistema

**Percorso:** `./scripts/monitoring.sh`

**Cosa fa:**

- Controlla stato container Docker
- Verifica database MySQL (connessioni, dimensione)
- Verifica Redis (memoria, chiavi)
- Controlla Nginx (configurazione, connessioni)
- Analizza spazio disco e memoria
- Mostra metriche performance
- Analizza log errori

**Comando:**

```bash
./scripts/monitoring.sh
```

**Output esempio:**

```
[MONITORING] Controllo container Docker...
[SUCCESS] Container attivi:
NAME                    STATUS
mynutriapp_web          Up
mynutriapp_db           Up (healthy)

[MONITORING] Controllo database MySQL...
[SUCCESS] Database MySQL: OK
   - Connessioni attive: 5
   - Dimensione database: 12.45 MB

[MONITORING] Controllo Redis...
[SUCCESS] Redis: OK
   - Memoria utilizzata: 2.5M
   - Chiavi in memoria: 15
```

**Quando usarlo:**

- Monitoraggio quotidiano
- Troubleshooting problemi
- Verifica performance

---

### 🔒 `scripts/security.sh` - Hardening Sicurezza

**Percorso:** `./scripts/security.sh`

**Cosa fa:**

- Aggiorna sistema operativo
- Configura firewall avanzato (UFW)
- Installa Fail2ban (protezione SSH)
- Configura SSL hardening
- Configura sicurezza Docker
- Esegue scan sicurezza

**Comando:**

```bash
./scripts/security.sh
```

**Quando usarlo:**

- Dopo il primo deploy
- Periodicamente per verificare sicurezza
- Prima di esporre server pubblicamente

**Note:**

- ⚠️ Richiede privilegi sudo
- Alcune funzioni SSL richiedono configurazione manuale

---

### 🔄 `scripts/update.sh` - Aggiornamenti Sistema

**Percorso:** `./scripts/update.sh`

**Cosa fa:**

- Aggiorna applicazione (git pull + rebuild)
- Aggiorna sistema operativo
- Aggiorna Docker
- Pulisce sistema (container, immagini - **VOLUMI PRESERVATI**)

**⚠️ IMPORTANTE - Persistenza Database:**

- ✅ **I volumi del database (`mysql_data`, `redis_data`) sono SEMPRE preservati durante gli aggiornamenti**
- ✅ Lo script usa `docker-compose down` (senza `-v`) che mantiene i volumi intatti
- ✅ Il database viene automaticamente riutilizzato al riavvio dopo l'aggiornamento
- ✅ Viene eseguito un backup automatico prima di ogni aggiornamento
- ⚠️ Solo `docker-compose down -v` rimuoverebbe i volumi (NON usato negli script normali)

---

### 🔐 `scripts/renew-ssl.sh` - Gestione Certificati SSL

**Percorso:** `./scripts/renew-ssl.sh`

**Cosa fa:**

- Rinnova certificati SSL Let's Encrypt
- Ottiene nuovi certificati SSL
- Mostra stato certificati esistenti
- Testa configurazione SSL

**Comandi disponibili:**

```bash
# Rinnova certificati esistenti
./scripts/renew-ssl.sh renew

# Ottieni nuovo certificato
./scripts/renew-ssl.sh obtain your-domain.com your-email@example.com

# Mostra stato certificati
./scripts/renew-ssl.sh status

# Test configurazione SSL
./scripts/renew-ssl.sh test your-domain.com
```

**Quando usarlo:**

- Prima configurazione SSL
- Rinnovo manuale certificati (opzionale - già automatico)
- Verifica stato certificati
- Troubleshooting SSL

**Nota:** Il rinnovo automatico è già configurato in `docker-compose.yml` (ogni 12 ore). Questo script è utile per operazioni manuali o verifica.

**Comandi disponibili:**

```bash
# Aggiorna solo applicazione
./scripts/update.sh app

# Aggiorna sistema operativo
./scripts/update.sh system

# Aggiorna Docker
./scripts/update.sh docker

# Pulisci sistema (rimuove container/images/volumes non usati)
./scripts/update.sh cleanup

# Tutto insieme
./scripts/update.sh all
```

**Quando usarlo:**

- Aggiornamenti applicazione
- Manutenzione periodica
- Pulizia spazio disco

**Cosa fa `update.sh app`:**

1. Esegue backup database
2. Ferma container
3. Pull ultime modifiche (`git pull`)
4. Rebuild container (`docker-compose build --no-cache`)
5. Avvia container (`docker-compose up -d`)
6. Testa applicazione
7. Se fallisce, ripristina versione precedente

---

### 🗄️ `scripts/manage-backup.sh` - Gestione Backup Interattiva

**Percorso:** `./scripts/manage-backup.sh`

**Cosa fa:**

- Menu interattivo per gestire backup
- Lista backup disponibili
- Ripristina backup
- Pulisci backup vecchi
- Mostra statistiche

**Comando:**

```bash
./scripts/manage-backup.sh
```

**Menu disponibile:**

```
🗄️  GESTIONE BACKUP MYNUTRIAPP
================================
1. Esegui backup manuale
2. Lista backup disponibili
3. Ripristina backup
4. Pulisci backup vecchi
5. Mostra statistiche
6. Testa backup
7. Configura backup automatico
8. Disabilita backup automatico
9. Esci
```

**Ripristino backup:**

```bash
./scripts/manage-backup.sh
# Scegli opzione 3
# Seleziona il backup da ripristinare
# Conferma operazione
```

---

### ⏰ `scripts/setup-backup.sh` - Configurazione Backup Automatico

**Percorso:** `./scripts/setup-backup.sh`

**Cosa fa:**

- Configura backup automatico giornaliero
- Crea directory backup
- Installa script backup
- Configura cron job (ogni giorno alle 2:00)

**Comando:**

```bash
./scripts/setup-backup.sh
```

**Quando usarlo:**

- Se backup automatico non configurato da `deploy.sh`
- Per riconfigurare backup

**Note:**

- ✅ Viene eseguito automaticamente da `deploy.sh`
- Non necessario eseguirlo manualmente

---

### 📧 `scripts/notifications.sh` - Sistema Notifiche

**Percorso:** `./scripts/notifications.sh`

**Cosa fa:**

- Invia notifiche email per eventi critici
- Monitora salute sistema
- Notifica backup falliti/riusciti
- Avvisa per CPU/memoria/disco alti

**Comandi disponibili:**

```bash
# Test notifiche
./scripts/notifications.sh test

# Controllo salute sistema
./scripts/notifications.sh check

# Notifica backup riuscito
./scripts/notifications.sh backup-success "10MB"

# Notifica backup fallito
./scripts/notifications.sh backup-failed
```

**Quando usarlo:**

- Configurazione iniziale (test)
- Integrazione con cron per monitoraggio automatico

**Configurazione email in `.env`:**

```env
NOTIFICATION_EMAIL_FROM=admin@mynutriapp.com
NOTIFICATION_EMAIL_TO=your-email@example.com
```

---

## 🗄️ MySQL in Produzione

### Configurazione Attuale

Il progetto usa **MySQL 8.0** containerizzato con:

- ✅ Configurazione ottimizzata (`mysql-production.cnf`)
- ✅ Charset UTF8MB4 per Unicode completo
- ✅ InnoDB come storage engine
- ✅ Binary logging per backup incrementali
- ✅ Slow query log per ottimizzazione
- ✅ Performance tuning applicato

### File di Configurazione

**`mysql-production.cnf`** contiene:

- Buffer pool InnoDB: 1GB (70% RAM per VPS 2GB)
- Max connections: 200
- Slow query log: query >2 secondi
- Binary log: abilitato per 7 giorni

**Personalizzazione nel `.env`:**

```env
# Per VPS con 4GB RAM, aumenta buffer pool
MYSQL_INNODB_BUFFER_POOL_SIZE=2G

# Per più utenti simultanei
MYSQL_MAX_CONNECTIONS=300
```

### Verifica MySQL

```bash
# Accedi a MySQL
docker-compose exec db mysql -u root -p

# Verifica configurazione
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE 'character_set_server';

# Verifica tabelle
USE mynutriapp;
SHOW TABLES;

# Dovresti vedere 11 tabelle:
# - patients
# - diete
# - allenamenti
# - progressi
# - misure_antropometriche
# - composizione_corporea
# - documents
# - listino
# - vendite
# - appuntamenti
# - slot_disponibilita

# Esci
exit
```

### Monitoraggio MySQL

```bash
# Stato connessioni
docker-compose exec db mysql -u root -p -e "SHOW STATUS LIKE 'Threads_connected';"

# Dimensione database
docker-compose exec db mysql -u root -p -e "
SELECT 
    table_schema AS 'Database',
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
FROM information_schema.tables
WHERE table_schema = 'mynutriapp'
GROUP BY table_schema;"

# Slow query log
docker-compose exec db tail -f /var/lib/mysql/slow-query.log
```

---

## 🔄 Flusso di Avvio Completo

### 1. Avvio Container MySQL

Quando esegui `docker-compose up`:

1. **MySQL si avvia** e crea automaticamente:

   - Database `mynutriapp` (tramite `MYSQL_DATABASE`)
   - Utente `mynutriapp` (tramite `MYSQL_USER` e `MYSQL_PASSWORD`)
   - Password root (tramite `MYSQL_ROOT_PASSWORD`)
2. **MySQL esegue `init.sql`** automaticamente:

   - Solo se il volume MySQL è vuoto (primo avvio)
   - Crea tutte le 11 tabelle necessarie
   - Usa `CREATE TABLE IF NOT EXISTS` (idempotente)
3. **Healthcheck MySQL** verifica:

   - Che MySQL risponda ai ping
   - Che il database sia accessibile
   - Attende fino a 30 secondi per il primo controllo

### 2. Avvio Container Flask

Flask si avvia SOLO dopo che MySQL è `healthy`:

- MySQL deve essere healthy prima che Flask parta
- Redis deve essere started
- Flask si connette e trova tabelle già create

### 3. Avvio Container Nginx

Nginx si avvia dopo Flask e funge da reverse proxy.

### Comando Flask di Backup

Se `init.sql` non viene eseguito, crea le tabelle manualmente:

```bash
# Entra nel container Flask
docker-compose exec web bash

# Esegui il comando Flask init-db
flask init-db

# Esci
exit
```

---

## 🛠️ Gestione Quotidiana

### Comandi Docker Essenziali

```bash
# Stato container
docker-compose ps

# Log in tempo reale
docker-compose logs -f

# Log di un servizio specifico
docker-compose logs -f web
docker-compose logs -f nginx
docker-compose logs -f db
docker-compose logs -f redis

# Riavvia un servizio
docker-compose restart web
docker-compose restart nginx
docker-compose restart db

# Riavvia tutto
docker-compose restart

# Ferma tutto
docker-compose down

# Avvia tutto
docker-compose up -d

# Rebuild e avvia
docker-compose up -d --build

# Entra in un container
docker-compose exec web bash
docker-compose exec db mysql -u root -p
docker-compose exec nginx sh
docker-compose exec redis redis-cli
```

### Backup

```bash
# Backup manuale
./scripts/backup.sh

# Gestione backup interattiva
./scripts/manage-backup.sh

# Lista backup disponibili
ls -la /var/backups/mynutriapp/

# Backup automatico (ogni giorno alle 2:00)
# Configurato automaticamente da deploy.sh
```

### Monitoring

```bash
# Menu interattivo completo
./scripts/manage.sh

# Monitoring sistema
./scripts/monitoring.sh

# Verifica stato rapido
docker-compose ps
```

### Aggiornamenti

```bash
# Aggiorna applicazione
./scripts/update.sh app

# O manualmente:
git pull
docker-compose down
docker-compose up -d --build
```

---

## 🔒 SSL e Sicurezza

### Configurazione SSL Completamente Containerizzata

**✅ SSL e Certbot sono già completamente containerizzati nel progetto!**

Il servizio Certbot è configurato in `docker-compose.yml` e si avvia automaticamente con:
- Rinnovo automatico ogni 12 ore
- Persistenza certificati tramite volumi Docker
- Integrazione completa con Nginx containerizzato

**Prerequisiti:**

- Dominio configurato e puntato al tuo VPS (record A DNS)
- Porte 80 e 443 aperte sul firewall
- Email valida per le notifiche di scadenza certificati

---

### Passo 1: Verifica Configurazione

Le directory Certbot vengono create automaticamente da `deploy.sh`. Verifica che esistano:

```bash
# Verifica directory Certbot
ls -la certbot/

# Dovresti vedere:
# - certbot/conf/    (certificati SSL)
# - certbot/www/     (webroot per ACME challenge)
# - certbot/logs/    (log Certbot)
```

Se le directory non esistono, creale manualmente:

```bash
mkdir -p certbot/conf certbot/www certbot/logs
chmod -R 755 certbot
```

---

### Passo 2: Avvia i Servizi

Il servizio Certbot è già configurato in `docker-compose.yml`. Avvia tutti i servizi:

```bash
# Avvia tutti i servizi (incluso Certbot)
docker-compose up -d

# Verifica che Certbot sia in esecuzione
docker-compose ps certbot
```

**Nota:** Certbot si avvia automaticamente e rimane in esecuzione per il rinnovo automatico.

---

### Passo 3: Ottieni Certificati SSL

Usa lo script dedicato per ottenere nuovi certificati:

```bash
# Ottieni certificato SSL (sostituisci dominio e email)
./scripts/renew-ssl.sh obtain your-domain.com your-email@example.com

# Lo script gestisce automaticamente:
# - Verifica che Nginx sia in esecuzione
# - Richiede certificato a Let's Encrypt
# - Salva certificati in certbot/conf/
```

**Oppure manualmente:**

```bash
# Ottieni certificati (sostituisci con il tuo dominio e email)
docker-compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d your-domain.com \
  -d www.your-domain.com

# Verifica che i certificati siano stati creati
ls -la certbot/conf/live/your-domain.com/
```

Dovresti vedere:
- `cert.pem` - Certificato
- `chain.pem` - Catena di certificati
- `fullchain.pem` - Certificato completo (cert + chain)
- `privkey.pem` - Chiave privata

---

### Passo 4: Configura Nginx per HTTPS

Il file `nginx.conf` è già configurato per servire la challenge ACME. Ora devi configurare HTTPS.

**Opzione A: Usa il file di esempio (Raccomandato)**

```bash
# Copia il file di esempio
cp nginx-ssl.conf.example nginx.conf

# Sostituisci il dominio nel file
sed -i 's/your-domain.com/tuo-dominio.com/g' nginx.conf

# Riavvia Nginx
docker-compose restart nginx
```

**Opzione B: Aggiorna manualmente `nginx.conf`**

Aggiungi un nuovo blocco `server` per HTTPS (vedi `nginx-ssl.conf.example` per esempio completo):

```nginx
# Redirect HTTP a HTTPS
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    # ACME Challenge (già presente in nginx.conf)
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect tutto il resto a HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# Server HTTPS principale
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # Certificati SSL (montati da docker-compose)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # ... resto della configurazione SSL ...
}
```

**⚠️ Ricorda di sostituire `your-domain.com` con il tuo dominio reale!**

---

### Passo 5: Riavvia Nginx

```bash
# Test configurazione Nginx
docker-compose exec nginx nginx -t

# Se OK, riavvia Nginx
docker-compose restart nginx

# Verifica che HTTPS funzioni
curl -I https://your-domain.com
```

---

### Passo 5: Configura Nginx per HTTPS

Crea un nuovo file `nginx-ssl.conf` o aggiorna `nginx.conf` con questa configurazione completa:

```nginx
# ========================================
# 🌐 CONFIGURAZIONE NGINX CON SSL
# ========================================

# Redirect HTTP a HTTPS
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    # ACME Challenge per rinnovo certificati
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect tutto il resto a HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# Server HTTPS principale
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # Certificati SSL
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL Configuration (Best Practices)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "no-referrer-when-downgrade";

    # File upload size
    client_max_body_size 10M;

    # Static files
    location /static/ {
        alias /usr/share/nginx/html/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Proxy to Flask app
    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Rate limiting per login
    location /login {
        limit_req zone=login burst=3 nodelay;
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
    }

    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

**⚠️ Ricorda di sostituire `your-domain.com` con il tuo dominio reale!**

**💡 Suggerimento:** Puoi usare il file di esempio `nginx-ssl.conf.example` come base e personalizzarlo secondo le tue esigenze.

---

### Passo 6: Riavvia Nginx

```bash
# Riavvia Nginx con la configurazione SSL
docker-compose restart nginx

# Verifica che tutto funzioni
docker-compose logs nginx
curl -I https://your-domain.com
```

---

### Passo 6: Rinnovo Automatico Certificati

**✅ Rinnovo automatico già configurato!**

Il servizio Certbot in `docker-compose.yml` è configurato per rinnovare automaticamente i certificati ogni 12 ore. Non è necessaria alcuna configurazione aggiuntiva.

**Come funziona:**

- Certbot container si avvia automaticamente con `docker-compose up -d`
- Esegue `certbot renew` ogni 12 ore automaticamente
- Riavvia Nginx solo quando i certificati vengono effettivamente rinnovati
- I certificati sono sempre aggiornati senza intervento manuale

**Rinnovo manuale (se necessario):**

```bash
# Usa lo script dedicato
./scripts/renew-ssl.sh renew

# Oppure direttamente
docker-compose run --rm certbot renew --webroot --webroot-path=/var/www/certbot
docker-compose restart nginx
```

**Verifica stato certificati:**

```bash
# Mostra informazioni sui certificati
./scripts/renew-ssl.sh status

# Oppure direttamente
docker-compose exec certbot certbot certificates
```

**Opzione avanzata: Cron Job per sicurezza aggiuntiva**

Se vuoi un controllo extra, puoi aggiungere un cron job che verifica periodicamente:

```bash
# Aggiungi al crontab (esegue ogni giorno alle 3:00 AM)
crontab -e

# Aggiungi questa riga (sostituisci con il percorso corretto)
0 3 * * * cd /path/to/MyNutriApp && ./scripts/renew-ssl.sh renew >> /var/log/ssl-renewal.log 2>&1
```

**Nota:** Questo è opzionale perché Certbot già rinnova automaticamente ogni 12 ore.

---

### Passo 7: Verifica Configurazione SSL

```bash
# Usa lo script dedicato per test
./scripts/renew-ssl.sh test your-domain.com

# Oppure manualmente:

# Test configurazione SSL
openssl s_client -connect your-domain.com:443 -servername your-domain.com

# Verifica rating SSL (online)
# Visita: https://www.ssllabs.com/ssltest/analyze.html?d=your-domain.com

# Verifica certificato dal container Nginx
docker-compose exec nginx openssl x509 -in /etc/letsencrypt/live/your-domain.com/cert.pem -text -noout

# Verifica certificato dal container Certbot
docker-compose exec certbot certbot certificates
```

---

### Troubleshooting SSL

**Errore: "Failed to obtain certificate"**

```bash
# Verifica che Nginx serva correttamente la challenge
curl http://your-domain.com/.well-known/acme-challenge/test

# Verifica che la porta 80 sia aperta
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Verifica log Certbot
docker-compose logs certbot
```

**Errore: "Certificate not found"**

```bash
# Verifica che i certificati esistano
ls -la certbot/conf/live/your-domain.com/

# Verifica permessi
chmod -R 755 certbot/conf
```

**Nginx non si avvia dopo configurazione SSL**

```bash
# Verifica sintassi configurazione
docker-compose exec nginx nginx -t

# Controlla log errori
docker-compose logs nginx | grep -i error
```

---

### Script SSL Disponibili

Il progetto include `scripts/renew-ssl.sh` con funzionalità complete:

```bash
# Rinnova certificati esistenti
./scripts/renew-ssl.sh renew

# Ottieni nuovo certificato
./scripts/renew-ssl.sh obtain your-domain.com your-email@example.com

# Mostra stato certificati
./scripts/renew-ssl.sh status

# Test configurazione SSL
./scripts/renew-ssl.sh test your-domain.com

# Mostra help
./scripts/renew-ssl.sh
```

**Vantaggi della configurazione containerizzata:**

- ✅ Rinnovo automatico ogni 12 ore (configurato in docker-compose.yml)
- ✅ Nessuna installazione manuale di Certbot sul sistema host
- ✅ Certificati persistenti tramite volumi Docker
- ✅ Integrazione completa con Nginx containerizzato
- ✅ Script dedicato per gestione facile
- ✅ Log centralizzati in `certbot/logs/`

---

### File di Configurazione SSL

Nel progetto è disponibile un file di esempio `nginx-ssl.conf.example` che contiene una configurazione completa e sicura per Nginx con SSL. Puoi usarlo come riferimento o copiarlo come `nginx.conf` dopo aver ottenuto i certificati.

**Caratteristiche della configurazione SSL:**

- ✅ Redirect automatico HTTP → HTTPS
- ✅ Supporto solo TLS 1.2 e 1.3
- ✅ Cipher suites moderne e sicure
- ✅ OCSP Stapling abilitato
- ✅ HSTS (HTTP Strict Transport Security)
- ✅ Security headers completi
- ✅ Rate limiting su endpoint critici
- ✅ Blocco accesso a file sensibili

**Come usarlo:**

```bash
# Copia il file di esempio
cp nginx-ssl.conf.example nginx.conf

# Modifica il dominio nel file
sed -i 's/your-domain.com/tuo-dominio.com/g' nginx.conf

# Riavvia Nginx
docker-compose restart nginx
```

---

### Hardening Sicurezza

Dopo aver configurato SSL, esegui lo script di hardening:

```bash
# Esegui script sicurezza
./scripts/security.sh
```

Questo configura:

- **Firewall avanzato (UFW)**
  - Blocca tutte le porte tranne quelle necessarie (22, 80, 443)
  - Rate limiting per connessioni SSH
  - Protezione DDoS base

- **Fail2ban per protezione SSH**
  - Blocca automaticamente IP che tentano accessi non autorizzati
  - Configurazione jail personalizzata per SSH

- **SSL/TLS Hardening**
  - Configurazione cipher suites sicure
  - Disabilita protocolli SSL obsoleti (TLS 1.0, TLS 1.1)
  - HSTS (HTTP Strict Transport Security)
  - OCSP Stapling

- **Sicurezza Docker**
  - Configurazione daemon Docker sicura
  - Limitazione risorse container
  - Audit logging

- **Sicurezza Sistema**
  - Aggiornamenti automatici sicurezza
  - Disabilita servizi non necessari
  - Configurazione log rotation

**⚠️ Nota:** Lo script richiede privilegi `sudo` e alcune configurazioni potrebbero richiedere riavvio del sistema.

---

### Checklist Sicurezza Post-Deploy

- [ ] SSL/HTTPS configurato e funzionante
- [ ] Firewall (UFW) attivo e configurato
- [ ] Fail2ban installato e attivo
- [ ] Password SSH sicura (o meglio, chiavi SSH)
- [ ] Backup automatico configurato
- [ ] Log monitoring attivo
- [ ] Certificati SSL con rinnovo automatico configurato
- [ ] Security headers configurati in Nginx
- [ ] Rate limiting attivo su endpoint critici

---

## 🐛 Troubleshooting Completo

### Container non si avvia

```bash
# Vedi log dettagliati
docker-compose logs [nome-container]

# Verifica configurazione
docker-compose config

# Riavvia tutto
docker-compose down
docker-compose up -d

# Verifica errori specifici
docker-compose logs web | grep -i error
docker-compose logs db | grep -i error
docker-compose logs nginx | grep -i error
```

### Database non accessibile

```bash
# Verifica che MySQL sia healthy
docker-compose ps db

# Accedi al database
docker-compose exec db mysql -u root -p

# Verifica log MySQL
docker-compose logs db

# Testa connessione manualmente
docker-compose exec db mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASSWORD}

# Se le tabelle non esistono, creale manualmente
docker-compose exec web flask init-db
```

### Problemi con .env

```bash
# Verifica che .env esista
ls -la .env

# Verifica variabili essenziali
grep -E "SECRET_KEY|MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD" .env

# Ricarica variabili e riavvia
source .env
docker-compose down
docker-compose up -d
```

### Porta già in uso

```bash
# Verifica porte utilizzate
sudo netstat -tulpn | grep -E "80|443|3306|6379|8080"

# Ferma servizi conflittuali
sudo systemctl stop nginx  # Se installato sul sistema
sudo systemctl stop mysql   # Se installato sul sistema
sudo systemctl stop apache2  # Se installato

# Riavvia container
docker-compose restart
```

### MySQL non si avvia

```bash
# Verifica log MySQL
docker-compose logs db

# Verifica configurazione
docker-compose exec db mysqld --validate-config

# Verifica permessi volume
docker volume inspect mynutriapp_mysql_data

# Verifica che il volume esista e contenga dati
docker-compose exec db mysql -u root -p -e "USE mynutriapp; SHOW TABLES;"

# ⚠️ ATTENZIONE: Ricrea volume (PERDE TUTTI I DATI!)
# Usa SOLO se vuoi resettare completamente il database
docker-compose down -v  # ⚠️ Questo rimuove i volumi!
docker-compose up -d db
```

### Flask non si connette al database

```bash
# Verifica che MySQL sia healthy
docker-compose ps db

# Verifica DATABASE_URL
docker-compose exec web env | grep DATABASE_URL

# Testa connessione manualmente
docker-compose exec web python3 -c "
from app.config.config import Config
print(Config.SQLALCHEMY_DATABASE_URI)
"

# Verifica log Flask
docker-compose logs web | grep -i "database\|mysql\|error"
```

### Nginx non funziona

```bash
# Verifica configurazione Nginx
docker-compose exec nginx nginx -t

# Verifica log Nginx
docker-compose logs nginx

# Riavvia Nginx
docker-compose restart nginx

# Verifica che Nginx sia attivo
docker-compose ps nginx
```

### Backup fallisce

```bash
# Verifica che il container database sia attivo
docker-compose ps db

# Prova backup manuale
./scripts/backup.sh

# Verifica permessi directory backup
ls -la /var/backups/mynutriapp/

# Verifica cron job
crontab -l | grep mynutriapp-backup

# Vedi log backup
tail -f /var/log/mynutriapp-backup.log
```

---

## 📊 Verifica Funzionamento

### Test Endpoint

```bash
# Health check
curl http://localhost/health
# Dovrebbe rispondere: healthy

# Homepage
curl http://localhost/
# Dovrebbe rispondere con HTML

# Verifica Nginx
curl -I http://localhost
# Dovrebbe mostrare header HTTP 200
```

### Test Database

```bash
# Accedi al database
docker-compose exec db mysql -u root -p mynutriapp

# Verifica tabelle
SHOW TABLES;
# Dovresti vedere 11 tabelle

# Test query
SELECT COUNT(*) FROM patients;
SELECT COUNT(*) FROM diete;
SELECT COUNT(*) FROM appuntamenti;

# Esci
exit
```

### Test Redis

```bash
# Test Redis
docker-compose exec redis redis-cli ping
# Dovrebbe rispondere: PONG

# Verifica chiavi
docker-compose exec redis redis-cli KEYS "*"

# Verifica memoria
docker-compose exec redis redis-cli INFO memory
```

### Test Container

```bash
# Verifica tutti i container sono attivi
docker-compose ps

# Verifica healthcheck MySQL
docker-compose ps db | grep healthy

# Verifica log senza errori
docker-compose logs --tail=50 | grep -i error
```

---

## 📋 Checklist Deploy Completo

### Pre-Deploy

- [ ] VPS Hostinger accessibile via SSH
- [ ] Repository clonato
- [ ] File `.env` creato e configurato
- [ ] Variabili essenziali impostate:
  - [ ] `SECRET_KEY` (generata)
  - [ ] `MYSQL_ROOT_PASSWORD`
  - [ ] `MYSQL_PASSWORD`
  - [ ] `ADMIN_PHONE`
  - [ ] `ADMIN_PASSWORD`

### Deploy

- [ ] `deploy.sh` eseguito con successo
- [ ] Docker installato
- [ ] Docker Compose installato
- [ ] Tutti i container sono "Up"
- [ ] MySQL è "(healthy)"
- [ ] Nessun errore nei log

### Post-Deploy

- [ ] Applicazione accessibile su `http://your-vps-ip`
- [ ] Login funzionante
- [ ] Database accessibile
- [ ] Backup automatico configurato
- [ ] Firewall configurato
- [ ] phpMyAdmin accessibile (opzionale)
- [ ] SSL configurato (opzionale)

---

## 🔄 Workflow Quotidiano

### Mattina - Verifica Sistema

```bash
# Verifica stato container
docker-compose ps

# Verifica log errori
docker-compose logs --tail=100 | grep -i error

# Monitoring sistema
./scripts/monitoring.sh
```

### Backup

```bash
# Backup automatico (ogni giorno alle 2:00)
# Verifica ultimo backup
ls -lt /var/backups/mynutriapp/ | head -5

# Backup manuale se necessario
./scripts/backup.sh
```

### Aggiornamenti

```bash
# Aggiorna applicazione (database preservato automaticamente)
./scripts/update.sh app

# Verifica funzionamento dopo aggiornamento
docker-compose ps
curl http://localhost/health

# Verifica che il database sia ancora presente
docker-compose exec db mysql -u root -p -e "USE mynutriapp; SHOW TABLES;"
```

**🔒 Protezione Dati durante Aggiornamenti:**

- ✅ I volumi Docker (`mysql_data`, `redis_data`) sono **persistenti** e **non vengono mai rimossi** durante aggiornamenti normali
- ✅ `docker-compose down` (usato da `update.sh`) **preserva** tutti i volumi
- ✅ Solo `docker-compose down -v` rimuoverebbe i volumi (⚠️ **NON usato negli script**)
- ✅ Backup automatico viene eseguito prima di ogni aggiornamento
- ✅ Dopo `git pull` e rebuild, i container si riconnettono automaticamente ai volumi esistenti

### Monitoraggio

```bash
# Menu interattivo completo
./scripts/manage.sh

# O comandi diretti
docker-compose ps
docker-compose logs -f
```

---

## 📝 Note Importanti

1. **Tutto è containerizzato** - Non installare servizi sul sistema host
2. **Backup automatico** - Configurato ogni giorno alle 2:00 in `/var/backups/mynutriapp/`
3. **🔒 Persistenza Database** - I volumi Docker (`mysql_data`, `redis_data`) sono **SEMPRE preservati** durante:
   - Aggiornamenti applicazione (`./scripts/update.sh app`)
   - Redeploy (`./deploy.sh`)
   - Riavvii container (`docker-compose restart`)
   - Fermate temporanee (`docker-compose down`)
   - Solo `docker-compose down -v` rimuoverebbe i volumi (⚠️ **NON usato negli script normali**)
3. **Firewall** - Configurato automaticamente (porte 22, 80, 443)
4. **Log** - Disponibili tramite `docker-compose logs`
5. **SSL** - Richiede configurazione manuale (vedi sezione SSL)
6. **MySQL** - Configurato per produzione con ottimizzazioni
7. **Script** - Tutti nella cartella `scripts/`, eseguibili dalla root

---

## 🆘 Supporto e Risorse

### Comandi di Emergenza

```bash
# Ferma tutto
docker-compose down

# Riavvia tutto
docker-compose up -d

# Vedi tutti i log
docker-compose logs

# Backup manuale urgente
./scripts/backup.sh

# Ripristina da backup
./scripts/manage-backup.sh
```

### Log Importanti

```bash
# Log applicazione
docker-compose logs web

# Log database
docker-compose logs db

# Log Nginx
docker-compose logs nginx

# Log backup
tail -f /var/log/mynutriapp-backup.log

# Log sistema
sudo journalctl -u docker
```

---

## ✅ Risultato Finale

Dopo il deploy completo avrai:

- ✅ Applicazione Flask funzionante
- ✅ Database MySQL 8.0 ottimizzato
- ✅ Redis per rate limiting
- ✅ Nginx come reverse proxy
- ✅ Backup automatico configurato
- ✅ Firewall configurato
- ✅ Monitoring disponibile
- ✅ phpMyAdmin per gestione database (opzionale)

**🎉 MyNutriApp è online e pronto per la produzione!**

---

## 📞 Comandi Rapidi Riepilogo

```bash
# DEPLOY
./deploy.sh

# GESTIONE
./scripts/manage.sh
./scripts/monitoring.sh

# BACKUP
./scripts/backup.sh
./scripts/manage-backup.sh

# AGGIORNAMENTI
./scripts/update.sh app

# DOCKER
docker-compose ps
docker-compose logs -f
docker-compose restart
docker-compose down
docker-compose up -d
```

---

**📚 Per maggiori dettagli tecnici, consulta i file nella cartella `docs/`**
