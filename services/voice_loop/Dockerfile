FROM python:3.11-slim

WORKDIR /app

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y \
    wget \
    ffmpeg \
    portaudio19-dev \
    alsa-utils \
    libasound2-dev \
    libportaudio2 \
    libportaudiocpp0 \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Installa Piper TTS
RUN pip install --no-cache-dir piper-tts

# Scarica modelli vocali Piper
RUN mkdir -p /models && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx \
    -O /models/it_IT-paola-medium.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx.json \
    -O /models/it_IT-paola-medium.onnx.json

# Copia requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia applicazione
COPY jarvis_loop.py .

# Esponi device audio
# Nota: richiede --device /dev/snd in docker-compose

CMD ["python", "-u", "jarvis_loop.py"]
