# QR Code Generator & Scanner - Modulo Standalone

Questo modulo contiene tutte le funzioni necessarie per generare e scansionare QR code, estratte dal progetto MalibuApp e ripulite da dipendenze specifiche.

## 📁 Struttura File

```
qr_standalone/
├── qr_generator.py      # Funzioni Python per generazione QR
├── qr_scanner.js        # Modulo JavaScript per scansione QR
├── qr_validator.py      # Funzioni di validazione QR
├── requirements.txt     # Dipendenze Python
└── README.md           # Questa documentazione
```

## 🐍 Backend Python

### Installazione

```bash
pip install -r requirements.txt
```

### Utilizzo

#### Generazione Codice QR

```python
from qr_generator import generate_short_code, qr_data_url, qr_save_to_file

# Genera un codice alfanumerico con checksum (lunghezza 10)
code = generate_short_code(10)
print(f"Codice generato: {code}")

# Genera QR code come data URL (per embed in HTML)
qr_url = qr_data_url(code)
# Usa qr_url in un tag <img src="...">

# Salva QR code direttamente su file
qr_save_to_file(code, "qr_code.png")

# Genera QR code come bytes
from qr_generator import qr_image_bytes
qr_bytes = qr_image_bytes(code)
```

#### Validazione Codice QR

```python
from qr_validator import validate_qr_format, sanitize_qr_code

# Valida formato
is_valid = validate_qr_format("A3B7C9D2E1", min_length=8, max_length=20)

# Sanitizza codice (rimuove spazi, converte maiuscole)
clean_code = sanitize_qr_code("  a3b-7c9  ")  # -> "A3B7C9"
```

### Funzioni Disponibili

#### `qr_generator.py`

- **`generate_short_code(length=10)`**: Genera codice alfanumerico con checksum
- **`base36_checksum(s)`**: Calcola checksum base36
- **`validate_short_code(code)`**: Valida codice verificando checksum
- **`qr_data_url(text, error_correction='M')`**: Genera QR come data URL
- **`qr_image_bytes(text, error_correction='M')`**: Genera QR come bytes PNG
- **`qr_save_to_file(text, filepath, error_correction='M')`**: Salva QR su file

#### `qr_validator.py`

- **`validate_qr_format(code, min_length=8, max_length=20)`**: Valida formato
- **`sanitize_qr_code(code)`**: Pulisce e normalizza codice
- **`extract_qr_from_text(text)`**: Estrae QR da testo misto

## 🌐 Frontend JavaScript

### Installazione

Il modulo JavaScript richiede la libreria `html5-qrcode`. Aggiungi nel tuo HTML:

```html
<!-- Libreria html5-qrcode (CDN) -->
<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>

<!-- Modulo scanner QR -->
<script src="qr_scanner.js"></script>
```

### Utilizzo Base

```html
<!DOCTYPE html>
<html>
<head>
    <title>QR Scanner</title>
</head>
<body>
    <!-- Container per lo scanner -->
    <div id="qr-reader"></div>
    
    <!-- Input hidden per il risultato -->
    <input type="hidden" id="qr-result">
    
    <!-- Input manuale (opzionale) -->
    <input type="text" id="qr-manual" placeholder="Inserisci QR manualmente">
    
    <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
    <script src="qr_scanner.js"></script>
    <script>
        // Inizializza scanner
        const scanner = initQrScanner('qr-reader', function(decodedText, result) {
            console.log('QR scansionato:', decodedText);
            // Fai qualcosa con il codice QR
        }, {
            resultInputId: 'qr-result',
            manualInputId: 'qr-manual'
        });
    </script>
</body>
</html>
```

### Utilizzo con Auto-Submit Form

```html
<form id="qr-form" method="POST" action="/process">
    <div id="qr-reader"></div>
    <input type="hidden" id="qr-result" name="qr">
    <input type="text" id="qr-manual" placeholder="QR manuale">
</form>

<script>
    // Scanner con auto-submit
    initQrScanner('qr-reader', null, {
        autoSubmit: true,
        formId: 'qr-form',
        resultInputId: 'qr-result',
        manualInputId: 'qr-manual',
        precheckUrl: '/api/qr/check',  // Opzionale: verifica prima di submit
        allowDuplicates: false
    });
</script>
```

### Opzioni Scanner

```javascript
const options = {
    autoSubmit: false,              // Submit automatico del form
    formId: 'my-form',              // ID del form da submitare
    resultInputId: 'qr-result',     // ID input hidden per risultato
    manualInputId: 'qr-manual',     // ID input manuale fallback
    allowDuplicates: false,          // Permetti scansioni duplicate
    precheckUrl: '/api/check',      // URL per precheck QR (opzionale)
    precheckMethod: 'POST',         // Metodo HTTP per precheck
    precheckPayloadKey: 'qr'        // Chiave nel payload precheck
};

const scanner = initQrScanner('container-id', onSuccess, options);
```

### Metodi Scanner

```javascript
// Ferma lo scanner
scanner.stop();

// Riavvia lo scanner
scanner.restart();

// Avvia lo scanner (se fermato)
scanner.start();
```

### Eventi Personalizzati

Il modulo emette un evento `qr-scanned` quando viene scansionato un QR:

```javascript
document.addEventListener('qr-scanned', function(event) {
    const qrCode = event.detail.code;
    const result = event.detail.result;
    console.log('QR scansionato:', qrCode);
});
```

## 🎨 Styling CSS (Opzionale)

Per uno styling completo, puoi aggiungere questi CSS:

```css
.qr-status {
    padding: 0.5rem;
    text-align: center;
    font-weight: bold;
    border-radius: 4px;
    margin-bottom: 1rem;
}

.qr-status--loading { background: #fff3cd; color: #856404; }
.qr-status--ready { background: #d1ecf1; color: #0c5460; }
.qr-status--success { background: #d4edda; color: #155724; }
.qr-status--error { background: #f8d7da; color: #721c24; }

.qr-toast {
    position: fixed;
    top: 20px;
    right: 20px;
    background: white;
    padding: 1rem;
    border-radius: 8px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    opacity: 0;
    transform: translateX(100%);
    transition: all 0.3s ease;
}

.qr-toast--visible {
    opacity: 1;
    transform: translateX(0);
}

.qr-error {
    padding: 1rem;
    background: #f8d7da;
    color: #721c24;
    border-radius: 4px;
    margin-top: 1rem;
}
```

## 🔒 Requisiti di Sicurezza

- **HTTPS**: La camera richiede HTTPS (o localhost) per funzionare
- **Permessi**: Il browser richiederà permessi per accedere alla camera
- **Validazione**: Sempre validare i QR code lato server prima di processarli

## 📝 Note

- Il modulo previene automaticamente doppie scansioni (2 secondi di delay)
- Supporta feedback sonoro (beep) e tattile (vibrazione) su dispositivi mobile
- Include fallback per input manuale se la camera non è disponibile
- Compatibile con tutti i browser moderni che supportano WebRTC

## 🚀 Esempi Completi

Vedi i commenti nei file sorgente per esempi di utilizzo dettagliati.

## 📄 Licenza

Questo codice è estratto dal progetto MalibuApp. Usa liberamente nei tuoi progetti.

