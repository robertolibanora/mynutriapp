#!/usr/bin/env python3
"""
Script per eseguire il controllo scadenze
Può essere eseguito manualmente o tramite cron
"""

import sys
import os
from datetime import datetime

# Aggiungi il path del progetto
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

# Importa Flask app per inizializzare il database
from wsgi import app
from app.routes.whatsapp.scadenze import controlla_scadenze, controlla_scadenze_multiple

def main():
    """Esegue il controllo scadenze"""
    print(f"🚀 Avvio controllo scadenze - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Usa app Flask per inizializzare il database
    
    with app.app_context():
        try:
            # Controlla se è stato passato un parametro per scadenze multiple
            if len(sys.argv) > 1 and sys.argv[1] == '--multiple':
                print("📅 Modalità scadenze multiple (1, 3, 7, 10 giorni)")
                totale = controlla_scadenze_multiple()
                print(f"✅ Completato! Totale messaggi inviati: {totale}")
            else:
                print("📅 Modalità scadenze 10 giorni")
                risultato = controlla_scadenze()
                print(f"✅ Completato! Risultato: {risultato}")
                
        except Exception as e:
            print(f"❌ Errore durante esecuzione: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
