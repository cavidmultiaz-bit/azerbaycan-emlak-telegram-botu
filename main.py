import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

import config
from bot.handlers import start_command, help_command, handle_text_message, handle_voice_message

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Starts the Azerbaycan Emlak Telegram Bot."""
    print("🚀 Azerbaycan Emlak Telegram Botu başlatılıyor...")
    
    # Validate environment configuration
    config.validate_config()
    
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN tanımlanmadığı için bot başlatılamıyor.")
        sys.exit(1)

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # Message Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))

    logger.info("Bot dinlemede... Ctrl+C ile durdurabilirsiniz.")
    app.run_polling()

if __name__ == "__main__":
    main()
