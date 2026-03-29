FROM python:3.11-slim

WORKDIR /app

# Installa dipendenze di sistema necessarie per MMS-TTS
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia l'applicazione
COPY app.py .

# Esponi la porta
EXPOSE 8003

# Comando di avvio
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
