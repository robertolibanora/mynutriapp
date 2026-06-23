"""
Sistema WhatsApp via Evolution API
"""

import requests
import logging
from app.config.config import Config
from app.utils.helpers import format_phone_whatsapp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _configurazione_valida() -> bool:
    if not Config.WHATSAPP_ENABLED:
        logger.warning("⚠️ WhatsApp disabilitato (WHATSAPP_ENABLED=False)")
        return False

    if not all([Config.EVOLUTION_API_URL, Config.EVOLUTION_API_KEY, Config.EVOLUTION_INSTANCE]):
        logger.error("❌ Configurazione Evolution API mancante: EVOLUTION_API_URL, EVOLUTION_API_KEY o EVOLUTION_INSTANCE")
        return False

    return True


def invia_whatsapp(telefono, messaggio):
    """
    Invia messaggio WhatsApp al destinatario tramite Evolution API.

    Args:
        telefono (str): Numero destinatario (locale o internazionale)
        messaggio (str): Testo del messaggio

    Returns:
        bool: True se inviato con successo, False altrimenti
    """
    try:
        if not _configurazione_valida():
            return False

        numero = format_phone_whatsapp(telefono)
        if not numero:
            logger.error("❌ Numero di telefono non valido")
            return False

        url = f"{Config.EVOLUTION_API_URL}/message/sendText/{Config.EVOLUTION_INSTANCE}"
        headers = {
            "apikey": Config.EVOLUTION_API_KEY,
            "Content-Type": "application/json",
        }
        data = {
            "number": numero,
            "text": messaggio,
        }

        logger.info(f"📤 Invio WhatsApp a {numero}: {messaggio[:50]}...")
        response = requests.post(url, headers=headers, json=data, timeout=30)

        if response.status_code in (200, 201):
            logger.info(f"✅ Messaggio inviato con successo a {numero}")
            return True

        logger.error(f"❌ Errore Evolution API: {response.status_code} - {response.text}")
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


if __name__ == "__main__":
    test_telefono = "3401234567"
    test_messaggio = "Test messaggio WhatsApp dal sistema nutriapp! 🚀"

    print("🧪 Test invio WhatsApp...")
    risultato = invia_whatsapp(test_telefono, test_messaggio)
    print(f"Risultato: {'✅ Successo' if risultato else '❌ Errore'}")
