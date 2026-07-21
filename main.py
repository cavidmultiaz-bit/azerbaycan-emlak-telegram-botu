import os
import sys
import json
import logging
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode, ChatAction

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "anahtar.env")
load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MAX_RESULTS_PER_SITE = int(os.getenv("MAX_RESULTS_PER_SITE", "5"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
TEMP_AUDIO_DIR = BASE_DIR / "temp_audio"

# --- DATA MODELS ---
class Listing(BaseModel):
    title: str
    price: str
    location: str
    rooms: str | None = None
    area: str | None = None
    url: str
    image_url: str | None = None
    source: str

class PropertySearchParams(BaseModel):
    intent: str = Field(description="'kiraye' if renting, 'satiliq' if buying/selling, 'unknown' if not clear")
    property_type: str = Field(description="'menzil' for apartment, 'heyet_evi' for house/villa, 'ofis' for office, 'torpaq' for land, 'all' for any")
    city_region: str | None = Field(default=None, description="City or district name in Azerbaijan e.g. Bakı, Nəsimi, Yasamal, Nizami, Xırdalan, Gəncə")
    min_price: float | None = Field(default=None, description="Minimum price in AZN")
    max_price: float | None = Field(default=None, description="Maximum price in AZN")
    rooms: int | None = Field(default=None, description="Number of rooms e.g. 1, 2, 3, 4")
    raw_query: str = Field(description="Normalized search phrase in Azerbaijani")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "az,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

# --- SCRAPERS ---
def search_tap_az(params: PropertySearchParams) -> list[Listing]:
    listings = []
    query_parts = []
    if params.city_region: query_parts.append(params.city_region)
    if params.rooms: query_parts.append(f"{params.rooms} otaqli")
    if params.intent == "kiraye": query_parts.append("kiraye")
    elif params.intent == "satiliq": query_parts.append("satiliq")
    if not query_parts and params.raw_query: query_parts.append(params.raw_query)

    search_query = " ".join(query_parts) if query_parts else "emlak"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://tap.az/elanlar/emlak?q%5Bkeywords%5D={encoded_query}"
    
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".products-i")
                for item in items[:MAX_RESULTS_PER_SITE]:
                    link_el = item.select_one("a.products-i__link")
                    title_el = item.select_one(".products-i__name")
                    price_el = item.select_one(".price-val")
                    img_el = item.select_one(".products-i__top img")
                    city_el = item.select_one(".products-i__datetime")
                    if not link_el or not title_el: continue
                    
                    item_url = "https://tap.az" + link_el.get("href", "")
                    title = title_el.get_text(strip=True)
                    price = price_el.get_text(strip=True) + " AZN" if price_el else "Qiymət belirtilməyib"
                    image_url = img_el.get("src") or img_el.get("data-src") if img_el else None
                    location = city_el.get_text(strip=True) if city_el else (params.city_region or "Bakı")
                    
                    listings.append(Listing(
                        title=title, price=price, location=location,
                        rooms=f"{params.rooms} otaqlı" if params.rooms else None,
                        url=item_url, image_url=image_url, source="tap.az"
                    ))
    except Exception as e:
        logger.error(f"Error tap.az: {e}")
    return listings

def search_arenda_az(params: PropertySearchParams) -> list[Listing]:
    listings = []
    query_parts = []
    if params.city_region: query_parts.append(params.city_region)
    if params.rooms: query_parts.append(f"{params.rooms} otaqli")
    if params.intent == "kiraye": query_parts.append("kiraye")
    elif params.intent == "satiliq": query_parts.append("satiliq")
    if not query_parts and params.raw_query: query_parts.append(params.raw_query)

    search_query = " ".join(query_parts) if query_parts else "ev"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://arenda.az/axtarish?keyword={encoded_query}"
    
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".product-item, .item-card, .flat-item, .post-item, div[class*='item']")
                for item in items[:MAX_RESULTS_PER_SITE]:
                    link_el = item.select_one("a[href*='/']")
                    title_el = item.select_one(".title, .name, h2, h3, .heading")
                    price_el = item.select_one(".price, .cost, .val")
                    img_el = item.select_one("img")
                    location_el = item.select_one(".location, .address, .city")
                    if not link_el or not title_el: continue
                    
                    href = link_el.get("href", "")
                    item_url = href if href.startswith("http") else f"https://arenda.az{href}"
                    title = title_el.get_text(strip=True)
                    price = price_el.get_text(strip=True) if price_el else "Razılaşma yolu ilə"
                    image_url = img_el.get("src") or img_el.get("data-src") if img_el else None
                    if image_url and not image_url.startswith("http"): image_url = "https://arenda.az" + image_url
                    location = location_el.get_text(strip=True) if location_el else (params.city_region or "Bakı")
                    
                    listings.append(Listing(
                        title=title, price=price, location=location,
                        rooms=f"{params.rooms} otaqlı" if params.rooms else None,
                        url=item_url, image_url=image_url, source="arenda.az"
                    ))
    except Exception as e:
        logger.error(f"Error arenda.az: {e}")
    return listings

