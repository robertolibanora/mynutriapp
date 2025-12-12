# 🛡️ CHECKLIST PRODUZIONE - MyNutriApp

## 📋 Checklist per Junior DevOps

### ✅ **MONITORAGGIO QUOTIDIANO** (5 minuti al giorno)

#### Mattina (prima di iniziare)
- [ ] Esegui health check: `./scripts/health-check.sh`
- [ ] Verifica log errori: `docker compose logs web --tail 50 | grep -i error`
- [ ] Controlla spazio disco: `df -h`
- [ ] Verifica che tutti i container siano attivi: `docker compose ps`

#### Sera (prima di finire)
- [ ] Verifica backup giornaliero: `ls -lh /var/backups/mynutriapp/ | tail -5`
- [ ] Controlla metriche del giorno: `docker stats --no-stream`

---

### 📅 **MONITORAGGIO SETTIMANALE** (15 minuti)

- [ ] Verifica backup settimanali (almeno 7 backup)
- [ ] Controlla spazio backup: `du -sh /var/backups/mynutriapp/`
- [ ] Verifica log di sistema: `journalctl -u docker --since "7 days ago" | tail -50`
- [ ] Controlla aggiornamenti sicurezza: `apt list --upgradable`
- [ ] Verifica certificati SSL: `echo | openssl s_client -servername mynutriapp.cloud -connect mynutriapp.cloud:443 2>&1 | openssl x509 -noout -dates`

---

### 🚨 **ALERTING E NOTIFICHE**

#### Cosa monitorare automaticamente:
1. **Container down** → Alert immediato
2. **Spazio disco > 85%** → Alert warning
3. **Spazio disco > 95%** → Alert critico
4. **Backup fallito** → Alert critico
5. **Errori 500 frequenti** → Alert warning
6. **Certificato SSL in scadenza** → Alert 30 giorni prima

#### Setup alerting (da implementare):
```bash
# Aggiungi a crontab per check ogni ora
0 * * * * cd /var/www/mynutriapp && ./scripts/health-check.sh | mail -s "MyNutriApp Health Check" admin@example.com
```

---

### 💾 **BACKUP**

#### Backup automatico
- ✅ Configurato: Backup giornaliero alle 2:00 AM
- ✅ Script: `/usr/local/bin/mynutriapp-backup`
- ✅ Directory: `/var/backups/mynutriapp/`

#### Verifica backup:
```bash
# Lista backup
ls -lh /var/backups/mynutriapp/

# Test ripristino (su ambiente di test)
./scripts/manage-backup.sh
# Scegli opzione 3 (Ripristina backup)
```

#### Best practices backup:
- [ ] Mantieni almeno 7 backup giornalieri
- [ ] Mantieni almeno 4 backup settimanali
- [ ] Mantieni almeno 12 backup mensili
- [ ] Testa ripristino backup almeno 1 volta al mese
- [ ] Backup off-site (cloud storage) almeno settimanale

---

### 🔒 **SICUREZZA**

#### Checklist sicurezza:
- [ ] Password forti in `.env` (non committate su git)
- [ ] `.env` con permessi 600: `chmod 600 .env`
- [ ] Firewall configurato (solo porte necessarie aperte)
- [ ] SSH con chiavi, non password
- [ ] Rate limiting attivo (verifica in `.env`)
- [ ] CSRF protection attiva
- [ ] Certificati SSL validi e auto-rinnovati (Caddy)
- [ ] Container non eseguiti come root
- [ ] Log non contengono password/sensibili

#### Verifica sicurezza:
```bash
# Verifica permessi file sensibili
ls -la .env

# Verifica container non root
docker compose exec web whoami  # Dovrebbe essere "app"

# Verifica firewall
sudo ufw status
```

---

### 📊 **MONITORAGGIO RISORSE**

#### Metriche da monitorare:
- **CPU**: < 80% normale, > 90% warning
- **Memoria**: < 85% normale, > 90% warning
- **Disco**: < 80% normale, > 90% warning
- **Rete**: Monitora traffico anomalo

#### Comandi utili:
```bash
# Statistiche container in tempo reale
docker stats

# Uso disco per volume
docker system df -v

# Log con limitazione
docker compose logs --tail 100 -f web
```

