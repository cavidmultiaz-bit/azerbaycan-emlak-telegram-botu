import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env or anahtar.env
BASE_DIR = Path(__file__).resolve().parent
if (BASE_DIR / "anahtar.env").exists():
    load_dotenv(BASE_DIR / "anahtar.env")
else:
    load_dotenv(BASE_DIR / ".env")

MASTER_ENV = BASE_DIR.parent.parent / "_knowledge" / "credentials" / "master.env"
if MASTER_ENV.exists():
    load_dotenv(MASTER_ENV)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

MAX_RESULTS_PER_SITE = int(os.getenv("MAX_RESULTS_PER_SITE", "5"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
TEMP_AUDIO_DIR = BASE_DIR / "temp_audio"

def validate_config():
    """Verify that required API tokens are present."""
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not OPENAI_API_KEY and not GROQ_API_KEY:
        missing.append("OPENAI_API_KEY (or GROQ_API_KEY)")
    
    if missing:
        print(f"⚠️ DİKKAT: Eksik ortam değişkenleri: {', '.join(missing)}")
        print("Lütfen .env dosyanızı güncelleyin veya _knowledge/credentials/master.env dosyasına ekleyin.")
        return False
    return True