def search_emlak_az(params: PropertySearchParams) -> list[Listing]:
    listings = []
    query_parts = []
    if params.city_region: query_parts.append(params.city_region)
    if params.rooms: query_parts.append(f"{params.rooms} otaqli")
    if params.intent == "kiraye": query_parts.append("kiraye")
    elif params.intent == "satiliq": query_parts.append("satiliq")
    if not query_parts and params.raw_query: query_parts.append(params.raw_query)

    search_query = " ".join(query_parts) if query_parts else "mənzil"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://emlak.az/search?q={encoded_query}"
    
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".listing-item, .post-block, .item, tr.item")
                for item in items[:MAX_RESULTS_PER_SITE]:
                    link_el = item.select_one("a[href*='/']")
                    title_el = item.select_one(".title, .name, td.title, h3")
                    price_el = item.select_one(".price, td.price")
                    img_el = item.select_one("img")
                    location_el = item.select_one(".location, .city, td.location")
                    if not link_el: continue
                    
                    href = link_el.get("href", "")
                    item_url = href if href.startswith("http") else f"https://emlak.az{href}"
                    title = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)
                    if not title or len(title) < 3: title = f"İlan #{item_url.split('/')[-1]}"
                    price = price_el.get_text(strip=True) if price_el else "Əlaqə saxlayın"
                    image_url = img_el.get("src") or img_el.get("data-src") if img_el else None
                    if image_url and not image_url.startswith("http"): image_url = "https://emlak.az" + image_url
                    location = location_el.get_text(strip=True) if location_el else (params.city_region or "Bakı")
                    
                    listings.append(Listing(
                        title=title, price=price, location=location,
                        rooms=f"{params.rooms} otaqlı" if params.rooms else None,
                        url=item_url, image_url=image_url, source="emlak.az"
                    ))
    except Exception as e:
        logger.error(f"Error emlak.az: {e}")
    return listings

