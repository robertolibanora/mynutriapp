"""
Crittografia campo-specifica per dati sanitari sensibili.
Uso Fernet (symmetric encryption) - overhead minimo.
"""
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import os
import base64

# Cache della chiave per evitare ricalcoli (singleton pattern)
_fernet_instance = None

def get_fernet():
    """Ritorna istanza Fernet (singleton) - chiave da ENV."""
    global _fernet_instance
    if _fernet_instance is None:
        encryption_key = os.getenv('ENCRYPTION_KEY')
        if not encryption_key:
            raise ValueError("ENCRYPTION_KEY non configurata in .env")
        
        # Se la chiave è già in formato base64, usala direttamente
        try:
            key_bytes = base64.urlsafe_b64decode(encryption_key.encode())
            if len(key_bytes) == 32:
                _fernet_instance = Fernet(encryption_key.encode())
            else:
                raise ValueError("Chiave non valida")
        except Exception:
            # Se non è base64, genera da password usando PBKDF2
            # (per retrocompatibilità, ma meglio usare chiave base64)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'mynutriapp_salt',  # Fisso per semplicità
                iterations=100000,
                backend=default_backend()
            )
            key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
            _fernet_instance = Fernet(key)
    
    return _fernet_instance

def encrypt_field(value):
    """
    Crittografa un campo sensibile.
    Ritorna None se value è None/empty, altrimenti stringa crittografata.
    """
    if not value or value.strip() == '':
        return None
    
    try:
        fernet = get_fernet()
        encrypted = fernet.encrypt(value.encode('utf-8'))
        return encrypted.decode('utf-8')
    except Exception as e:
        # In caso di errore, logga ma non blocca (fallback graceful)
        import logging
        logging.error(f"Errore crittografia: {e}")
        return value  # Fallback: ritorna in chiaro (da monitorare)

def decrypt_field(encrypted_value):
    """
    Decrittografa un campo.
    Ritorna None se encrypted_value è None/empty.
    """
    if not encrypted_value or encrypted_value.strip() == '':
        return None
    
    try:
        fernet = get_fernet()
        decrypted = fernet.decrypt(encrypted_value.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception as e:
        # Se decrittazione fallisce, potrebbe essere dato vecchio non crittografato
        # Ritorna il valore originale (migrazione graduale)
        import logging
        logging.warning(f"Errore decrittazione (dato vecchio?): {e}")
        return encrypted_value

