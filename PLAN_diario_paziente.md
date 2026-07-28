# Piano: Diario del paziente

> Feature: il paziente registra messaggi audio sul proprio diario alimentare/comportamentale;
> Whisper trascrive; Claude estrae una struttura; il nutrizionista revisiona e conferma;
> entrambi vedono una timeline.

**Stack reale del progetto (importante):** Flask 3 + MySQL 8 (PyMySQL) + Jinja2 SSR,
auth a sessione cookie, migrazioni custom via `db_schema.py` (niente Alembic).
**Non** FastAPI/PostgreSQL come ipotizzato inizialmente — il piano segue le convenzioni già in uso.

**Stato attuale:** NON esiste alcun modulo diario, audio, trascrizione o integrazione Claude/Whisper.
Pattern riutilizzabili: upload documenti (`documenti.py`), `UPLOAD_FOLDERS`, servizi in `app/services/`,
blueprint HTML + eventuali JSON sotto `/api/admin`, `ensure_*` in `db_schema.py`.

---

## Premesse architetturali (decisioni da confermare in review)

| Decisione | Proposta | Alternativa |
|-----------|----------|-------------|
| Persistenza voci | Tabella `diario_voci` + file audio in `static/uploads/diario/` | Solo JSON blob |
| Stati pipeline | `uploaded` → `transcribing` → `transcribed` → `extracting` → `pending_review` → `confirmed` / `rejected` (+ `failed`) | Stati più grezzi |
| Processing async | Job in-process / thread o coda Redis (già presente) | Sincrono nella request (rischioso: timeout Gunicorn 30s) |
| Chi carica audio | Paziente (`role=user`) dal proprio account | Anche admin per conto del paziente |
| Chi conferma | Solo `admin` (nutrizionista) | — |
| Vista timeline | Template Jinja admin + user (come progressi/documenti) | SPA separata (fuori scope) |
| Whisper | OpenAI Whisper API (HTTP) | Whisper locale (CPU/GPU VPS) |
| Claude | Anthropic Messages API | — |

**Dipendenze nuove previste (aggregate):** `openai` e/o client HTTP già coperto da `requests`; `anthropic`.
Eventuale `celery`/`rq` solo se si sceglie coda vera — altrimenti worker minimale su Redis o thread + stato DB.

**Config env nuove (da aggiungere a `.env.example` / `Config`):**
`OPENAI_API_KEY` (o path modello locale), `ANTHROPIC_API_KEY`, `WHISPER_MODEL`,
`DIARIO_MAX_AUDIO_MB`, `DIARIO_ALLOWED_MIME`, flag `DIARIO_ASYNC_ENABLED`.

---

## Fase 1 — Modelli + migrazione DB

### Stato: IMPLEMENTATA (2026-07-29)

### Scelte rispetto allo schema richiesto
- **Niente seconda tabella `patient`**: si riusa `patients` (già in produzione), estesa con
  `email`, `nutrizionista_id`, consensi, `aggiornato_il`. `creato_il` è property su `data_creazione`.
- **Tabella `utente`**: necessaria per FK `nutrizionista_id` / `revisionato_da` (prima non esisteva).
- **JSONB → JSON** MySQL 8.
- **Alembic** introdotto (`alembic.ini`, `migrations/`); revision `20260729_diario_01`.
- Enum Python: `ConsultationStato` in `app/models/enums.py`.
- Schemi Pydantic: `app/schemas/diario.py`.

### File toccati
- `app/models/enums.py`, `app/models/diario.py`, `app/models/models.py`, `app/models/__init__.py`
- `app/schemas/diario.py`
- `migrations/versions/20260729_diario_01.py`, `migrations/env.py`, `alembic.ini`
- `init.sql`, `requirements.txt`, `wsgi.py`

### Come testare la migrazione in locale

```bash
cd /var/www/mynutriapp
source venv/bin/activate
pip install -r requirements.txt

# Stato corrente
alembic current
alembic history

# Upgrade (usa DB di .env; verifica il log "[alembic] target database: ...")
alembic upgrade head

# Downgrade + re-upgrade (ATTENZIONE: sul DB di .env)
alembic downgrade base
alembic upgrade head

# DB dedicato (consigliato): crea lo schema baseline patients, poi
export ALEMBIC_DATABASE_URI='mysql+pymysql://USER:PASS@127.0.0.1:3306/mynutriapp_alembic_test?charset=utf8mb4'
alembic upgrade head
alembic downgrade base
alembic upgrade head
unset ALEMBIC_DATABASE_URI
```

### Obiettivo (storico)
Definire lo schema delle voci di diario e renderlo applicabile su installazioni esistenti.
**Aggiornamento:** ora si usa Alembic (non solo `db_schema.ensure_*`).

---

## Fase 2 — Endpoint upload e storage audio

### Stato: IMPLEMENTATA (2026-07-29)

Upload da **nutrizionista proprietario** (non dal paziente):
- `POST /api/consultations/{id}/audio`
- `DELETE /api/consultations/{id}/audio` (soft delete: file + `cancellato_il`)

Storage: `{AUDIO_STORAGE_PATH}/{patient_id}/{consultation_id}/{uuid}.ext.enc`
Cifratura AES-256-CTR+HMAC streaming; `cifrato=True`; SHA-256 del plaintext; durata reale;
`consultation.stato → CARICATO`. Ownership via `session['utente_id']`.

