# MyNutriAPP 🥗

Un'applicazione web completa per la gestione di pazienti nutrizionisti, sviluppata con Flask e progettata con un approccio mobile-first.

## 🚀 Caratteristiche Principali

- **Gestione Pazienti**: Sistema completo per la gestione dei pazienti con profili dettagliati
- **Agenda Unificata**: Sistema di appuntamenti e slot temporali
- **Piani Nutrizionali**: Creazione e gestione di diete personalizzate
- **Allenamenti**: Schede di allenamento per i pazienti
- **Documenti**: Gestione documenti e progressi
- **Sistema Economico**: Tracking delle vendite e fatturazione
- **Integrazione WhatsApp**: Notifiche automatiche e broadcast
- **Design Mobile-First**: Interfaccia ottimizzata per dispositivi mobili

## 🛠️ Tecnologie Utilizzate

- **Backend**: Python 3.13, Flask
- **Database**: SQLite (sviluppo), PostgreSQL (produzione)
- **Frontend**: HTML5, CSS3, JavaScript
- **Integrazioni**: WhatsApp Business API
- **Deployment**: Configurazione per produzione

## 📱 Design System

L'applicazione segue un design system coerente con:
- **Colori**: Background #000000, grigio base #1a1a1a, testo bianco #ffffff, accento fluo #ff0040
- **Approccio**: Mobile-first con UI/UX ottimizzata per dispositivi mobili
- **Componenti**: Sistema di componenti riutilizzabili per navbar, card, bottoni e icone
- **Animazioni**: Animazioni minimali (hover/click) per una migliore UX

## 🚀 Installazione

### Prerequisiti
- Python 3.13
- pip (gestore pacchetti Python)

### Setup Locale

1. **Clona il repository**
   ```bash
   git clone https://github.com/robertolibanora/mynutriapp.git
   cd mynutriapp
   ```

2. **Crea un ambiente virtuale**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Su Windows: venv\Scripts\activate
   ```

3. **Installa le dipendenze**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configura le variabili d'ambiente**
   ```bash
   cp .env.example .env
   # Modifica il file .env con le tue configurazioni
   ```

5. **Inizializza il database**
   ```bash
   flask init-db
   ```

6. **Avvia l'applicazione**
   ```bash
   python app.py
   ```

L'applicazione sarà disponibile su `http://localhost:5000`

## 📁 Struttura del Progetto

```
nutriapp/
├── app.py                 # File principale dell'applicazione
├── config.py             # Configurazioni
├── models.py             # Modelli del database
├── requirements.txt      # Dipendenze Python
├── routes/               # Route dell'applicazione
│   ├── auth.py          # Autenticazione
│   ├── patients.py      # Gestione pazienti
│   ├── agenda.py        # Sistema agenda
│   ├── diete.py         # Gestione diete
│   ├── allenamenti.py   # Gestione allenamenti
│   └── whatsapp/        # Integrazione WhatsApp
├── static/              # File statici (CSS, JS, immagini)
├── templates/           # Template HTML
│   ├── admin/          # Template per admin
│   ├── user/           # Template per utenti
│   └── public/         # Template pubblici
└── venv/               # Ambiente virtuale
```

## 🔧 Configurazione

### Variabili d'Ambiente

Crea un file `.env` nella root del progetto con le seguenti variabili:

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///nutriapp.db
WHATSAPP_TOKEN=your-whatsapp-token
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id
```

### Database

L'applicazione supporta sia SQLite (sviluppo) che PostgreSQL (produzione). Per inizializzare il database:

```bash
flask init-db
```

## 📱 Funzionalità

### Per Amministratori
- Dashboard completa con statistiche
- Gestione pazienti e appuntamenti
- Creazione diete e allenamenti
- Sistema economico e fatturazione
- Configurazione WhatsApp e broadcast

### Per Utenti/Pazienti
- Dashboard personale
- Visualizzazione diete e allenamenti
- Prenotazione appuntamenti
- Upload documenti e progressi
- Accesso al listino prezzi

## 🔗 Integrazione WhatsApp

L'applicazione include un sistema completo di integrazione WhatsApp per:
- Notifiche automatiche
- Broadcast personalizzati
- Gestione scadenze
- Invio documenti

## 🚀 Deployment

### Produzione

1. **Configura le variabili d'ambiente per la produzione**
2. **Installa le dipendenze di produzione**
3. **Configura il database PostgreSQL**
4. **Avvia l'applicazione con un server WSGI**

## 🤝 Contribuire

1. Fork del progetto
2. Crea un branch per la tua feature (`git checkout -b feature/AmazingFeature`)
3. Commit delle modifiche (`git commit -m 'Add some AmazingFeature'`)
4. Push al branch (`git push origin feature/AmazingFeature`)
5. Apri una Pull Request

## 📄 Licenza

Questo progetto è sotto licenza MIT. Vedi il file `LICENSE` per maggiori dettagli.

## 👨‍💻 Autore

**Roberto Libanora**
- GitHub: [@robertolibanora](https://github.com/robertolibanora)

## 📞 Supporto

Per supporto o domande, contatta:
- Email: [inserire email]
- WhatsApp: [inserire numero]

---

⭐ Se questo progetto ti è utile, considera di dargli una stella su GitHub!
