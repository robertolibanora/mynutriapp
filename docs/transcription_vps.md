# Trascrizione audio — setup VPS

La feature diario usa Whisper in due modalità selezionabili da env
(`TRANSCRIPTION_PROVIDER`), **senza cambiare codice**.

| Valore | Implementazione | Dati sanitari |
|--------|-----------------|---------------|
| `local_whisper` (**default**) | `faster-whisper` self-hosted | Restano sul server |
| `openai_whisper` | OpenAI Whisper API | Escono dal server (solo fallback) |

Job asincroni: `JOB_BACKEND=thread` (BackgroundTasks in-process). Per Celery+Redis
basta implementare `CeleryJobRunner` in `app/services/jobs/__init__.py`.

---

## 1. Dipendenze Python

```bash
cd /var/www/mynutriapp
source venv/bin/activate
pip install -r requirements.txt
```

Pacchetti rilevanti: `faster-whisper`, `openai`, `mutagen`, `cryptography`.

---

## 2. Dipendenze di sistema (obbligatorie per local_whisper)

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

`faster-whisper` usa CTranslate2; su CPU conviene `WHISPER_COMPUTE_TYPE=int8`.

### RAM / modello consigliati

| `WHISPER_MODEL_SIZE` | RAM orientativa (CPU) | Qualità IT |
|----------------------|------------------------|------------|
| `tiny` / `base`      | ~1–2 GB                | bassa      |
| `small` (default)    | ~2–4 GB                | buona      |
| `medium`             | ~5–8 GB                | alta       |
| `large-v3`           | ≥10 GB / meglio GPU    | massima    |

Primo avvio: download automatico del modello (cache in
`~/.cache/huggingface` oppure `WHISPER_DOWNLOAD_ROOT`).

### GPU (opzionale)

```bash
# driver NVIDIA + CUDA compatibile con ctranslate2
export WHISPER_DEVICE=cuda
export WHISPER_COMPUTE_TYPE=float16
```

---

## 3. Variabili `.env`

```bash
TRANSCRIPTION_PROVIDER=local_whisper
TRANSCRIPTION_LANGUAGE=it
TRANSCRIPTION_MAX_ATTEMPTS=3
JOB_BACKEND=thread

WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

AUDIO_ENCRYPTION_KEY=...   # già richiesta dalla Fase 2
AUDIO_STORAGE_PATH=storage/audio
```

Fallback API (privacy: i colloqui lasciano il VPS):

```bash
TRANSCRIPTION_PROVIDER=openai_whisper
OPENAI_API_KEY=sk-...
OPENAI_WHISPER_MODEL=whisper-1
```

---

## 4. Migrazione DB

```bash
cd /var/www/mynutriapp
source venv/bin/activate
alembic upgrade head   # aggiunge consultation.errore_pipeline
```

---

## 5. Gunicorn / timeout

La trascrizione **non** avviene nella request HTTP (202 Accepted + job).
Non serve alzare `GUNICORN_TIMEOUT` per Whisper. Con `JOB_BACKEND=thread` il
lavoro gira nel worker Gunicorn: preferire pochi worker e abbastanza RAM, oppure
migrare a Celery quando il carico cresce.

---

## 6. Smoke test API

```bash
# dopo login (cookie di sessione) e upload audio
curl -X POST -b cookies.txt https://HOST/api/consultations/1/transcribe
curl -b cookies.txt https://HOST/api/consultations/1/status
```

Stati attesi: `CARICATO` → (job) → `TRASCRITTO` oppure `ERRORE` con `errore` valorizzato.
