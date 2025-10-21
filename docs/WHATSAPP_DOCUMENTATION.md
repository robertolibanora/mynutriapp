# 📱 Sistema WhatsApp per nutriapp

## 🎯 Panoramica

Sistema WhatsApp semplificato per nutriapp che gestisce:
- **Trigger automatici** per eventi specifici
- **Invio messaggi personalizzati** a tutti i pazienti
- **Gestione scadenze** con notifiche automatiche

## 🚀 Funzionalità Principali

### ✅ **Trigger Automatici**
- **📅 Appuntamenti**: Invio automatico per conferma/annullamento
- **🍽️ Diete**: Invio automatico per nuove diete caricate
- **💪 Allenamenti**: Invio automatico per nuovi allenamenti caricati
- **⏰ Scadenze**: Invio automatico per scadenze (10 giorni prima)

### ✅ **Invio Messaggi Personalizzati**
- **Form semplice** per scrivere messaggi
- **Variabili personalizzate** ({nome}, {cognome}, {eta}, etc.)
- **Anteprima messaggio** in tempo reale
- **Invio a tutti i pazienti** con telefono

## 📁 Struttura File

```
routes/whatsapp/
├── __init__.py              # Modulo principale (esporta funzioni)
├── sender.py                # Invio messaggi diretti via Meta API
├── triggers.py              # Gestione trigger automatici
├── scadenze.py              # Controllo scadenze automatiche
├── run_scadenze.py          # Script esecuzione scadenze
├── gestione.py              # CLI per gestione trigger
├── broadcast.py             # Sistema broadcast semplificato
├── broadcast_routes.py      # Routes web per interfaccia
└── templates/admin/         # Template HTML
    ├── broadcast_dashboard.html  # Dashboard con gestione trigger
    └── broadcast_nuovo.html      # Form invio messaggio
```

## 🔧 Configurazione

### **1. Variabili d'Ambiente**

Aggiungi al file `.env`:

```bash
# WhatsApp Business API
WHATSAPP_ACCESS_TOKEN=your_access_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
```

### **2. Installazione Dipendenze**

```bash
pip install requests
```

### **3. Registrazione Blueprint**

Il blueprint è già registrato in `routes/__init__.py`:

```python
from routes.whatsapp.broadcast_routes import broadcast_bp
app.register_blueprint(broadcast_bp)
```

## 🎮 Utilizzo

### **Interfaccia Web**

1. **Accedi come admin** al sistema
2. **Vai su Admin → 📱 WhatsApp**
3. **Gestisci i trigger** (abilita/disabilita)
4. **Clicca "Invia Messaggio"** per inviare messaggi personalizzati

### **Gestione Trigger**

#### **Via Interfaccia Web**
- Vai su **Admin → 📱 WhatsApp**
- Usa i **pulsanti toggle** per abilitare/disabilitare i trigger
- I trigger si aggiornano immediatamente

#### **Via CLI**
```bash
# Mostra stato trigger
python routes/whatsapp/gestione.py status

# Abilita trigger specifico
python routes/whatsapp/gestione.py enable appuntamenti

# Disabilita trigger specifico
python routes/whatsapp/gestione.py disable scadenze

# Abilita tutti i trigger
python routes/whatsapp/gestione.py enable-all

# Disabilita tutti i trigger
python routes/whatsapp/gestione.py disable-all
```

### **Invio Messaggi Personalizzati**

1. **Vai su Admin → 📱 WhatsApp**
2. **Clicca "Invia Messaggio"**
3. **Scrivi il messaggio** con variabili personalizzate
4. **Usa "Anteprima"** per vedere il risultato
5. **Clicca "Invia a Tutti"**

### **Controllo Scadenze**

#### **Esecuzione Manuale**
```bash
# Controllo scadenze standard (10 giorni)
python routes/whatsapp/run_scadenze.py

# Controllo scadenze multiple (1, 3, 7, 10 giorni)
python routes/whatsapp/run_scadenze.py --multiple
```

#### **Esecuzione Automatica (Cron)**
```bash
# Aggiungi al crontab per esecuzione giornaliera alle 9:00
0 9 * * * cd /path/to/nutriapp && source venv/bin/activate && python routes/whatsapp/run_scadenze.py

# Per esecuzione ogni 6 ore
0 */6 * * * cd /path/to/nutriapp && source venv/bin/activate && python routes/whatsapp/run_scadenze.py
```

## 📝 Variabili per Messaggi

### **Dati Personali**
- `{nome}` - Nome del paziente
- `{cognome}` - Cognome del paziente
- `{nome_completo}` - Nome e cognome
- `{eta}` - Età in anni
- `{telefono}` - Numero di telefono

### **Dati Fisici**
- `{altezza}` - Altezza in cm
- `{peso_iniziale}` - Peso iniziale
- `{data_nascita}` - Data di nascita
- `{data_creazione}` - Data iscrizione

### **Esempi di Messaggi**

```
Ciao {nome}! Come stai? Continua così! 💪

Ciao {nome_completo}! 
La tua età è {eta} anni e il tuo peso iniziale è {peso_iniziale} kg.
Continua a seguire il tuo percorso! 🚀
```