def search_yeniemlak_az(params: PropertySearchParams) -> list[Listing]:
    listings = []
    query_parts = []
    if params.city_region: query_parts.append(params.city_region)
    if params.rooms: query_parts.append(f"{params.rooms} otaqli")
    if params.intent == "kiraye": query_parts.append("kiraye")
    elif params.intent == "satiliq": query_parts.append("satiliq")
    if not query_parts and params.raw_query: query_parts.append(params.raw_query)

    search_query = " ".join(query_parts) if query_parts else "ev"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://yeniemlak.az/elan/axtar?keyword={encoded_query}"
    
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".elan-item, .item-card, .list-item, div[id*='elan']")
                for item in items[:MAX_RESULTS_PER_SITE]:
                    link_el = item.select_one("a[href*='/elan/']") or item.select_one("a")
                    title_el = item.select_one(".title, .name, h3, .heading")
                    price_el = item.select_one(".price, .qiymet")
                    img_el = item.select_one("img")
                    location_el = item.select_one(".location, .unvan")
                    if not link_el: continue
                    
                    href = link_el.get("href", "")
                    item_url = href if href.startswith("http") else f"https://yeniemlak.az{href}"
                    title = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)
                    if not title or len(title) < 3: title = f"Yeni Emlak İlanı ({item_url.split('/')[-1]})"
                    price = price_el.get_text(strip=True) if price_el else "Qiymət zənglə"
                    image_url = img_el.get("src") or img_el.get("data-src") if img_el else None
                    if image_url and not image_url.startswith("http"): image_url = "https://yeniemlak.az" + image_url
                    location = location_el.get_text(strip=True) if location_el else (params.city_region or "Bakı")
                    
                    listings.append(Listing(
                        title=title, price=price, location=location,
                        rooms=f"{params.rooms} otaqlı" if params.rooms else None,
                        url=item_url, image_url=image_url, source="yeniemlak.az"
                    ))
    except Exception as e:
        logger.error(f"Error yeniemlak.az: {e}")
    return listings

def fetch_all_listings(params: PropertySearchParams) -> list[Listing]:
    scrapers = [
        ("tap.az", search_tap_az),
        ("arenda.az", search_arenda_az),
        ("emlak.az", search_emlak_az),
        ("yeniemlak.az", search_yeniemlak_az),
    ]
    all_results = []
    seen_urls = set()
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_source = {executor.submit(func, params): name for name, func in scrapers}
        for future in as_completed(future_to_source):
            try:
                results = future.result()
                for item in results:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_results.append(item)
            except Exception as e:
                logger.error(f"Scraper execution error: {e}")
    return all_results

# --- AI SERVICES ---
SYSTEM_PROMPT = """Sən Azərbaycan emlak arama asistanısan. İstifadəçinin yazdığı və ya səsli mesajdan çevrilmiş mətni analiz edib emlak axtarış parametrlərini JSON formatında çıxarmalısan.
JSON Formadı:
{
  "intent": "kiraye" | "satiliq" | "unknown",
  "property_type": "menzil" | "heyet_evi" | "ofis" | "torpaq" | "all",
  "city_region": "Bakı" | "Nəsimi" | "Yasamal" | "Nizami" | "Xırdalan" | null,
  "min_price": number | null,
  "max_price": number | null,
  "rooms": number | null,
  "raw_query": "Axtarış üçün qısa açar sözlər"
}"""

def transcribe_audio(audio_path: str | Path) -> str:
    if not OPENAI_API_KEY: raise ValueError("OPENAI_API_KEY missing.")
    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", file=audio_file, language="az",
            prompt="Emlak araması: ev satışı, kirayə ev, mənzil, otaq, Qiymət AZN Bakı"
        )
    return transcript.text.strip()

def parse_user_request(text: str) -> PropertySearchParams:
    if not OPENAI_API_KEY: raise ValueError("OPENAI_API_KEY missing.")
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
            temperature=0.1
        )
        data = json.loads(response.choices[0].message.content)
        return PropertySearchParams(**data)
    except Exception as e:
        logger.error(f"Error parsing user query: {e}")
        return PropertySearchParams(
            intent="satiliq" if "sat" in text.lower() else ("kiraye" if "kiray" in text.lower() else "unknown"),
            property_type="all", city_region=None, min_price=None, max_price=None, rooms=None, raw_query=text
        )

# --- FORMATTERS ---
def format_parsed_params_summary(params: PropertySearchParams) -> str:
    intent_str = "Kirayə" if params.intent == "kiraye" else ("Satılıq" if params.intent == "satiliq" else "Axtarış")
    type_str = {"menzil": "Mənzil", "heyet_evi": "Həyət evi", "ofis": "Ofis", "torpaq": "Torpaq"}.get(params.property_type, "Mənzil")
    details = []
    if params.city_region: details.append(f"📍 **Ərazi:** {params.city_region}")
    if params.rooms: details.append(f"🚪 **Otaq:** {params.rooms} otaqlı")
    if params.max_price: details.append(f"💰 **Maks. Qiymət:** {int(params.max_price)} AZN")
    details_text = " | ".join(details) if details else "Ümumi axtarış"
    return f"🔍 **Axtarış Anlaşıldı:** {intent_str} {type_str}\n{details_text}"

