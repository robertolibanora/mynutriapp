"""
Modulo per gestire tutti i trigger WhatsApp
Centralizza la logica di invio messaggi per eventi specifici
"""

from .sender import (
    invia_messaggio_appuntamento,
    invia_messaggio_nuova_dieta, 
    invia_messaggio_nuovo_allenamento,
    invia_messaggio_scadenza
)
from .broadcast import load_trigger_templates, sostituisci_variabili

def trigger_appuntamento_confermato(appuntamento):
    """
    Trigger per appuntamento confermato
    
    Args:
        appuntamento: Oggetto Appuntamento
    """
    try:
        # Usa template configurabile (niente doppio invio)
        templates = load_trigger_templates()
        testo = templates.get('appuntamenti')
        variabili_extra = {
            '{stato_appuntamento}': 'confermato',
            '{data_appuntamento}': appuntamento.data_appuntamento.strftime('%d/%m/%Y'),
            '{ora_appuntamento}': appuntamento.data_appuntamento.strftime('%H:%M'),
            '{tipo_appuntamento}': appuntamento.tipo.replace('_', ' ').title()
        }
        messaggio = sostituisci_variabili(testo, appuntamento.patient, variabili_extra)
        from .sender import invia_whatsapp
        if invia_whatsapp(appuntamento.patient.telefono, messaggio):
            print(f"✅ WhatsApp inviato per appuntamento confermato: {appuntamento.patient.nome}")
        else:
            print(f"⚠️ WhatsApp non inviato per appuntamento confermato: {appuntamento.patient.nome}")
    except Exception as e:
        print(f"⚠️ Errore invio WhatsApp appuntamento confermato: {e}")

def trigger_appuntamento_annullato(appuntamento):
    """
    Trigger per appuntamento annullato
    
    Args:
        appuntamento: Oggetto Appuntamento
    """
    try:
        templates = load_trigger_templates()
        testo = templates.get('appuntamenti')
        variabili_extra = {
            '{stato_appuntamento}': 'annullato',
            '{data_appuntamento}': appuntamento.data_appuntamento.strftime('%d/%m/%Y'),
            '{ora_appuntamento}': appuntamento.data_appuntamento.strftime('%H:%M'),
            '{tipo_appuntamento}': appuntamento.tipo.replace('_', ' ').title()
        }
        messaggio = sostituisci_variabili(testo, appuntamento.patient, variabili_extra)
        from .sender import invia_whatsapp
        if invia_whatsapp(appuntamento.patient.telefono, messaggio):
            print(f"✅ WhatsApp inviato per appuntamento annullato: {appuntamento.patient.nome}")
        else:
            print(f"⚠️ WhatsApp non inviato per appuntamento annullato: {appuntamento.patient.nome}")
    except Exception as e:
        print(f"⚠️ Errore invio WhatsApp appuntamento annullato: {e}")

def trigger_nuova_dieta(paziente, dieta):
    """
    Trigger per nuova dieta caricata
    
    Args:
        paziente: Oggetto Patient
        dieta: Oggetto Dieta
    """
    try:
        invia_messaggio_nuova_dieta(paziente, dieta)
        print(f"✅ WhatsApp inviato per nuova dieta: {paziente.nome}")
    except Exception as e:
        print(f"⚠️ Errore invio WhatsApp nuova dieta: {e}")

def trigger_nuovo_allenamento(paziente, allenamento):
    """
    Trigger per nuovo allenamento caricato
    
    Args:
        paziente: Oggetto Patient
        allenamento: Oggetto Allenamento
    """
    try:
        invia_messaggio_nuovo_allenamento(paziente, allenamento)
        print(f"✅ WhatsApp inviato per nuovo allenamento: {paziente.nome}")
    except Exception as e:
        print(f"⚠️ Errore invio WhatsApp nuovo allenamento: {e}")

def trigger_scadenza_dieta(paziente, data_scadenza):
    """
    Trigger per scadenza dieta
    
    Args:
        paziente: Oggetto Patient
        data_scadenza: Data di scadenza
    """
    try:
        invia_messaggio_scadenza(paziente, 'dieta', data_scadenza)
        print(f"✅ WhatsApp inviato per scadenza dieta: {paziente.nome}")
    except Exception as e:
        print(f"⚠️ Errore invio WhatsApp scadenza dieta: {e}")

def trigger_scadenza_allenamento(paziente, data_scadenza):
    """
    Trigger per scadenza allenamento
    
    Args:
        paziente: Oggetto Patient
        data_scadenza: Data di scadenza
    """
    try:
        invia_messaggio_scadenza(paziente, 'allenamento', data_scadenza)
        print(f"✅ WhatsApp inviato per scadenza allenamento: {paziente.nome}")
    except Exception as e:
        print(f"⚠️ Errore invio WhatsApp scadenza allenamento: {e}")

