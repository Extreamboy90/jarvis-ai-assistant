#!/usr/bin/env python3
"""
Telegram Bot for AI Assistant
Handles voice messages and text messages
"""

import os
import logging
import tempfile
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurazione
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", "http://stt:8001")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://tts:8002")

# Comandi del bot

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Ciao {user.first_name}! 👋\n\n"
        "Sono Jarvis, il tuo assistente AI personale.\n\n"
        "Puoi:\n"
        "• Scrivermi messaggi di testo\n"
        "• Inviarmi messaggi vocali\n"
        "• Chiedermi di controllare dispositivi smart\n"
        "• Chiedere informazioni di sistema\n\n"
        "Comandi disponibili:\n"
        "/start - Mostra questo messaggio\n"
        "/help - Aiuto\n"
        "/clear - Cancella cronologia conversazione\n"
        "/functions - Mostra funzioni disponibili"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /help"""
    await update.message.reply_text(
        "🤖 *Jarvis AI Assistant*\n\n"
        "*Cosa posso fare:*\n"
        "• Rispondere alle tue domande\n"
        "• Controllare dispositivi Tuya\n"
        "• Eseguire comandi di sistema\n"
        "• Fornirti informazioni in tempo reale\n\n"
        "*Come usarmi:*\n"
        "Inviami un messaggio testuale o vocale e ti risponderò!\n\n"
        "*Esempi:*\n"
        "- \"Che ore sono?\"\n"
        "- \"Accendi la luce del salotto\"\n"
        "- \"Quali dispositivi smart ho?\"\n"
        "- \"Come sta il sistema?\"",
        parse_mode="Markdown"
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /clear"""
    user_id = str(update.effective_user.id)
    try:
        response = requests.delete(f"{ORCHESTRATOR_URL}/conversation/{user_id}")
        if response.status_code == 200:
            await update.message.reply_text("✅ Cronologia conversazione cancellata!")
        else:
            await update.message.reply_text("❌ Errore durante la cancellazione della cronologia")
    except Exception as e:
        logger.error(f"Error clearing conversation: {e}")
        await update.message.reply_text(f"❌ Errore: {str(e)}")

async def functions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per il comando /functions"""
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/functions")
        if response.status_code == 200:
            functions = response.json().get("functions", [])
            if functions:
                text = "🔧 *Funzioni disponibili:*\n\n"
                for func in functions:
                    text += f"• *{func['name']}*\n  {func['description']}\n\n"
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.message.reply_text("Nessuna funzione disponibile")
        else:
            await update.message.reply_text("❌ Errore nel recupero delle funzioni")
    except Exception as e:
        logger.error(f"Error getting functions: {e}")
        await update.message.reply_text(f"❌ Errore: {str(e)}")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per messaggi di testo"""
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    logger.info(f"Text message from {user_id}: {user_message}")

    # Mostra "sta scrivendo..."
    await update.message.chat.send_action("typing")

    try:
        # Invia messaggio all'orchestrator con timeout aumentato
        response = requests.post(
            f"{ORCHESTRATOR_URL}/chat",
            json={
                "message": user_message,
                "user_id": user_id
            },
            timeout=120  # Aumentato a 2 minuti per modelli smart
        )
        response.raise_for_status()

        data = response.json()
        ai_response = data.get("response", "Mi dispiace, non ho potuto elaborare la tua richiesta.")

        # Invia risposta testuale
        await update.message.reply_text(ai_response)

        # Se richiesto, genera anche audio della risposta
        # (opzionale, commentato per ora per non rallentare)
        # await send_voice_response(update, ai_response)

    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        await update.message.reply_text(f"❌ Mi dispiace, si è verificato un errore: {str(e)}")

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per messaggi vocali"""
    user_id = str(update.effective_user.id)

    logger.info(f"Voice message from {user_id}")

    # Mostra "sta registrando audio..."
    await update.message.chat.send_action("record_voice")

    try:
        # Scarica il file audio
        voice_file = await update.message.voice.get_file()

        # Salva temporaneamente
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_audio:
            await voice_file.download_to_drive(tmp_audio.name)
            audio_path = tmp_audio.name

        logger.info(f"Audio saved to {audio_path}")

        # Mostra "sta scrivendo..."
        await update.message.chat.send_action("typing")

        # Trascrivi audio con STT
        with open(audio_path, "rb") as audio_file:
            stt_response = requests.post(
                f"{STT_SERVICE_URL}/transcribe",
                files={"audio": audio_file},
                timeout=30
            )
            stt_response.raise_for_status()

        transcription = stt_response.json().get("text", "")
        logger.info(f"Transcription: {transcription}")

        if not transcription:
            await update.message.reply_text("❌ Non ho capito il messaggio vocale")
            os.unlink(audio_path)
            return

        # Mostra la trascrizione
        await update.message.reply_text(f"🎤 _{transcription}_", parse_mode="Markdown")

        # Invia all'orchestrator
        await update.message.chat.send_action("typing")
        chat_response = requests.post(
            f"{ORCHESTRATOR_URL}/chat",
            json={
                "message": transcription,
                "user_id": user_id
            },
            timeout=60
        )
        chat_response.raise_for_status()

        data = chat_response.json()
        ai_response = data.get("response", "Mi dispiace, non ho potuto elaborare la tua richiesta.")

        # Invia risposta testuale
        await update.message.reply_text(ai_response)

        # Genera e invia risposta vocale
        await send_voice_response(update, ai_response)

        # Rimuovi file temporaneo
        os.unlink(audio_path)

    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await update.message.reply_text(f"❌ Errore nell'elaborazione del messaggio vocale: {str(e)}")

async def send_voice_response(update: Update, text: str):
    """Genera e invia risposta vocale"""
    try:
        # Mostra "sta registrando audio..."
        await update.message.chat.send_action("record_voice")

        # Genera audio con TTS
        tts_response = requests.post(
            f"{TTS_SERVICE_URL}/speak",
            json={"text": text, "speed": 1.0},
            timeout=30
        )
        tts_response.raise_for_status()

        # Salva audio temporaneamente
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_voice:
            tmp_voice.write(tts_response.content)
            voice_path = tmp_voice.name

        # Invia messaggio vocale
        with open(voice_path, "rb") as voice_file:
            await update.message.reply_voice(voice=voice_file)

        # Rimuovi file temporaneo
        os.unlink(voice_path)

    except Exception as e:
        logger.error(f"Error sending voice response: {e}")
        # Non fallire se TTS non funziona, abbiamo già inviato il testo

def main():
    """Start the bot"""
    logger.info("Starting Telegram Bot...")

    # Crea l'applicazione
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registra handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("functions", functions_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Avvia il bot
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
