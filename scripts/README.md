# 📜 Script MyNutriApp

Questa cartella contiene tutti gli script di gestione e manutenzione del progetto.

## 📋 Script Disponibili

### 🚀 Script Principali

- **`backup.sh`** - Backup database MySQL
- **`manage.sh`** - Menu interattivo completo
- **`monitoring.sh`** - Monitoring sistema
- **`security.sh`** - Hardening sicurezza
- **`update.sh`** - Aggiornamenti sistema/app
- **`renew-ssl.sh`** - Gestione certificati SSL (containerizzato)

### 🗄️ Backup

- **`backup.sh`** - Backup manuale database
- **`manage-backup.sh`** - Gestione backup interattiva
- **`setup-backup.sh`** - Configurazione backup automatico

### 📧 Notifiche

- **`notifications.sh`** - Sistema notifiche email

### 🔒 Sicurezza

- **`security.sh`** - Hardening sicurezza

### ⚠️ Deprecati

- **`secure-dashboard.sh`** - Non compatibile con Docker (Nginx containerizzato)
- **`install_dependencies.sh`** - Non necessario (tutto containerizzato)

## 🚀 Come Usare

Tutti gli script possono essere eseguiti dalla root del progetto:

```bash
# Dalla root del progetto
./scripts/backup.sh
./scripts/manage.sh
./scripts/monitoring.sh
```

Gli script si occupano automaticamente di navigare alla root del progetto per eseguire i comandi Docker.

## 📚 Documentazione Completa

Vedi **[docs/SCRIPTS.md](../docs/SCRIPTS.md)** per documentazione dettagliata di ogni script.

## ⚙️ Note Tecniche

- Tutti gli script usano `$(dirname "$0")/..` per trovare la root del progetto
- Gli script sono compatibili con Docker e Docker Compose
- Non richiedono modifiche manuali - tutto è automatizzato