# ========================================
# FUNZIONI DI UTILITÀ
# ========================================

def trigger_appuntamento_stato(appuntamento, nuovo_stato):
    """
    Trigger generico per cambio stato appuntamento
    
    Args:
        appuntamento: Oggetto Appuntamento
        nuovo_stato: Nuovo stato ('confermato', 'annullato')
    """
    if nuovo_stato == 'confermato':
        trigger_appuntamento_confermato(appuntamento)
    elif nuovo_stato == 'annullato':
        trigger_appuntamento_annullato(appuntamento)

def trigger_scadenza_generica(paziente, tipo, data_scadenza):
    """
    Trigger generico per scadenze
    
    Args:
        paziente: Oggetto Patient
        tipo: 'dieta' o 'allenamento'
        data_scadenza: Data di scadenza
    """
    if tipo == 'dieta':
        trigger_scadenza_dieta(paziente, data_scadenza)
    elif tipo == 'allenamento':
        trigger_scadenza_allenamento(paziente, data_scadenza)

# ========================================
# FUNZIONI PER DISABILITARE/ABILITARE TRIGGER
# ========================================

# Flag globali per abilitare/disabilitare trigger
TRIGGERS_ENABLED = {
    'appuntamenti': True,
    'diete': True,
    'allenamenti': True,
    'scadenze': True
}

def enable_trigger(trigger_type):
    """Abilita un tipo di trigger"""
    if trigger_type in TRIGGERS_ENABLED:
        TRIGGERS_ENABLED[trigger_type] = True
        print(f"✅ Trigger {trigger_type} abilitato")

def disable_trigger(trigger_type):
    """Disabilita un tipo di trigger"""
    if trigger_type in TRIGGERS_ENABLED:
        TRIGGERS_ENABLED[trigger_type] = False
        print(f"❌ Trigger {trigger_type} disabilitato")

def is_trigger_enabled(trigger_type):
    """Verifica se un trigger è abilitato"""
    return TRIGGERS_ENABLED.get(trigger_type, False)

# ========================================
# VERSIONI SICURE DEI TRIGGER (con controllo abilitazione)
# ========================================

def safe_trigger_appuntamento_stato(appuntamento, nuovo_stato):
    """Trigger sicuro per appuntamenti (controlla se abilitato)"""
    if is_trigger_enabled('appuntamenti'):
        trigger_appuntamento_stato(appuntamento, nuovo_stato)
    else:
        print(f"⏸️ Trigger appuntamenti disabilitato per {appuntamento.patient.nome}")

def safe_trigger_nuova_dieta(paziente, dieta):
    """Trigger sicuro per diete (controlla se abilitato)"""
    if is_trigger_enabled('diete'):
        trigger_nuova_dieta(paziente, dieta)
    else:
        print(f"⏸️ Trigger diete disabilitato per {paziente.nome}")

def safe_trigger_nuovo_allenamento(paziente, allenamento):
    """Trigger sicuro per allenamenti (controlla se abilitato)"""
    if is_trigger_enabled('allenamenti'):
        trigger_nuovo_allenamento(paziente, allenamento)
    else:
        print(f"⏸️ Trigger allenamenti disabilitato per {paziente.nome}")

def safe_trigger_scadenza_generica(paziente, tipo, data_scadenza):
    """Trigger sicuro per scadenze (controlla se abilitato)"""
    if is_trigger_enabled('scadenze'):
        trigger_scadenza_generica(paziente, tipo, data_scadenza)
    else:
        print(f"⏸️ Trigger scadenze disabilitato per {paziente.nome}")

# ========================================
# STATISTICHE E MONITORAGGIO
# ========================================

def get_trigger_stats():
    """Ritorna statistiche sui trigger"""
    return {
        'trigger_enabled': TRIGGERS_ENABLED,
        'total_triggers': len(TRIGGERS_ENABLED),
        'enabled_triggers': sum(1 for enabled in TRIGGERS_ENABLED.values() if enabled),
        'disabled_triggers': sum(1 for enabled in TRIGGERS_ENABLED.values() if not enabled)
    }

def print_trigger_status():
    """Stampa lo stato dei trigger"""
    stats = get_trigger_stats()
    print("📊 STATO TRIGGER WHATSAPP:")
    for trigger, enabled in stats['trigger_enabled'].items():
        status = "✅ Abilitato" if enabled else "❌ Disabilitato"
        print(f"   {trigger}: {status}")
    print(f"   Totale: {stats['enabled_triggers']}/{stats['total_triggers']} abilitati")

# Test del modulo
if __name__ == "__main__":
    print("🧪 Test modulo whatsapp_triggers...")
    print_trigger_status()
    print("✅ Modulo whatsapp_triggers funzionante!")
