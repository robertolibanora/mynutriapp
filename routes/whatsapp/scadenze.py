"""
Job per controllare scadenze diete e allenamenti
E inviare messaggi WhatsApp automatici
"""

from datetime import date, timedelta
import logging
from models import db, Dieta, Allenamento, Patient
from .triggers import safe_trigger_scadenza_generica

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def controlla_scadenze():
    """
    Controlla scadenze diete e allenamenti e invia messaggi WhatsApp
    """
    oggi = date.today()
    tra_10_giorni = oggi + timedelta(days=10)
    
    logger.info(f"🔍 Controllo scadenze per il {tra_10_giorni.strftime('%d/%m/%Y')}")
    
    # Contatori per statistiche
    diete_inviate = 0
    allenamenti_inviati = 0
    errori = 0
    
    try:
        # ========================================
        # DIETE IN SCADENZA
        # ========================================
        logger.info("🍽️ Controllo diete in scadenza...")
        diete = Dieta.query.filter(Dieta.data_fine == tra_10_giorni).all()
        
        for dieta in diete:
            try:
                paziente = dieta.patient
                if paziente and paziente.telefono:
                    logger.info(f"📤 Invio scadenza dieta a {paziente.nome} {paziente.cognome}")
                    
                    safe_trigger_scadenza_generica(paziente, 'dieta', dieta.data_fine)
                    diete_inviate += 1
                    logger.info(f"✅ Messaggio dieta inviato a {paziente.nome}")
                else:
                    logger.warning(f"⚠️ Paziente {dieta.patient_id} senza telefono per dieta")
                    
            except Exception as e:
                errori += 1
                logger.error(f"❌ Errore processamento dieta {dieta.id}: {e}")
        
        # ========================================
        # ALLENAMENTI IN SCADENZA
        # ========================================
        logger.info("💪 Controllo allenamenti in scadenza...")
        allenamenti = Allenamento.query.filter(Allenamento.data_fine == tra_10_giorni).all()
        
        for allenamento in allenamenti:
            try:
                paziente = allenamento.patient
                if paziente and paziente.telefono:
                    logger.info(f"📤 Invio scadenza allenamento a {paziente.nome} {paziente.cognome}")
                    
                    safe_trigger_scadenza_generica(paziente, 'allenamento', allenamento.data_fine)
                    allenamenti_inviati += 1
                    logger.info(f"✅ Messaggio allenamento inviato a {paziente.nome}")
                else:
                    logger.warning(f"⚠️ Paziente {allenamento.patient_id} senza telefono per allenamento")
                    
            except Exception as e:
                errori += 1
                logger.error(f"❌ Errore processamento allenamento {allenamento.id}: {e}")
        
        # ========================================
        # STATISTICHE FINALI
        # ========================================
        logger.info("📊 STATISTICHE SCADENZE:")
        logger.info(f"   🍽️ Diete inviate: {diete_inviate}")
        logger.info(f"   💪 Allenamenti inviati: {allenamenti_inviati}")
        logger.info(f"   ❌ Errori: {errori}")
        logger.info(f"   📱 Totale messaggi: {diete_inviate + allenamenti_inviati}")
        
        return {
            'diete_inviate': diete_inviate,
            'allenamenti_inviati': allenamenti_inviati,
            'errori': errori,
            'totale': diete_inviate + allenamenti_inviati
        }
        
    except Exception as e:
        logger.error(f"❌ Errore generale controllo scadenze: {e}")
        return {
            'diete_inviate': 0,
            'allenamenti_inviati': 0,
            'errori': 1,
            'totale': 0
        }

def controlla_scadenze_multiple():
    """
    Controlla scadenze per più giorni (1, 3, 7, 10 giorni)
    """
    oggi = date.today()
    giorni_controllo = [1, 3, 7, 10]
    
    logger.info(f"🔍 Controllo scadenze multiple per {len(giorni_controllo)} giorni")
    
    totale_messaggi = 0
    
    for giorni in giorni_controllo:
        data_controllo = oggi + timedelta(days=giorni)
        logger.info(f"📅 Controllo scadenze per {giorni} giorni ({data_controllo.strftime('%d/%m/%Y')})")
        
        # Diete
        diete = Dieta.query.filter(Dieta.data_fine == data_controllo).all()
        for dieta in diete:
            try:
                paziente = dieta.patient
                if paziente and paziente.telefono:
                    messaggio = f"""Ciao {paziente.nome}! ⏰

La tua dieta scade tra {giorni} giorni! 📅

📅 Scadenza: {dieta.data_fine.strftime('%d/%m/%Y')}

Contattaci per il rinnovo! 📞"""
                    
                    from .sender import invia_whatsapp
                    if invia_whatsapp(paziente.telefono, messaggio):
                        totale_messaggi += 1
                        logger.info(f"✅ Scadenza dieta {giorni} giorni inviata a {paziente.nome}")
            except Exception as e:
                logger.error(f"❌ Errore scadenza dieta {giorni} giorni: {e}")
        
        # Allenamenti
        allenamenti = Allenamento.query.filter(Allenamento.data_fine == data_controllo).all()
        for allenamento in allenamenti:
            try:
                paziente = allenamento.patient
                if paziente and paziente.telefono:
                    messaggio = f"""Ciao {paziente.nome}! ⏰

Il tuo piano di allenamento scade tra {giorni} giorni! 📅

📅 Scadenza: {allenamento.data_fine.strftime('%d/%m/%Y')}

Contattaci per il rinnovo! 📞"""
                    
                    from .sender import invia_whatsapp
                    if invia_whatsapp(paziente.telefono, messaggio):
                        totale_messaggi += 1
                        logger.info(f"✅ Scadenza allenamento {giorni} giorni inviata a {paziente.nome}")
            except Exception as e:
                logger.error(f"❌ Errore scadenza allenamento {giorni} giorni: {e}")
    
    logger.info(f"📊 TOTALE MESSAGGI SCADENZE MULTIPLE: {totale_messaggi}")
    return totale_messaggi

# Test del job (solo per debug)
if __name__ == "__main__":
    print("🧪 Test controllo scadenze...")
    
    # Test scadenze 10 giorni
    print("\n📅 Test scadenze 10 giorni:")
    risultato = controlla_scadenze()
    print(f"Risultato: {risultato}")
    
    # Test scadenze multiple
    print("\n📅 Test scadenze multiple:")
    totale = controlla_scadenze_multiple()
    print(f"Totale messaggi: {totale}")
