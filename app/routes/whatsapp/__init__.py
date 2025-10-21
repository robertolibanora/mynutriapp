"""
Modulo WhatsApp Semplificato
Gestisce invio messaggi, trigger automatici e broadcast
"""

from .sender import invia_whatsapp
from .triggers import (
    safe_trigger_appuntamento_stato,
    safe_trigger_nuova_dieta,
    safe_trigger_nuovo_allenamento,
    safe_trigger_scadenza_generica,
    print_trigger_status,
    enable_trigger,
    disable_trigger
)
from .broadcast import (
    invia_broadcast_personalizzato,
    invia_broadcast_scadenze,
    invia_broadcast_filtro,
    sostituisci_variabili
)

__all__ = [
    'invia_whatsapp',
    'safe_trigger_appuntamento_stato',
    'safe_trigger_nuova_dieta', 
    'safe_trigger_nuovo_allenamento',
    'safe_trigger_scadenza_generica',
    'print_trigger_status',
    'enable_trigger',
    'disable_trigger',
    'invia_broadcast_personalizzato',
    'invia_broadcast_scadenze',
    'invia_broadcast_filtro',
    'sostituisci_variabili'
]
