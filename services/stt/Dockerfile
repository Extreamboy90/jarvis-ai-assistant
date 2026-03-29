FROM python:3.11-slim

WORKDIR /app

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    pkg-config \
    build-essential \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libavdevice-dev \
    libavfilter-dev \
    libswscale-dev \
    libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia l'applicazione
COPY app.py .

# Esponi la porta
EXPOSE 8001

# Comando di avvio
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
