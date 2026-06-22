# 🥗 MyNutriApp

Applicazione web completa per la gestione di pazienti nutrizionisti, sviluppata con Flask e progettata con approccio mobile-first.

## 🚀 Quick Start - Deploy su VPS (systemd)

### Prerequisiti
- VPS Ubuntu/Debian con accesso SSH
- MySQL 8.0, Redis e Caddy installati sul server
- Dominio (opzionale, per SSL)

### Deploy in produzione

```bash
# 1. Clona e configura
git clone https://github.com/robertolibanora/mynutriapp.git
sudo mkdir -p /opt/mynutriapp
sudo rsync -a --exclude venv --exclude .git ./ /opt/mynutriapp/
sudo cp .env.example /opt/mynutriapp/.env
sudo nano /opt/mynutriapp/.env   # SECRET_KEY, DB_*, REDIS_*, ADMIN_*, etc.

# 2. Database
sudo mysql -u root -p < /opt/mynutriapp/init.sql

# 3. Installazione systemd
sudo chmod +x /opt/mynutriapp/deploy/install-systemd.sh
sudo /opt/mynutriapp/deploy/install-systemd.sh

# 4. Avvia e verifica
sudo systemctl start mynutriapp
sudo systemctl status mynutriapp
curl http://127.0.0.1:8000/health
```

**L'app risponde su `127.0.0.1:8000`**. Caddy (in `deploy/caddy/Caddyfile`) fa da reverse proxy con HTTPS automatico.

---

## 📋 Configurazione .env

Copia `.env.example` in `.env` e configura:

```env
# OBBLIGATORIO
SECRET_KEY=your-secret-key-minimo-64-caratteri
ENCRYPTION_KEY=your-encryption-key
ADMIN_PHONE=+39XXXXXXXXXX
ADMIN_PASSWORD_HASH=your-admin-password-hash

# Database e Redis (servizi nativi sulla VPS)
DB_HOST=127.0.0.1
DB_USER=mynutriapp
DB_PASSWORD=your-secure-password
REDIS_HOST=127.0.0.1
REDIS_PASSWORD=your-redis-password
```

**Genera chiavi necessarie:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('tua_password_admin'))"
```

---

## ⚙️ Comandi systemd

```bash
# Stato servizio
sudo systemctl status mynutriapp

# Log in tempo reale
sudo journalctl -u mynutriapp -f

# Riavvia
sudo systemctl restart mynutriapp

# Ferma / avvia
sudo systemctl stop mynutriapp
sudo systemctl start mynutriapp

# Abilita all'avvio del server
sudo systemctl enable mynutriapp
```

---

## 🌐 Caddy

Modifica il dominio in `deploy/caddy/Caddyfile` prima del deploy:

```caddy
tuodominio.it {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy gestisce **HTTPS automatico** (Let's Encrypt) senza Certbot.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -f
```

---

## 🛠️ Sviluppo locale

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # adatta DB_HOST/REDIS_HOST per il tuo ambiente
python run.py          # http://127.0.0.1:9091
```

---

## 🏗️ Architettura

### Stack tecnologico

- **Backend**: Python 3.13, Flask, Gunicorn
- **Database**: MySQL 8.0
- **Cache / rate limiting**: Redis
- **Web server**: Caddy (reverse proxy + HTTPS automatico)
- **Process manager**: systemd

### Servizi sulla VPS

| Servizio | Unit systemd | Ruolo |
|----------|--------------|-------|
| MyNutriApp | `mynutriapp.service` | App Flask (Gunicorn) |
| MySQL | `mysql.service` | Database |
| Redis | `redis-server.service` | Rate limiting |
| Caddy | `caddy.service` | Reverse proxy + HTTPS + static |

---

## 📱 Funzionalità

### Per amministratori
- Dashboard con statistiche
- Gestione pazienti e appuntamenti
- Diete, allenamenti, fatturazione
- Integrazione WhatsApp

### Per pazienti
- Dashboard personale
- Diete, allenamenti, appuntamenti
- Upload documenti e progressi

---

## 🔒 Sicurezza

- Crittografia dati sanitari (Fernet)
- Audit logging (GDPR Art. 30)
- Session hardening, CSRF, rate limiting (Redis)
- Security headers HTTP
- Validazione upload file

---

## 🗄️ Database

Configurazione produzione in `mysql-production.cnf` (copiabile in `/etc/mysql/conf.d/`).

```bash
mysql -u root -p < init.sql
```

---

## 🆘 Troubleshooting

### Servizio non parte
```bash
sudo journalctl -u mynutriapp -n 50 --no-pager
sudo systemctl status mynutriapp
```

### Database non accessibile
```bash
sudo systemctl status mysql
mysql -u mynutriapp -p -h 127.0.0.1 mynutriapp
```

### Redis non raggiungibile
```bash
sudo systemctl status redis-server
redis-cli -a 'password' ping
```

---

## 📁 Struttura progetto

```
mynutriapp/
├── app/                       # Applicazione Flask
├── deploy/
│   ├── gunicorn.conf.py       # Config Gunicorn
│   ├── install-systemd.sh     # Script install VPS
│   ├── caddy/Caddyfile        # Reverse proxy Caddy (+ HTTPS)
│   └── systemd/mynutriapp.service
├── static/                    # Asset statici
├── templates/                 # Template HTML
├── init.sql                   # Schema database
├── mysql-production.cnf       # Tuning MySQL
├── requirements.txt
├── run.py                     # Dev locale
├── wsgi.py                    # Entry point produzione
└── .env.example
```

---

## ✅ Checklist deploy

- [ ] VPS accessibile via SSH
- [ ] App in `/opt/mynutriapp` con `.env` configurato
- [ ] MySQL e Redis attivi (`systemctl status mysql redis-server`)
- [ ] `init.sql` importato
- [ ] `mynutriapp.service` enabled e running
- [ ] Caddy configurato (dominio in `deploy/caddy/Caddyfile`) e `curl /health` OK

---

## 👨‍💻 Autore

**Roberto Libanora** — [GitHub](https://github.com/robertolibanora)
