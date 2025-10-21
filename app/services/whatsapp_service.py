"""
Servizio per la gestione dei messaggi WhatsApp
"""

from app.routes.whatsapp.sender import (
    invia_whatsapp,
    invia_messaggio_appuntamento,
    invia_messaggio_nuova_dieta,
    invia_messaggio_nuovo_allenamento,
    invia_messaggio_scadenza
)
from app.routes.whatsapp.triggers import (
    safe_trigger_appuntamento_stato,
    safe_trigger_nuova_dieta,
    safe_trigger_nuovo_allenamento,
    safe_trigger_scadenza_generica
)

class WhatsAppService:
    """Servizio centralizzato per WhatsApp"""
    
    @staticmethod
    def invia_notifica_appuntamento(appuntamento, stato):
        """Invia notifica per appuntamento"""
        return safe_trigger_appuntamento_stato(appuntamento, stato)
    
    @staticmethod
    def invia_notifica_dieta(paziente, dieta):
        """Invia notifica per nuova dieta"""
        return safe_trigger_nuova_dieta(paziente, dieta)
    
    @staticmethod
    def invia_notifica_allenamento(paziente, allenamento):
        """Invia notifica per nuovo allenamento"""
        return safe_trigger_nuovo_allenamento(paziente, allenamento)
    
    @staticmethod
    def invia_notifica_scadenza(paziente, tipo, data_scadenza):
        """Invia notifica per scadenza"""
        return safe_trigger_scadenza_generica(paziente, tipo, data_scadenza)
