# 🥗 MyNutriApp

Applicazione web completa per la gestione di pazienti nutrizionisti, sviluppata con Flask e progettata con approccio mobile-first.

## 🚀 Quick Start - Deploy su VPS

### Prerequisiti
- VPS Hostinger con Ubuntu/Debian
- Accesso SSH
- Dominio (opzionale per SSL)

### Deploy in 3 Passi

```bash
# 1. Clona e configura
git clone https://github.com/robertolibanora/mynutriapp.git
cd mynutriapp
nano .env  # Configura SECRET_KEY, MYSQL_ROOT_PASSWORD, MYSQL_PASSWORD, etc.

# 2. Deploy automatico
chmod +x deploy.sh
./deploy.sh

# 3. Verifica
docker-compose ps
```

**🎉 Fatto! L'app è online su `http://your-vps-ip`**

---

## 📋 Configurazione .env

Crea il file `.env` nella root con:

```env
# OBBLIGATORIO
SECRET_KEY=your-secret-key-minimo-64-caratteri
MYSQL_ROOT_PASSWORD=your-secure-root-password
MYSQL_PASSWORD=your-secure-app-password
ADMIN_PHONE=+39XXXXXXXXXX
ADMIN_PASSWORD_HASH=your-admin-password-hash
ENCRYPTION_KEY=your-encryption-key

# OPZIONALE - MySQL ottimizzazioni
MYSQL_INNODB_BUFFER_POOL_SIZE=1G
MYSQL_MAX_CONNECTIONS=200

# OPZIONALE - Altri servizi
WHATSAPP_ACCESS_TOKEN=your-token
WHATSAPP_PHONE_NUMBER_ID=your-phone-id
```

**Genera chiavi necessarie:**
```bash
# SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# ENCRYPTION_KEY (crittografia dati sensibili)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ADMIN_PASSWORD_HASH (hash password admin)
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('tua_password_admin'))"
```

---

## 🛠️ Script Disponibili

Tutti gli script sono nella cartella `scripts/`:

| Script | Comando | Descrizione |
|--------|---------|-------------|
| **Deploy** | `./deploy.sh` | Deploy completo automatico |
| **Backup** | `./scripts/backup.sh` | Backup database manuale |
| **Gestione** | `./scripts/manage.sh` | Menu interattivo completo |
| **Monitoring** | `./scripts/monitoring.sh` | Verifica stato sistema |
| **Sicurezza** | `./scripts/security.sh` | Hardening sicurezza |
| **Aggiornamenti** | `./scripts/update.sh app` | Aggiorna applicazione |
| **Backup Management** | `./scripts/manage-backup.sh` | Gestione backup interattiva |

### Comandi Rapidi

```bash
# Deploy
./deploy.sh

# Gestione (menu interattivo)
./scripts/manage.sh

# Backup manuale
./scripts/backup.sh

# Monitoring
./scripts/monitoring.sh

# Aggiorna app
./scripts/update.sh app
```

---

## 🐳 Docker Commands

```bash
# Stato container
docker-compose ps

# Log in tempo reale
docker-compose logs -f

# Riavvia tutto
docker-compose restart

# Ferma tutto
docker-compose down

# Avvia tutto
docker-compose up -d

# Rebuild e avvia
docker-compose up -d --build
```

---

## 📚 Documentazione

- **[deploy.md](deploy.md)** - ⭐ **Guida completa deploy VPS** - Tutto quello che serve per deploy su Hostinger
  - Deploy passo-passo
  - Configurazione completa
  - Tutti gli script spiegati
  - Troubleshooting completo
  - MySQL produzione
  - SSL e sicurezza

---

## 🏗️ Architettura

### Stack Tecnologico

- **Backend**: Python 3.13, Flask, Gunicorn
- **Database**: MySQL 8.0 (produzione)
- **Cache/Rate Limiting**: Redis 7
- **Web Server**: Nginx (reverse proxy)
- **Containerizzazione**: Docker & Docker Compose

### Servizi Containerizzati

- `mynutriapp_web` - Applicazione Flask (Gunicorn)
- `mynutriapp_nginx` - Nginx reverse proxy
- `mynutriapp_db` - MySQL 8.0
- `mynutriapp_redis` - Redis
- `mynutriapp_phpmyadmin` - phpMyAdmin (opzionale)

---

## 📱 Funzionalità

### Per Amministratori
- Dashboard completa con statistiche
- Gestione pazienti e appuntamenti
- Creazione diete e allenamenti
- Sistema economico e fatturazione
- Integrazione WhatsApp e broadcast

### Per Utenti/Pazienti
- Dashboard personale
- Visualizzazione diete e allenamenti
- Prenotazione appuntamenti
- Upload documenti e progressi
- Accesso al listino prezzi

