FROM python:3.11-slim

WORKDIR /app

# Installa dipendenze di sistema e Piper TTS
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Installa Piper TTS
RUN pip install --no-cache-dir piper-tts

# Crea directory per i modelli vocali
RUN mkdir -p /models

# Scarica modelli vocali italiani
# Riccardo x_low (voce maschile - backup)
RUN wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx \
    -O /models/it_IT-riccardo-x_low.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx.json \
    -O /models/it_IT-riccardo-x_low.onnx.json

# Paola medium (voce femminile - qualità superiore)
RUN wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx \
    -O /models/it_IT-paola-medium.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium/it_IT-paola-medium.onnx.json \
    -O /models/it_IT-paola-medium.onnx.json

# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia l'applicazione
COPY app.py .

# Esponi la porta
EXPOSE 8002

# Comando di avvio
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