## 🔄 Integrazione con il Sistema

### **Trigger Automatici Integrati**

I trigger sono integrati nei seguenti file:

#### **`routes/appuntamenti.py`**
```python
# Quando cambia lo stato di un appuntamento
from routes.whatsapp.triggers import safe_trigger_appuntamento_stato
safe_trigger_appuntamento_stato(appuntamento, nuovo_stato)
```

#### **`routes/diete.py`**
```python
# Quando viene caricata una nuova dieta
from routes.whatsapp.triggers import safe_trigger_nuova_dieta
safe_trigger_nuova_dieta(paziente, nuova_dieta)
```

#### **`routes/allenamenti.py`**
```python
# Quando viene caricato un nuovo allenamento
from routes.whatsapp.triggers import safe_trigger_nuovo_allenamento
safe_trigger_nuovo_allenamento(paziente, nuovo_allenamento)
```

### **Sistema Scadenze**

Il sistema controlla automaticamente:
- **Diete in scadenza** tra 10 giorni
- **Allenamenti in scadenza** tra 10 giorni
- **Invio notifiche** ai pazienti interessati

## 🛠️ API e Funzioni

### **Invio Messaggi**

```python
from routes.whatsapp.sender import invia_whatsapp

# Invio messaggio diretto
successo = invia_whatsapp("393401234567", "Ciao! Messaggio di test")
```

### **Broadcast Personalizzato**

```python
from routes.whatsapp.broadcast import invia_broadcast_personalizzato

# Invio a tutti i pazienti
template = "Ciao {nome}! Il tuo messaggio personalizzato."
stats = invia_broadcast_personalizzato(template)
print(f"Inviati: {stats['inviati']}, Errori: {stats['errori']}")
```

### **Gestione Trigger**

```python
from routes.whatsapp.triggers import enable_trigger, disable_trigger

# Abilita trigger
enable_trigger('appuntamenti')

# Disabilita trigger
disable_trigger('scadenze')
```

## 📊 Statistiche e Monitoraggio

### **Statistiche Broadcast**

Ogni invio restituisce statistiche dettagliate:

```python
{
    'totale_pazienti': 100,      # Pazienti totali nel database
    'inviati': 95,               # Messaggi inviati con successo
    'errori': 3,                 # Errori durante l'invio
    'senza_telefono': 2,         # Pazienti senza numero
    'successo_percentuale': 95.0 # Percentuale di successo
}
```

### **Log Dettagliati**

Tutti gli invii vengono loggati con:
- **Timestamp** dell'invio
- **Paziente destinatario**
- **Messaggio inviato**
- **Risultato** (successo/errore)
- **Dettagli errori** se presenti

## 🚨 Sicurezza e Limitazioni

### **Sicurezza**
- **Accesso solo admin** per interfaccia web
- **Conferma obbligatoria** per invii broadcast
- **Validazione input** per messaggi
- **Gestione errori** robusta

### **Limitazioni**
- **Rate limiting** di Meta API (1000 messaggi/giorno per numero di telefono)
- **Timeout** di 10 secondi per richieste API
- **Validazione numeri** di telefono (formato internazionale)

## 🔧 Risoluzione Problemi

### **Errori Comuni**

#### **"Configurazione WhatsApp mancante"**
- Verifica che `WHATSAPP_ACCESS_TOKEN` e `WHATSAPP_PHONE_NUMBER_ID` siano impostati
- Controlla che le credenziali siano valide

#### **"Errore invio WhatsApp: 400"**
- Verifica il formato del numero di telefono (deve essere internazionale)
- Controlla che il numero sia registrato su WhatsApp Business

#### **"Timeout invio WhatsApp"**
- Verifica la connessione internet
- Controlla che l'API Meta sia raggiungibile

### **Debug**

#### **Abilita Log Dettagliati**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### **Test Invio Singolo**
```python
from routes.whatsapp.sender import invia_whatsapp
successo = invia_whatsapp("393401234567", "Test messaggio")
print(f"Invio: {'Successo' if successo else 'Fallito'}")
```

## 📈 Sviluppi Futuri

### **Funzionalità Pianificate**
- **Template predefiniti** per messaggi comuni
- **Scheduling messaggi** per invii programmati
- **Statistiche avanzate** con grafici
- **Filtri personalizzati** per target specifici
- **Integrazione webhook** per ricevere risposte

### **Miglioramenti Tecnici**
- **Caching** per ottimizzare le performance
- **Queue system** per gestire invii massivi
- **Retry logic** per gestire errori temporanei
- **Database logging** per storico completo

## 📞 Supporto

Per problemi o domande:
1. **Controlla i log** per errori specifici
2. **Verifica la configurazione** WhatsApp
3. **Testa con invio singolo** prima del broadcast
4. **Consulta questa documentazione** per dettagli tecnici

---

**Sistema WhatsApp nutriapp** - Gestione professionale dei messaggi automatici e personalizzati 🚀

