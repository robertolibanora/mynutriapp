"""
QR Code Validator - Funzioni standalone per validazione QR code

Questo modulo contiene funzioni di utilità per validare formati e codici QR
senza dipendenze dal resto dell'applicazione.
"""

import re
from typing import Optional


def validate_qr_format(code: str, min_length: int = 8, max_length: int = 20) -> bool:
    """
    Valida il formato base di un codice QR.
    
    Verifica che il codice:
    - Non sia vuoto
    - Rispetti la lunghezza minima/massima
    - Contenga solo caratteri alfanumerici (A-Z, 0-9)
    
    Args:
        code: Codice da validare
        min_length: Lunghezza minima (default: 8)
        max_length: Lunghezza massima (default: 20)
        
    Returns:
        True se il formato è valido, False altrimenti
    """
    if not code:
        return False
    
    code = code.strip()
    
    # Verifica lunghezza
    if len(code) < min_length or len(code) > max_length:
        return False
    
    # Verifica caratteri alfanumerici (solo maiuscole e cifre)
    if not re.match(r'^[A-Z0-9]+$', code):
        return False
    
    return True


def sanitize_qr_code(code: str) -> Optional[str]:
    """
    Pulisce e normalizza un codice QR.
    
    - Rimuove spazi iniziali/finali
    - Converte in maiuscolo
    - Rimuove caratteri non alfanumerici
    
    Args:
        code: Codice da sanitizzare
        
    Returns:
        Codice sanitizzato o None se non valido
    """
    if not code:
        return None
    
    # Rimuovi spazi e converti in maiuscolo
    sanitized = code.strip().upper()
    
    # Rimuovi caratteri non alfanumerici
    sanitized = re.sub(r'[^A-Z0-9]', '', sanitized)
    
    if not sanitized:
        return None
    
    return sanitized


def extract_qr_from_text(text: str) -> Optional[str]:
    """
    Estrae un codice QR da un testo che potrebbe contenere altri caratteri.
    
    Utile quando il QR viene letto da un'immagine o copiato con spazi/separatori.
    
    Args:
        text: Testo da cui estrarre il QR
        
    Returns:
        Codice QR estratto o None se non trovato
    """
    if not text:
        return None
    
    # Cerca sequenze alfanumeriche di lunghezza ragionevole (8-20 caratteri)
    matches = re.findall(r'[A-Z0-9]{8,20}', text.upper())
    
    if not matches:
        return None
    
    # Restituisci la prima sequenza trovata
    return matches[0]


# ─────────────────────────────────────────
# Esempio di utilizzo
# ─────────────────────────────────────────

if __name__ == "__main__":
    # Test validazione formato
    test_codes = [
        "A3B7C9D2E1",      # Valido
        "ABC123",          # Troppo corto
        "A3B7C9D2E1X",     # Valido
        "a3b7c9d2e1",      # Minuscole (da sanitizzare)
        "A3B-7C9",         # Con trattino (da sanitizzare)
        "A3B 7C9D2E1",     # Con spazio (da sanitizzare)
        "",                # Vuoto
    ]
    
    print("Test validazione formato:")
    for code in test_codes:
        valid = validate_qr_format(code)
        print(f"  '{code}' -> {valid}")
    
    print("\nTest sanitizzazione:")
    for code in test_codes:
        sanitized = sanitize_qr_code(code)
        print(f"  '{code}' -> '{sanitized}'")
    
    print("\nTest estrazione da testo:")
    test_texts = [
        "Il codice QR è A3B7C9D2E1",
        "QR: A3B7C9D2E1 - Cliente 123",
        "A3B-7C9 D2E1",
        "Nessun codice qui"
    ]
    for text in test_texts:
        extracted = extract_qr_from_text(text)
        print(f"  '{text}' -> '{extracted}'")