def format_listing_message(listing: Listing) -> str:
    source_badge = {"tap.az": "🔵 tap.az", "arenda.az": "🟢 arenda.az", "emlak.az": "🔴 emlak.az", "yeniemlak.az": "🟠 yeniemlak.az"}.get(listing.source, listing.source)
    msg = f"🏠 <b>{listing.title}</b>\n\n💵 <b>Qiymət:</b> {listing.price}\n📍 <b>Ünvan:</b> {listing.location}\n"
    if listing.rooms: msg += f"🚪 <b>Otaq:</b> {listing.rooms}\n"
    msg += f"🌐 <b>Mənbə:</b> {source_badge}\n🔗 <a href='{listing.url}'>İlana saytda baxmaq üçün toxunun</a>"
    return msg

# --- TELEGRAM HANDLERS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🏡 <b>Azerbaycan Emlak Arama Botuna Hoş Geldiniz!</b>\n\n"
        "1. 💬 <b>Yazılı mesaj gönderin:</b> <i>'Bakıda 2 otaqlı kirayə ev tap 500 azn'</i>\n"
        "2. 🎙️ <b>Səsli mesaj atın:</b> Səsinizi analiz edib <b>tap.az, arenda.az, emlak.az, yeniemlak.az</b> sitələrində axtarım!"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("İster yazılı ister səsli olaraq axtardığınız evi bildirin!", parse_mode=ParseMode.HTML)

async def process_search_query(update: Update, user_text: str):
    await update.message.reply_chat_action(action=ChatAction.TYPING)
    params = parse_user_request(user_text)
    summary = format_parsed_params_summary(params)
    await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)
    
    await update.message.reply_chat_action(action=ChatAction.TYPING)
    listings = fetch_all_listings(params)
    
    if not listings:
        await update.message.reply_text("😔 <b>Axtarışınıza uyğun elan tapılmadı.</b>", parse_mode=ParseMode.HTML)
        return
        
    await update.message.reply_text(f"✅ <b>Tapılan {len(listings)} ən uyğun elan:</b>", parse_mode=ParseMode.HTML)
    for listing in listings[:10]:
        msg_content = format_listing_message(listing)
        try:
            if listing.image_url:
                await update.message.reply_photo(photo=listing.image_url, caption=msg_content, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(msg_content, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
        except Exception:
            await update.message.reply_text(msg_content, parse_mode=ParseMode.HTML, disable_web_page_preview=False)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_search_query(update, update.message.text)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice or update.message.audio
    if not voice: return
    await update.message.reply_chat_action(action=ChatAction.RECORD_VOICE)
    TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    temp_file_path = TEMP_AUDIO_DIR / f"voice_{update.message.message_id}.ogg"
    
    try:
        telegram_file = await context.bot.get_file(voice.file_id)
        await telegram_file.download_to_drive(custom_path=temp_file_path)
        transcribed_text = transcribe_audio(temp_file_path)
        await update.message.reply_text(f"🎙️ <b>Səsli mesajınız anlaşıldı:</b>\n<i>\"{transcribed_text}\"</i>", parse_mode=ParseMode.HTML)
        await process_search_query(update, transcribed_text)
    except Exception as e:
        logger.error(f"Voice handling error: {e}")
        await update.message.reply_text("❌ Səsli mesaj analiz edilərkən xəta baş verdi.", parse_mode=ParseMode.HTML)
    finally:
        if temp_file_path.exists():
            try: os.remove(temp_file_path)
            except Exception: pass

def main():
    print("🚀 Azerbaycan Emlak Telegram Botu başlatılıyor...")
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN missing!")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))

    logger.info("Bot dinlemede...")
    app.run_polling()

if __name__ == "__main__":
    main()
