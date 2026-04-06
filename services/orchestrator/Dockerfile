FROM python:3.11-slim

WORKDIR /app

# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia l'applicazione e i plugins
COPY app.py .
COPY database.py .
COPY memory.py .
COPY gemini_client.py .
COPY telegram_bot.py .
COPY voice_websocket.py .
COPY plugins/ ./plugins/
COPY db/ ./db/

# Esponi la porta
EXPOSE 8000

# Comando di avvio (viene overridden nel docker-compose per bot/api)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