### File
- `app/utils/audio_crypto.py`, `app/services/diario_audio_service.py`
- `app/routes/consultations_audio.py`, config/env, `tests/test_consultation_audio.py`

### Test
`venv/bin/python -m unittest tests.test_consultation_audio -v`

### Obiettivo (storico)
Il paziente (e opzionalmente admin) carica un file audio; viene salvato su disco e creato un record in stato caricato.

### File toccati (storico piano)
- `app/config/config.py` — `AUDIO_STORAGE_PATH`, MIME, size
- `.env.example` — `AUDIO_*`
- route/service audio consultation

### Dipendenze nuove
`mutagen` (durata). `cryptography` già presente.

### Rischi
- Storage fuori da `static/` pubblico (ok: `storage/audio`).
- Sessione admin senza riga `utente` → manca `utente_id` (re-login dopo seed utente).
- Upload grandi vs timeout Gunicorn.

### Cosa testare
- Upload valido, MIME errato, size, consenso, non-proprietario (coperti dai unit test).

---

## Fase 3 — Integrazione trascrizione (Whisper)

### Stato: IMPLEMENTATA (2026-07-29)

- ABC `Transcriber` + `LocalWhisperTranscriber` (default) + `OpenAIWhisperTranscriber`
- Scelta via `TRANSCRIPTION_PROVIDER` (env)
- Job async: `BackgroundTasks` + `JOB_BACKEND=thread|sync|celery`
- Decrypt temp → transcribe → `finally` unlink; retry backoff max 3
- `POST .../transcribe` (202), `GET .../status`
- Docs VPS: `docs/transcription_vps.md`

### Test
`venv/bin/python -m unittest tests.test_consultation_transcription -v`

### Obiettivo (storico)
Portare una voce da caricato a trascritto; gestire failure.

### File
- `app/services/transcription/*`, `diario_transcription_service.py`, `jobs/`
- `app/routes/consultations_audio.py`, migration `20260729_diario_02`

### Dipendenze
`faster-whisper`, `openai` (+ `ffmpeg` di sistema per local)

### Rischi
- RAM modello locale; privacy se si usa API OpenAI
- Thread in-process vs Celery sotto carico

### Cosa testare
- Successo, retry transient, errore permanente, factory provider (unit test)

---

## Fase 4 — Estrazione strutturata via Claude API

### Stato: IMPLEMENTATA (2026-07-29)

- Schema Pydantic `DiaryExtractionSchema`
- Anonimizzazione `[PAZIENTE]` → restore post-risposta
- `ClaudeDiaryExtractor` (Haiku default, `CLAUDE_DIARY_MODEL` override)
- Retry parse 1× poi `ERRORE` senza salvare JSON parziale
- `POST /api/consultations/{id}/extract` → `diary_entry` + stato `ELABORATO`
- Chiave `ANTHROPIC_API_KEY` redacted nei log/errori

### Test
`venv/bin/python -m unittest tests.test_diary_extraction -v`

### Obiettivo (storico)
Da trascrizione produrre JSON validato e portare lo stato a elaborato/review.

---

## Fase 5 — Flusso di revisione e conferma del nutrizionista

### Stato: IMPLEMENTATA (2026-07-29)

API:
- `GET/PATCH /api/consultations/{id}/diary`
- `POST .../diary/confirm` · `POST .../diary/reject` (rigenera)
- `PATCH .../diary/post-confirm` (correzioni post-CONFERMATO)

Flag risposta: `da_revisionare`, `confermato`, `valido_storico`.

UI:
- `/admin/diario/consultations/{id}/review` (trascrizione | campi | Conferma/Rigenera)
- `/admin/diario/pazienti/{id}` + link da scheda paziente

### Test
`venv/bin/python -m unittest tests.test_diary_review -v`

---

## Fase 6 — Vista timeline del diario

### Stato: IMPLEMENTATA (2026-07-29)

API:
- `GET /api/patients/{id}/diary` — CONFERMATE default, `include_pending`, `from`/`to`, paginazione
- `GET /api/patients/{id}/diary/trends` — serie peso/misure (skip null)

UI: `/admin/diario/pazienti/{id}/timeline` (timeline espandibile + Chart.js peso)

### Test
`venv/bin/python -m unittest tests.test_diary_timeline -v`

---

## Ordine di delivery consigliato

```
Fase 1 (DB) → Fase 2 (upload) → Fase 3 (Whisper) → Fase 4 (Claude)
    → Fase 5 (review) → Fase 6 (timeline)
```

Fasi 5 e 6 possono sovrapporsi in parte (lista review + timeline admin condividono query).
Fasi 3–4 condividono il worker di pipeline: implementare lo scheletro async già in fase 3.

## Fuori scope (esplicito)

- Matching automatico alimenti ↔ catalogo `foods` / USDA
- App mobile nativa
- Multi-nutrizionista / tabella `professionals` (ancora assente nel progetto)
- Migrazione a FastAPI/PostgreSQL
- Eliminazione automatica audio post-conferma (policy retention da definire a parte)

## Criteri di “fatto” end-to-end

1. Paziente carica audio → appare in elaborazione.
2. Pipeline completa (mock o API reali in staging) → `pending_review`.
3. Admin conferma → voce in timeline paziente/admin.
4. ACL e assenza di URL audio pubblici verificati.
5. Nessuna chiave API committata; `.env.example` aggiornato.
