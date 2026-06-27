"""
QR Code Generator - Funzioni standalone per generazione QR code

Questo modulo contiene tutte le funzioni necessarie per generare QR code
senza dipendenze dal resto dell'applicazione MalibuApp.

Dipendenze:
    - qrcode[pil] (pip install qrcode[pil])
    - secrets, string, base64, io (standard library)
"""

import base64
import io
import secrets
import string
from typing import Optional

try:
    import qrcode
except ImportError:
    raise ImportError(
        "qrcode non installato. Esegui: pip install qrcode[pil]"
    )

# Alfabeto per codici alfanumerici (maiuscole + cifre)
ALPHABET = string.ascii_uppercase + string.digits

# Mappa per error correction levels (compatibile con qrcode 8.x)
ERROR_CORRECTION_MAP = {
    'L': qrcode.constants.ERROR_CORRECT_L,
    'M': qrcode.constants.ERROR_CORRECT_M,
    'Q': qrcode.constants.ERROR_CORRECT_Q,
    'H': qrcode.constants.ERROR_CORRECT_H,
}


def base36_checksum(s: str) -> str:
    """
    Calcola un checksum semplice su base 36 per validazione codice.
    
    Args:
        s: Stringa da cui calcolare il checksum
        
    Returns:
        Carattere checksum (A-Z, 0-9)
    """
    n = sum(ord(c) for c in s) % 36
    return ALPHABET[n]


def generate_short_code(length: int = 10) -> str:
    """
    Genera un codice alfanumerico corto con checksum.
    
    Il codice generato è formato da:
    - (length-1) caratteri casuali (A-Z, 0-9)
    - 1 carattere checksum
    
    Esempio: length=10 -> "A3B7C9D2E1" (9 caratteri + 1 checksum)
    
    Args:
        length: Lunghezza totale del codice (default: 10)
                Consigliato: 8-12 caratteri
        
    Returns:
        Codice alfanumerico con checksum
    """
    if length < 2:
        raise ValueError("La lunghezza deve essere almeno 2 (1 carattere + checksum)")
    
    # Genera core casuale
    core = ''.join(secrets.choice(ALPHABET) for _ in range(length - 1))
    
    # Aggiungi checksum
    checksum = base36_checksum(core)
    
    return core + checksum


def validate_short_code(code: str) -> bool:
    """
    Valida un codice corto verificando il checksum.
    
    Args:
        code: Codice da validare
        
    Returns:
        True se valido, False altrimenti
    """
    if not code or len(code) < 2:
        return False
    
    # Verifica che tutti i caratteri siano nell'alfabeto
    if not all(c in ALPHABET for c in code):
        return False
    
    # Estrai core e checksum
    core = code[:-1]
    provided_checksum = code[-1]
    
    # Calcola checksum atteso
    expected_checksum = base36_checksum(core)
    
    return provided_checksum == expected_checksum


def qr_data_url(text: str, error_correction: str = 'M') -> str:
    """
    Genera un QR code come data URL (base64) pronto per embed in HTML.
    
    Args:
        text: Testo da codificare nel QR code
        error_correction: Livello correzione errori ('L', 'M', 'Q', 'H')
                         L = ~7%, M = ~15%, Q = ~25%, H = ~30%
        
    Returns:
        Data URL nel formato: "data:image/png;base64,..."
    """
    if not text:
        raise ValueError("Il testo non può essere vuoto")
    
    # Configurazione QR code
    error_correction_level = ERROR_CORRECTION_MAP.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M)
    qr = qrcode.QRCode(
        version=1,
        error_correction=error_correction_level,
        box_size=10,
        border=4,
    )
    
    qr.add_data(text)
    qr.make(fit=True)
    
    # Genera immagine
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Converti in base64
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return f"data:image/png;base64,{b64}"


def qr_image_bytes(text: str, error_correction: str = 'M') -> bytes:
    """
    Genera un QR code come bytes PNG.
    
    Args:
        text: Testo da codificare nel QR code
        error_correction: Livello correzione errori ('L', 'M', 'Q', 'H')
        
    Returns:
        Bytes dell'immagine PNG
    """
    if not text:
        raise ValueError("Il testo non può essere vuoto")
    
    error_correction_level = ERROR_CORRECTION_MAP.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M)
    qr = qrcode.QRCode(
        version=1,
        error_correction=error_correction_level,
        box_size=10,
        border=4,
    )
    
    qr.add_data(text)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def qr_save_to_file(text: str, filepath: str, error_correction: str = 'M') -> None:
    """
    Salva un QR code direttamente su file.
    
    Args:
        text: Testo da codificare nel QR code
        filepath: Percorso del file dove salvare (es. "qr.png")
        error_correction: Livello correzione errori ('L', 'M', 'Q', 'H')
    """
    if not text:
        raise ValueError("Il testo non può essere vuoto")
    
    error_correction_level = ERROR_CORRECTION_MAP.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M)
    qr = qrcode.QRCode(
        version=1,
        error_correction=error_correction_level,
        box_size=10,
        border=4,
    )
    
    qr.add_data(text)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filepath)


# ─────────────────────────────────────────
# Esempio di utilizzo
# ─────────────────────────────────────────

if __name__ == "__main__":
    # Esempio 1: Genera codice corto
    code = generate_short_code(10)
    print(f"Codice generato: {code}")
    print(f"Valido: {validate_short_code(code)}")
    
    # Esempio 2: Genera QR code come data URL
    qr_url = qr_data_url(code)
    print(f"\nQR Data URL (primi 50 caratteri): {qr_url[:50]}...")
    
    # Esempio 3: Salva QR code su file
    qr_save_to_file(code, "test_qr.png")
    print("\nQR code salvato in test_qr.png")
    
    # Esempio 4: Genera QR code come bytes
    qr_bytes = qr_image_bytes(code)
    print(f"\nQR code come bytes: {len(qr_bytes)} bytes")

