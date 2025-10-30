#!/usr/bin/env python3
"""
Script per gestire i trigger WhatsApp
Permette di abilitare/disabilitare trigger e monitorare lo stato
"""

import sys
import os

# Aggiungi il path del progetto
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from app.routes.whatsapp.triggers import (
    enable_trigger, 
    disable_trigger, 
    print_trigger_status,
    get_trigger_stats
)

def main():
    """Gestisce i trigger WhatsApp"""
    if len(sys.argv) < 2:
        print("🔧 Gestione Trigger WhatsApp")
        print("Uso: python gestione_trigger.py [comando]")
        print("\nComandi disponibili:")
        print("  status                    - Mostra stato trigger")
        print("  enable [tipo]            - Abilita trigger (appuntamenti|diete|allenamenti|scadenze)")
        print("  disable [tipo]           - Disabilita trigger")
        print("  enable-all               - Abilita tutti i trigger")
        print("  disable-all              - Disabilita tutti i trigger")
        print("\nEsempi:")
        print("  python gestione_trigger.py status")
        print("  python gestione_trigger.py enable appuntamenti")
        print("  python gestione_trigger.py disable scadenze")
        return
    
    comando = sys.argv[1].lower()
    
    if comando == "status":
        print_trigger_status()
        
    elif comando == "enable":
        if len(sys.argv) < 3:
            print("❌ Specifica il tipo di trigger da abilitare")
            print("Tipi: appuntamenti, diete, allenamenti, scadenze")
            return
        
        tipo = sys.argv[2].lower()
        enable_trigger(tipo)
        
    elif comando == "disable":
        if len(sys.argv) < 3:
            print("❌ Specifica il tipo di trigger da disabilitare")
            print("Tipi: appuntamenti, diete, allenamenti, scadenze")
            return
            
        tipo = sys.argv[2].lower()
        disable_trigger(tipo)
        
    elif comando == "enable-all":
        from app.routes.whatsapp.triggers import TRIGGERS_ENABLED
        for trigger in TRIGGERS_ENABLED.keys():
            enable_trigger(trigger)
        print("✅ Tutti i trigger abilitati")
        
    elif comando == "disable-all":
        from app.routes.whatsapp.triggers import TRIGGERS_ENABLED
        for trigger in TRIGGERS_ENABLED.keys():
            disable_trigger(trigger)
        print("❌ Tutti i trigger disabilitati")
        
    else:
        print(f"❌ Comando sconosciuto: {comando}")
        print("Usa 'python gestione_trigger.py' per vedere i comandi disponibili")

if __name__ == "__main__":
    main()
