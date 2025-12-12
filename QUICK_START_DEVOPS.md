# 🚀 QUICK START - DevOps MyNutriApp

## ⚡ Setup Rapido (5 minuti)

### 1. Health Check Manuale
```bash
cd /var/www/mynutriapp
bash scripts/health-check.sh
```

### 2. Configura Backup Automatico
```bash
# Crea directory backup (richiede sudo la prima volta)
sudo mkdir -p /var/backups/mynutriapp
sudo chown $USER:$USER /var/backups/mynutriapp

# Configura cron backup
cd /var/www/mynutriapp
bash scripts/setup-backup.sh
```

### 3. Configura Monitoring Automatico
```bash
cd /var/www/mynutriapp
bash scripts/setup-monitoring.sh
```

### 4. Verifica Configurazione
```bash
# Verifica cron job
crontab -l

# Dovresti vedere:
# - Backup alle 2:00
# - Health check ogni ora
```

---

## 📋 Checklist Quotidiana (2 minuti)

```bash
# 1. Health check rapido
cd /var/www/mynutriapp && bash scripts/health-check.sh

# 2. Verifica container
docker compose ps

# 3. Verifica spazio disco
df -h | head -2

# 4. Verifica backup di ieri
ls -lh /var/backups/mynutriapp/ | tail -3
```

---

## 🆘 Comandi di Emergenza

### App non risponde
```bash
cd /var/www/mynutriapp
docker compose restart web
docker compose logs web --tail 50
```

### Database non risponde
```bash
docker compose restart db
docker compose logs db --tail 50
```

### Spazio disco pieno
```bash
# Pulisci backup vecchi (>30 giorni)
find /var/backups/mynutriapp -name "*.sql" -mtime +30 -delete

# Pulisci Docker
docker system prune -a --volumes
```

### Ripristino da backup
```bash
cd /var/www/mynutriapp
bash scripts/manage-backup.sh
# Scegli opzione 3 (Ripristina backup)
```

---

## 📊 Monitoraggio Risorse

```bash
# Statistiche container
docker stats --no-stream

# Uso disco
df -h

# Memoria
free -h

# Log errori recenti
docker compose logs web --since 1h | grep -i error
```

---

## ✅ Verifica Stato Completo

```bash
cd /var/www/mynutriapp
bash scripts/health-check.sh
```

**Cosa controlla:**
- ✅ Container attivi
- ✅ Database funzionante
- ✅ Redis funzionante
- ✅ Spazio disco
- ✅ Memoria
- ✅ Errori nei log
- ✅ Backup recenti
- ✅ Certificati SSL
- ✅ Endpoint pubblici

---

## 📚 Documentazione Completa

- **Checklist Produzione**: `PRODUCTION_CHECKLIST.md`
- **Script disponibili**: `scripts/README.md`
- **Deploy**: `deploy.md`

---

**Ultimo aggiornamento**: 2025-12-11