---

### 🔄 **AGGIORNAMENTI**

#### Processo aggiornamento sicuro:
1. [ ] Backup completo prima di aggiornare
2. [ ] Test su ambiente di staging (se disponibile)
3. [ ] Aggiorna codice: `git pull`
4. [ ] Rebuild container: `docker compose build --no-cache web`
5. [ ] Test locale prima di deployare
6. [ ] Deploy: `docker compose up -d web`
7. [ ] Verifica funzionamento: `./scripts/health-check.sh`
8. [ ] Monitora log per 10-15 minuti dopo deploy

#### Rollback rapido:
```bash
# Se qualcosa va storto dopo aggiornamento
git checkout <commit-precedente>
docker compose build --no-cache web
docker compose up -d web
```

---

### 📝 **LOGGING**

#### Cosa loggare:
- ✅ Errori applicazione (già configurato)
- ✅ Accessi admin (già configurato)
- ✅ Backup (già configurato in `/var/log/mynutriapp-backup.log`)
- ⚠️ Da aggiungere: Log rotazione automatica

#### Rotazione log:
```bash
# Aggiungi a /etc/logrotate.d/mynutriapp
/var/www/mynutriapp/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 app app
}
```

---

### 🧪 **TEST DI DISASTER RECOVERY**

#### Test mensile:
1. [ ] Simula crash container: `docker compose stop web`
2. [ ] Verifica riavvio automatico: `docker compose ps`
3. [ ] Test ripristino backup su ambiente di test
4. [ ] Verifica che alerting funzioni

---

### 📈 **METRICHE CHIAVE DA TRACCIARE**

#### Performance:
- Tempo di risposta pagine (< 500ms normale)
- Errori 500 (< 0.1% delle richieste)
- Uptime (> 99.5%)

#### Business:
- Numero utenti attivi
- Numero vendite/transazioni
- Spazio storage utilizzato

---

### 🆘 **PROCEDURE DI EMERGENZA**

#### App non risponde:
1. Verifica container: `docker compose ps`
2. Controlla log: `docker compose logs web --tail 100`
3. Riavvia se necessario: `docker compose restart web`
4. Se non risolve: `docker compose down && docker compose up -d`

#### Database corrotto:
1. Ferma app: `docker compose stop web`
2. Ripristina backup: `./scripts/manage-backup.sh` → opzione 3
3. Riavvia: `docker compose start web`

#### Disco pieno:
1. Pulisci backup vecchi: `./scripts/manage-backup.sh` → opzione 4
2. Pulisci immagini Docker: `docker system prune -a`
3. Pulisci log vecchi: `find /var/www/mynutriapp/logs -name "*.log" -mtime +14 -delete`

---

### 📞 **CONTATTI E DOCUMENTAZIONE**

- **Repository**: https://github.com/robertolibanora/mynutriapp
- **Documentazione deploy**: `deploy.md`
- **Script disponibili**: `scripts/README.md`

---

### ✅ **CHECKLIST SETUP INIZIALE**

Se è la prima volta che gestisci questa app:

- [ ] Leggi `README.md` e `deploy.md`
- [ ] Verifica che backup automatico sia configurato: `crontab -l | grep backup`
- [ ] Testa health check: `./scripts/health-check.sh`
- [ ] Verifica accesso SSH e chiavi
- [ ] Configura notifiche email in `.env`
- [ ] Testa ripristino backup su ambiente di test
- [ ] Documenta password/credenziali in password manager sicuro
- [ ] Crea runbook per procedure comuni

---

## 🎯 **PRIORITÀ OPERATIVE**

### 🔴 **CRITICO** (controlla subito se succede):
- Container down
- Database non accessibile
- Backup fallito per 2+ giorni
- Spazio disco > 95%
- Certificato SSL scaduto

### 🟡 **IMPORTANTE** (controlla entro 24h):
- Errori frequenti nei log
- Performance degradata
- Spazio disco > 85%
- Backup non eseguito oggi

### 🟢 **ROUTINE** (controlla settimanalmente):
- Aggiornamenti sicurezza
- Pulizia log vecchi
- Verifica metriche performance
- Review configurazioni

---

**Ultimo aggiornamento**: 2025-12-11
**Versione**: 1.0
