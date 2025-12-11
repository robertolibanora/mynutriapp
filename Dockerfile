# ========================================
# 🐳 DOCKERFILE PER MYNUTRIAPP
# Python 3.13 + Flask + Gunicorn
# ========================================

FROM python:3.13-slim

# Imposta variabili d'ambiente per ottimizzazione
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=wsgi.py
ENV FLASK_ENV=production

# Installa dipendenze di sistema necessarie per MySQL
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Crea directory di lavoro
WORKDIR /app

# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice dell'applicazione
COPY . .

# Crea utente non-root per sicurezza
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Espone la porta 8000
EXPOSE 8000

# Comando di avvio con Gunicorn (4 workers per performance)
# Usa wsgi.py:app per evitare conflitto con directory app/
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
