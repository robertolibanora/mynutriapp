"""
Sistema Broadcast WhatsApp
Permette di inviare messaggi personalizzati a tutti i pazienti
con sostituzione automatica di variabili (nome, cognome, etc.)
"""

import logging
import os
import json
from datetime import datetime, timedelta
from models import db, Patient, Dieta, Allenamento
from .sender import invia_whatsapp

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TEMPLATES_FILE = os.path.join(BASE_DIR, 'whatsapp_trigger_templates.json')

def _default_trigger_templates():
    """Template di default per ciascun trigger automatico."""
    return {
        'appuntamenti': "Ciao {nome}, il tuo appuntamento è stato {stato_appuntamento} per il {data_appuntamento} alle {ora_appuntamento}. Tipo: {tipo_appuntamento}.",
        'diete': "Ciao {nome}, è stata caricata una nuova dieta per te. Controlla l'app!",
        'allenamenti': "Ciao {nome}, è disponibile un nuovo allenamento. Forza! 💪",
        'scadenze': "Ciao {nome}, promemoria: la tua {tipo_scadenza} scade il {data_scadenza}."
    }

def load_trigger_templates():
    """Carica i template dei messaggi trigger da file JSON, con fallback ai default."""
    try:
        if os.path.exists(TEMPLATES_FILE):
            with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                defaults = _default_trigger_templates()
                # Assicura che tutte le chiavi esistano
                for k, v in defaults.items():
                    data.setdefault(k, v)
                # Migrazione semplice: aggiorna il template "appuntamenti" se è quello legacy
                legacy = "Ciao {nome}, il tuo appuntamento è stato {stato_appuntamento}. A presto!"
                if data.get('appuntamenti') == legacy:
                    data['appuntamenti'] = defaults['appuntamenti']
                    # Prova a salvare subito l'upgrade silenzioso
                    try:
                        with open(TEMPLATES_FILE, 'w', encoding='utf-8') as wf:
                            json.dump(data, wf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                return data
    except Exception as e:
        logger.warning(f"Impossibile leggere {TEMPLATES_FILE}: {e}")
    return _default_trigger_templates()

def save_trigger_templates(templates_dict):
    """Salva i template dei messaggi trigger su file JSON."""
    try:
        with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(templates_dict, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Errore salvataggio template trigger: {e}")
        return False

def sostituisci_variabili(testo, paziente, variabili_extra=None):
    """
    Sostituisce le variabili nel testo con i dati del paziente
    
    Args:
        testo (str): Testo con variabili da sostituire
        paziente: Oggetto Patient
        variabili_extra (dict): Variabili aggiuntive personalizzate
    
    Returns:
        str: Testo con variabili sostituite
    """
    # Variabili di base del paziente
    variabili = {
        '{nome}': paziente.nome,
        '{cognome}': paziente.cognome,
        '{nome_completo}': f"{paziente.nome} {paziente.cognome}",
        '{telefono}': paziente.telefono,
        '{data_nascita}': paziente.data_nascita.strftime('%d/%m/%Y'),
        '{eta}': str((datetime.now().date() - paziente.data_nascita).days // 365),
        '{altezza}': str(paziente.altezza_cm),
        '{peso_iniziale}': str(paziente.peso_iniziale),
        '{data_creazione}': paziente.data_creazione.strftime('%d/%m/%Y'),
    }
    
    # Variabili aggiuntive se fornite
    if variabili_extra:
        variabili.update(variabili_extra)
    
    # Sostituisci tutte le variabili
    testo_sostituito = testo
    for variabile, valore in variabili.items():
        testo_sostituito = testo_sostituito.replace(variabile, str(valore))
    
    return testo_sostituito

def invia_broadcast_personalizzato(testo_template, pazienti=None, variabili_extra=None):
    """
    Invia un messaggio personalizzato a tutti i pazienti (o a una lista specifica)
    
    Args:
        testo_template (str): Testo con variabili da sostituire
        pazienti (list): Lista di pazienti (se None, invia a tutti)
        variabili_extra (dict): Variabili aggiuntive personalizzate
    
    Returns:
        dict: Statistiche dell'invio
    """
    if pazienti is None:
        # Ottieni tutti i pazienti con telefono
        pazienti = Patient.query.filter(Patient.telefono.isnot(None)).all()
    
    logger.info(f"📤 Avvio broadcast a {len(pazienti)} pazienti")
    
    # Statistiche
    inviati = 0
    errori = 0
    pazienti_senza_telefono = 0
    
    for paziente in pazienti:
        try:
            # Verifica che abbia il telefono
            if not paziente.telefono:
                pazienti_senza_telefono += 1
                logger.warning(f"⚠️ Paziente {paziente.nome} {paziente.cognome} senza telefono")
                continue
            
            # Sostituisci variabili nel testo
            messaggio_personalizzato = sostituisci_variabili(testo_template, paziente, variabili_extra)
            
            # Invia messaggio
            successo = invia_whatsapp(paziente.telefono, messaggio_personalizzato)
            
            if successo:
                inviati += 1
                logger.info(f"✅ Messaggio inviato a {paziente.nome} {paziente.cognome}")
            else:
                errori += 1
                logger.error(f"❌ Errore invio a {paziente.nome} {paziente.cognome}")
                
        except Exception as e:
            errori += 1
            logger.error(f"❌ Errore processamento {paziente.nome} {paziente.cognome}: {e}")
    
    # Statistiche finali
    stats = {
        'totale_pazienti': len(pazienti),
        'inviati': inviati,
        'errori': errori,
        'senza_telefono': pazienti_senza_telefono,
        'successo_percentuale': (inviati / len(pazienti) * 100) if pazienti else 0
    }
    
    logger.info(f"📊 BROADCAST COMPLETATO:")
    logger.info(f"   📱 Messaggi inviati: {stats['inviati']}")
    logger.info(f"   ❌ Errori: {stats['errori']}")
    logger.info(f"   ⚠️ Senza telefono: {stats['senza_telefono']}")
    logger.info(f"   📈 Successo: {stats['successo_percentuale']:.1f}%")
    
    return stats

def invia_broadcast_scadenze(testo_template, giorni=10, variabili_extra=None):
    """
    Invia messaggio personalizzato solo ai pazienti con scadenze
    
    Args:
        testo_template (str): Testo con variabili da sostituire
        giorni (int): Giorni per la scadenza (default 10)
        variabili_extra (dict): Variabili aggiuntive personalizzate
    
    Returns:
        dict: Statistiche dell'invio
    """
    oggi = datetime.now().date()
    data_scadenza = oggi + timedelta(days=giorni)
    
    # Trova pazienti con scadenze
    pazienti_con_scadenze = set()
    
    # Diete in scadenza
    diete = Dieta.query.filter(Dieta.data_fine == data_scadenza).all()
    for dieta in diete:
        pazienti_con_scadenze.add(dieta.patient)
    
    # Allenamenti in scadenza
    allenamenti = Allenamento.query.filter(Allenamento.data_fine == data_scadenza).all()
    for allenamento in allenamenti:
        pazienti_con_scadenze.add(allenamento.patient)
    
    logger.info(f"📅 Trovati {len(pazienti_con_scadenze)} pazienti con scadenze tra {giorni} giorni")
    
    # Aggiungi variabili specifiche per scadenze
    if variabili_extra is None:
        variabili_extra = {}
    
    variabili_extra['{giorni_scadenza}'] = str(giorni)
    variabili_extra['{data_scadenza}'] = data_scadenza.strftime('%d/%m/%Y')
    
    return invia_broadcast_personalizzato(testo_template, list(pazienti_con_scadenze), variabili_extra)

def invia_broadcast_filtro(testo_template, filtro_callback, variabili_extra=None):
    """
    Invia messaggio personalizzato a pazienti filtrati
    
    Args:
        testo_template (str): Testo con variabili da sostituire
        filtro_callback (function): Funzione che filtra i pazienti (riceve Patient, ritorna bool)
        variabili_extra (dict): Variabili aggiuntive personalizzate
    
    Returns:
        dict: Statistiche dell'invio
    """
    # Ottieni tutti i pazienti
    tutti_pazienti = Patient.query.filter(Patient.telefono.isnot(None)).all()
    
    # Filtra i pazienti
    pazienti_filtrati = [p for p in tutti_pazienti if filtro_callback(p)]
    
    logger.info(f"🔍 Filtro applicato: {len(pazienti_filtrati)}/{len(tutti_pazienti)} pazienti selezionati")
    
    return invia_broadcast_personalizzato(testo_template, pazienti_filtrati, variabili_extra)

# ========================================
# FUNZIONI DI UTILITÀ PER FILTRI COMUNI
# ========================================

def filtro_eta_minima(eta_minima):
    """Filtro per età minima"""
    def filtro(paziente):
        eta = (datetime.now().date() - paziente.data_nascita).days // 365
        return eta >= eta_minima
    return filtro

def filtro_sesso(sesso):
    """Filtro per sesso"""
    def filtro(paziente):
        return paziente.sesso == sesso
    return filtro

def filtro_con_diete():
    """Filtro per pazienti con diete attive"""
    def filtro(paziente):
        oggi = datetime.now().date()
        return any(dieta.data_fine >= oggi for dieta in paziente.diete)
    return filtro

def filtro_con_allenamenti():
    """Filtro per pazienti con allenamenti attivi"""
    def filtro(paziente):
        oggi = datetime.now().date()
        return any(allenamento.data_fine >= oggi for allenamento in paziente.allenamenti)
    return filtro

def filtro_creati_dopo(data):
    """Filtro per pazienti creati dopo una data"""
    def filtro(paziente):
        return paziente.data_creazione.date() >= data
    return filtro

# ========================================
# ESEMPI DI UTILIZZO
# ========================================

def esempi_utilizzo():
    """Esempi di utilizzo del sistema broadcast"""
    
    print("📱 ESEMPI UTILIZZO BROADCAST WHATSAPP")
    print("=" * 50)
    
    print("\n1️⃣ Messaggio a tutti i pazienti:")
    print("invia_broadcast_personalizzato('Ciao {nome}, come stai?')")
    
    print("\n2️⃣ Messaggio personalizzato con variabili:")
    print("invia_broadcast_personalizzato('Ciao {nome}, la tua dieta scade tra {giorni_scadenza} giorni!')")
    
    print("\n3️⃣ Messaggio solo a pazienti con scadenze:")
    print("invia_broadcast_scadenze('Ciao {nome}, hai una scadenza tra {giorni_scadenza} giorni!')")
    
    print("\n4️⃣ Messaggio a pazienti filtrati (età minima 30):")
    print("invia_broadcast_filtro('Messaggio per over 30', filtro_eta_minima(30))")
    
    print("\n5️⃣ Messaggio con variabili personalizzate:")
    variabili = {'{giorni_scadenza}': '5', '{tipo_scadenza}': 'dieta'}
    print("invia_broadcast_personalizzato('Ciao {nome}, {tipo_scadenza} scade tra {giorni_scadenza} giorni!', variabili_extra=variabili)")

# Test del modulo
if __name__ == "__main__":
    esempi_utilizzo()
    
    # Test con un messaggio di esempio
    print("\n🧪 Test invio broadcast...")
    
    # Esempio di messaggio personalizzato
    messaggio_test = """Ciao {nome}! 👋

Questo è un messaggio di test personalizzato per {nome_completo}.

I tuoi dati:
- Età: {eta} anni
- Altezza: {altezza} cm
- Peso iniziale: {peso_iniziale} kg

Grazie per la fiducia! 💪"""
    
    print(f"Messaggio template: {messaggio_test}")
    print("✅ Modulo broadcast funzionante!")
