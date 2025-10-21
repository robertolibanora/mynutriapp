# 📁 Struttura del Progetto NutriApp

## 🏗️ Architettura

```
nutriapp/
├── 📁 app/                          # Applicazione principale
│   ├── 📁 models/                   # Modelli database
│   │   ├── __init__.py
│   │   └── models.py                # Tutti i modelli SQLAlchemy
│   ├── 📁 routes/                   # Route Flask (Blueprint)
│   │   ├── __init__.py              # Registrazione blueprint
│   │   ├── auth.py                  # Autenticazione
│   │   ├── dashboard.py             # Dashboard admin/user
│   │   ├── patients.py              # Gestione pazienti
│   │   ├── appuntamenti.py          # Gestione appuntamenti
│   │   ├── agenda.py                # Agenda unificata
│   │   ├── diete.py                 # Gestione diete
│   │   ├── allenamenti.py           # Gestione allenamenti
│   │   ├── progressi.py             # Gestione progressi
│   │   ├── documenti.py             # Gestione documenti
│   │   ├── listino.py               # Gestione listino
│   │   ├── vendite.py               # Gestione vendite
│   │   ├── slot.py                  # Gestione slot disponibilità
│   │   └── 📁 whatsapp/             # Modulo WhatsApp
│   │       ├── __init__.py
│   │       ├── broadcast.py         # Broadcast messaggi
│   │       ├── broadcast_routes.py  # Route broadcast
│   │       ├── gestione.py          # Gestione messaggi
│   │       ├── run_scadenze.py      # Script scadenze
│   │       ├── scadenze.py          # Logica scadenze
│   │       ├── sender.py            # Invio messaggi
│   │       └── triggers.py          # Trigger automatici
│   ├── 📁 services/                 # Logica business
│   │   ├── __init__.py
│   │   └── whatsapp_service.py      # Servizio WhatsApp
│   ├── 📁 utils/                    # Utility e helper
│   │   ├── __init__.py
│   │   └── helpers.py               # Funzioni helper comuni
│   └── 📁 config/                   # Configurazioni
│       ├── __init__.py
│       ├── config.py                # Configurazione principale
│       └── whatsapp_trigger_templates.json
├── 📁 templates/                    # Template HTML
│   ├── 📁 admin/                    # Template admin
│   ├── 📁 user/                     # Template utenti
│   ├── 📁 public/                   # Template pubblici
│   ├── 📁 errors/                   # Template errori
│   ├── base_admin.html
│   ├── base_user.html
│   └── login.html
├── 📁 static/                       # File statici
│   ├── 📁 css/                      # Fogli di stile
│   ├── 📁 js/                       # JavaScript
│   ├── 📁 images/                   # Immagini
│   ├── 📁 icons/                    # Icone
│   └── 📁 uploads/                  # File caricati
├── 📁 docs/                         # Documentazione
│   ├── STRUTTURA_PROGETTO.md
│   └── WHATSAPP_DOCUMENTATION.md
├── 📁 scripts/                      # Script di utilità
├── 📁 tests/                        # Test (futuro)
├── 📁 venv/                         # Virtual environment
├── 📄 app.py                        # Entry point principale
├── 📄 requirements.txt              # Dipendenze Python
└── 📄 README.md                     # Documentazione principale
```

## 🔧 Componenti Principali

### 📱 **App** (`app/`)
- **Models**: Modelli del database SQLAlchemy
- **Routes**: Blueprint Flask per tutte le route
- **Services**: Logica business e servizi
- **Utils**: Funzioni helper e utility
- **Config**: Configurazioni dell'applicazione

### 🎨 **Templates** (`templates/`)
- Template HTML organizzati per ruolo (admin/user/public)
- Template base per layout comuni
- Template per gestione errori

### 🎨 **Static** (`static/`)
- CSS, JavaScript, immagini e file statici
- Directory uploads per file caricati dagli utenti

### 📚 **Documentation** (`docs/`)
- Documentazione del progetto
- Guide per sviluppatori

## 🚀 **Avvio dell'Applicazione**

```bash
# Attiva virtual environment
source venv/bin/activate

# Avvia l'applicazione
python app.py
```

## 📦 **Dipendenze**

Le dipendenze sono gestite tramite `requirements.txt` e installate nel virtual environment `venv/`.

## 🔄 **Flusso di Lavoro**

1. **Entry Point**: `app.py` inizializza Flask e registra i blueprint
2. **Configurazione**: `app/config/config.py` gestisce tutte le configurazioni
3. **Modelli**: `app/models/models.py` definisce la struttura del database
4. **Route**: `app/routes/` contiene tutti i blueprint per le diverse funzionalità
5. **Servizi**: `app/services/` contiene la logica business
6. **Utility**: `app/utils/` contiene funzioni helper comuni

## 🎯 **Vantaggi della Nuova Struttura**

- ✅ **Separazione delle responsabilità**
- ✅ **Codice più mantenibile**
- ✅ **Facilità di testing**
- ✅ **Scalabilità migliorata**
- ✅ **Organizzazione professionale**
- ✅ **Import più chiari e gestibili**
