"""
Sistema WhatsApp Semplificato
Solo invio messaggi diretti, niente tracking o webhook
"""

import requests
import logging
from app.config.config import Config

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def invia_whatsapp(telefono, messaggio):
    """
    Invia messaggio WhatsApp diretto tramite Meta API
    
    Args:
        telefono (str): Numero telefono destinatario (formato internazionale, es. "393401234567")
        messaggio (str): Testo del messaggio da inviare
    
    Returns:
        bool: True se inviato con successo, False altrimenti
    """
    try:
        # Verifica configurazione
        if not Config.WHATSAPP_ACCESS_TOKEN or not Config.WHATSAPP_PHONE_NUMBER_ID:
            logger.error("❌ Configurazione WhatsApp mancante: ACCESS_TOKEN o PHONE_NUMBER_ID")
            return False
        
        # URL API Meta WhatsApp
        url = f"https://graph.facebook.com/v18.0/{Config.WHATSAPP_PHONE_NUMBER_ID}/messages"
        
        # Headers per autenticazione
        headers = {
            "Authorization": f"Bearer {Config.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Payload del messaggio
        data = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": messaggio}
        }
        
        # Invio richiesta
        logger.info(f"📤 Invio WhatsApp a {telefono}: {messaggio[:50]}...")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            logger.info(f"✅ Messaggio inviato con successo a {telefono}")
            return True
        else:
            logger.error(f"❌ Errore invio WhatsApp: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout invio WhatsApp")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Errore rete WhatsApp: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Errore generico WhatsApp: {e}")
        return False

def invia_messaggio_appuntamento(paziente, appuntamento, azione):
    """
    Invia messaggio per appuntamento (confermato/annullato)
    
    Args:
        paziente: Oggetto Patient
        appuntamento: Oggetto Appuntamento  
        azione (str): 'confermato' o 'annullato'
    """
    if azione == 'confermato':
        messaggio = f"""Ciao {paziente.nome}! 👋

Il tuo appuntamento è stato CONFERMATO ✅

📅 Data: {appuntamento.data_appuntamento.strftime('%d/%m/%Y')}
🕐 Ora: {appuntamento.data_appuntamento.strftime('%H:%M')}
📋 Tipo: {appuntamento.tipo.replace('_', ' ').title()}

Ti aspettiamo! 🎯"""
    
    elif azione == 'annullato':
        messaggio = f"""Ciao {paziente.nome}! 👋

Il tuo appuntamento è stato ANNULLATO ❌

📅 Data: {appuntamento.data_appuntamento.strftime('%d/%m/%Y')}
🕐 Ora: {appuntamento.data_appuntamento.strftime('%H:%M')}

Contattaci per riprogrammare! 📞"""
    
    else:
        return False
    
    return invia_whatsapp(paziente.telefono, messaggio)

def invia_messaggio_nuova_dieta(paziente, dieta):
    """
    Invia messaggio per nuova dieta caricata
    
    Args:
        paziente: Oggetto Patient
        dieta: Oggetto Dieta
    """
    messaggio = f"""Ciao {paziente.nome}! 🍽️

La tua nuova dieta è pronta! ✅

📅 Periodo: {dieta.data_inizio.strftime('%d/%m/%Y')} - {dieta.data_fine.strftime('%d/%m/%Y')}
🔥 Calorie: {dieta.kcal} kcal/giorno

Puoi scaricarla dall'area riservata del sito! 📱

Buon lavoro! 💪"""
    
    return invia_whatsapp(paziente.telefono, messaggio)

def invia_messaggio_nuovo_allenamento(paziente, allenamento):
    """
    Invia messaggio per nuovo allenamento caricato
    
    Args:
        paziente: Oggetto Patient
        allenamento: Oggetto Allenamento
    """
    messaggio = f"""Ciao {paziente.nome}! 💪

Il tuo nuovo piano di allenamento è pronto! ✅

📅 Periodo: {allenamento.data_inizio.strftime('%d/%m/%Y')} - {allenamento.data_fine.strftime('%d/%m/%Y')}

Puoi scaricarlo dall'area riservata del sito! 📱

Forza, iniziamo! 🔥"""
    
    return invia_whatsapp(paziente.telefono, messaggio)

def invia_messaggio_scadenza(paziente, tipo, data_scadenza):
    """
    Invia messaggio per scadenza imminente
    
    Args:
        paziente: Oggetto Patient
        tipo (str): 'dieta' o 'allenamento'
        data_scadenza: Data di scadenza
    """
    if tipo == 'dieta':
        messaggio = f"""Ciao {paziente.nome}! ⏰

La tua dieta scade tra 10 giorni! 📅

📅 Scadenza: {data_scadenza.strftime('%d/%m/%Y')}

Contattaci per il rinnovo! 📞"""
    
    elif tipo == 'allenamento':
        messaggio = f"""Ciao {paziente.nome}! ⏰

Il tuo piano di allenamento scade tra 10 giorni! 📅

📅 Scadenza: {data_scadenza.strftime('%d/%m/%Y')}

Contattaci per il rinnovo! 📞"""
    
    else:
        return False
    
    return invia_whatsapp(paziente.telefono, messaggio)

# Test della funzione (solo per debug)
if __name__ == "__main__":
    # Test con numero di prova (sostituisci con un numero reale per test)
    test_telefono = "393401234567"  # Sostituisci con numero reale
    test_messaggio = "Test messaggio WhatsApp dal sistema nutriapp! 🚀"
    
    print("🧪 Test invio WhatsApp...")
    risultato = invia_whatsapp(test_telefono, test_messaggio)
    print(f"Risultato: {'✅ Successo' if risultato else '❌ Errore'}")