---

## 🔒 Sicurezza

- ✅ Crittografia dati sanitari sensibili (Fernet)
- ✅ Audit logging completo (GDPR Art. 30)
- ✅ Session hardening (2h timeout, regeneration)
- ✅ Security headers HTTP (HSTS, CSP, X-Frame, etc.)
- ✅ Rate limiting (Redis)
- ✅ CSRF protection
- ✅ Password hashing (PBKDF2)
- ✅ File upload validation (dimensione + MIME type)
- ✅ Firewall configurato
- ✅ Backup automatico giornaliero

---

## 🗄️ Database

### MySQL 8.0 in Produzione

- ✅ Configurazione ottimizzata (`mysql-production.cnf`)
- ✅ UTF8MB4 per Unicode completo
- ✅ Binary logging per backup incrementali
- ✅ Slow query log per ottimizzazione
- ✅ Performance tuning applicato

**Vedi [docs/MYSQL.md](docs/MYSQL.md) per dettagli.**

---

## 🔄 Backup

### Backup Automatico

- ✅ Eseguito ogni giorno alle 2:00
- ✅ Salvato in `/var/backups/mynutriapp/`
- ✅ Compresso (.gz)
- ✅ Mantiene ultimi 7 giorni

### Backup Manuale

```bash
./scripts/backup.sh
# oppure
/usr/local/bin/mynutriapp-backup
```

### Gestione Backup

```bash
./scripts/manage-backup.sh
```

---

## 🆘 Troubleshooting

### Container non si avvia
```bash
docker-compose logs [nome-container]
docker-compose ps
```

### Database non accessibile
```bash
docker-compose exec db mysql -u root -p
docker-compose logs db
```

### Problemi con .env
```bash
# Verifica che .env esista
ls -la .env

# Verifica variabili essenziali
grep -E "SECRET_KEY|ENCRYPTION_KEY|ADMIN_PASSWORD_HASH|MYSQL_PASSWORD" .env
```

---

## 📁 Struttura Progetto

```
mynutriapp/
├── app/                    # Applicazione Flask
│   ├── models/            # Modelli database
│   ├── routes/            # Route applicazione
│   ├── config/            # Configurazioni
│   └── services/          # Servizi (WhatsApp, etc.)
├── scripts/               # Script di gestione
│   ├── backup.sh         # Backup database
│   ├── manage.sh         # Menu interattivo
│   ├── monitoring.sh      # Monitoring sistema
│   ├── security.sh       # Hardening sicurezza
│   ├── update.sh         # Aggiornamenti
│   └── ...               # Altri script
├── docs/                  # Documentazione completa
│   ├── DEPLOY.md         # Guida deploy
│   ├── MYSQL.md          # Config MySQL
│   ├── SCRIPTS.md        # Documentazione script
│   └── FLUSSO.md         # Dettagli tecnici
├── templates/             # Template HTML
├── static/                # File statici (CSS, JS, immagini)
├── deploy.sh              # Script deploy principale (root)
├── docker-compose.yml     # Configurazione Docker
├── Dockerfile             # Immagine Docker Flask
├── init.sql               # Inizializzazione database
├── mysql-production.cnf   # Config MySQL produzione
├── nginx.conf             # Config Nginx
├── nginx-rate-limit.conf  # Rate limiting Nginx
└── README.md              # Questo file
```

---

## ✅ Checklist Deploy

- [ ] VPS accessibile via SSH
- [ ] Repository clonato
- [ ] File `.env` configurato con tutte le variabili obbligatorie:
  - [ ] `SECRET_KEY`
  - [ ] `ENCRYPTION_KEY` (genera con script sopra)
  - [ ] `ADMIN_PASSWORD_HASH` (genera con script sopra)
  - [ ] `ADMIN_PHONE`
  - [ ] `MYSQL_ROOT_PASSWORD` e `MYSQL_PASSWORD`
- [ ] `docker-compose build` eseguito
- [ ] `docker-compose up -d` eseguito
- [ ] Tutti i container sono "Up" e MySQL è "(healthy)"
- [ ] Applicazione accessibile su `http://your-vps-ip`
- [ ] Tabella `audit_log` creata nel database
- [ ] Backup automatico configurato

---

## 📞 Supporto

Per problemi:
1. Controlla i log: `docker-compose logs`
2. Verifica stato: `docker-compose ps`
3. Consulta documentazione in `docs/`

---

## 👨‍💻 Autore

**Roberto Libanora**
- GitHub: [@robertolibanora](https://github.com/robertolibanora)

---

⭐ Se questo progetto ti è utile, considera di dargli una stella su GitHub!
