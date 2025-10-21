# 🚀 MyNutriAPP - Guida al Deployment

## 📋 Processo di Deployment Completo

### **1. Preparazione Server Ubuntu**
```bash
# Aggiorna il sistema
sudo apt update && sudo apt upgrade -y

# Installa dipendenze base
sudo apt install git curl -y
```

### **2. Clona il Progetto**
```bash
# Clona il repository
git clone https://github.com/robertolibanora/mynutriapp.git
cd mynutriapp

# Verifica i file
ls -la
```

### **3. Configura .env**
```bash
# Modifica il file .env
nano .env
```

**Configurazioni importanti:**
- `MYSQL_ROOT_PASSWORD` - Password per root MySQL
- `MYSQL_PASSWORD` - Password per utente mynutriapp
- `SECRET_KEY` - Chiave segreta Flask
- `ADMIN_PHONE` - Il tuo numero di telefono
- `ADMIN_PASSWORD` - Password per l'admin

### **4. Lancia il Deployment**
```bash
# Rendi eseguibile lo script
chmod +x deploy.sh

# Lancia il deployment completo
./deploy.sh
```

## 🎯 **Cosa Succede Automaticamente**

1. ✅ **Installa Docker** e Docker Compose
2. ✅ **Installa Nginx** e Certbot
3. ✅ **Avvia i container:**
   - `mynutriapp_web` - Applicazione Flask
   - `mynutriapp_db` - Database MySQL
   - `mynutriapp_redis` - Redis per rate limiting
   - `mynutriapp_phpmyadmin` - Gestione database
4. ✅ **Configura Nginx** come reverse proxy
5. ✅ **Chiede se configurare SSL** (Let's Encrypt)
6. ✅ **Configura il firewall**

## 🌐 **Servizi Disponibili**

- **App principale**: `http://your-domain.com` (o IP del server)
- **phpMyAdmin**: `http://your-domain.com:8080`
- **MySQL**: `localhost:3306`
- **Redis**: `localhost:6379`

## 🔧 **Comandi Utili**

```bash
# Vedi i log
docker-compose logs -f

# Riavvia tutto
docker-compose restart

# Ferma tutto
docker-compose down

# Avvia tutto
docker-compose up -d

# Entra nel container
docker-compose exec web bash

# Backup database
docker-compose exec db mysqldump -u root -p mynutriapp > backup.sql
```

## 🗄️ **Sistema Backup Automatico**

### **Backup Giornaliero:**
- ✅ **Automatico**: Ogni giorno alle 2:00
- ✅ **Directory**: `/var/backups/mynutriapp/`
- ✅ **Compresso**: File .gz per risparmiare spazio
- ✅ **Rotazione**: Mantiene solo 7 giorni
- ✅ **Log**: `/var/log/mynutriapp-backup.log`

### **Gestione Backup:**
```bash
# Backup manuale
/usr/local/bin/mynutriapp-backup

# Gestione completa backup
./manage-backup.sh

# Vedi backup disponibili
ls -la /var/backups/mynutriapp/

# Vedi log backup
tail -f /var/log/mynutriapp-backup.log
```

### **Ripristino Backup:**
```bash
# Lista backup
./manage-backup.sh

# Ripristina backup specifico
docker-compose exec -T db mysql -u root -p mynutriapp < /var/backups/mynutriapp/mynutriapp_backup_YYYYMMDD_HHMMSS.sql.gz
```

## 🛡️ **Sicurezza**

- ✅ **Database persistente** - I dati non si perdono
- ✅ **SSL automatico** - Certificato Let's Encrypt
- ✅ **Firewall configurato** - Solo porte necessarie aperte
- ✅ **Rate limiting** - Protezione da attacchi
- ✅ **Utente non-root** - Sicurezza container

## 🎪 **Risultato Finale**

**MyNutriAPP sarà online e accessibile da tutto il mondo!** 🌍✨

- App Flask funzionante
- Database MySQL persistente
- Redis per performance
- Nginx come reverse proxy
- SSL per sicurezza
- phpMyAdmin per gestione database
