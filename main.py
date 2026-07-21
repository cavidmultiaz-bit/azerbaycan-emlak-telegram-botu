import os
import sys
import json
import re
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
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))
TEMP_AUDIO_DIR = BASE_DIR / "temp_audio"

# --- BAKU METRO STATIONS: Normalization Map ---
# Maps common misspellings, abbreviations, and colloquial forms to canonical station names
METRO_ALIASES = {
    # İçəri Şəhər
    "iceri seher": "İçəri Şəhər", "icerisheher": "İçəri Şəhər", "icheri sheher": "İçəri Şəhər",
    # Sahil
    "sahil": "Sahil", "sahildə": "Sahil", "sahilde": "Sahil",
    # 28 May
    "28 may": "28 May", "28 maya": "28 May", "28may": "28 May", "iyirmi sekkiz may": "28 May",
    # Gənclik
    "genclik": "Gənclik", "gənclik": "Gənclik", "gencliye": "Gənclik", "gəncliyə": "Gənclik",
    "genclik metro": "Gənclik",
    # Nəriman Nərimanov
    "nerimanov": "Nəriman Nərimanov", "nərimanov": "Nəriman Nərimanov",
    "neriman nerimanov": "Nəriman Nərimanov", "nəriman nərimanov": "Nəriman Nərimanov",
    "nerimanova": "Nəriman Nərimanov", "nərimanova": "Nəriman Nərimanov",
    # Bakmil
    "bakmil": "Bakmil", "bakmila": "Bakmil", "bakmılda": "Bakmil",
    # Ulduz
    "ulduz": "Ulduz", "ulduzda": "Ulduz", "ulduza": "Ulduz",
    # Koroğlu
    "koroglu": "Koroğlu", "koroğlu": "Koroğlu", "koroqluda": "Koroğlu",
    # Qara Qarayev
    "qara qarayev": "Qara Qarayev", "qarayev": "Qara Qarayev", "qarayevə": "Qara Qarayev",
    "qara qarayevə": "Qara Qarayev", "qara qarayevda": "Qara Qarayev",
    # Neftçilər
    "neftciler": "Neftçilər", "neftçilər": "Neftçilər", "neftçilərdə": "Neftçilər",
    "neftcilerde": "Neftçilər", "neftcilərda": "Neftçilər",
    # Xalqlar Dostluğu
    "xalqlar dostlugu": "Xalqlar Dostluğu", "xalqlar dostluğu": "Xalqlar Dostluğu",
    "xalqlarda": "Xalqlar Dostluğu", "xalqlar": "Xalqlar Dostluğu",
    # Əhmədli
    "ehmedli": "Əhmədli", "əhmədli": "Əhmədli", "əhmədliyə": "Əhmədli",
    "ehmedliye": "Əhmədli", "ahmedli": "Əhmədli",
    # Həzi Aslanov
    "hezi aslanov": "Həzi Aslanov", "həzi aslanov": "Həzi Aslanov",
    "hezi aslanovda": "Həzi Aslanov", "həzi aslanovda": "Həzi Aslanov",
    # Cəfər Cabbarlı
    "cefer cabbarli": "Cəfər Cabbarlı", "cəfər cabbarlı": "Cəfər Cabbarlı",
    "cefer cabbarlıya": "Cəfər Cabbarlı", "cəfər cabbarlıya": "Cəfər Cabbarlı",
    "cabbarli": "Cəfər Cabbarlı", "cabbarlı": "Cəfər Cabbarlı",
    # Nizami
    "nizami": "Nizami", "nizamidə": "Nizami", "nizamide": "Nizami",
    # Elmlər Akademiyası
    "elmler": "Elmlər Akademiyası", "elmlər": "Elmlər Akademiyası",
    "elmler akademiyasi": "Elmlər Akademiyası", "elmlər akademiyası": "Elmlər Akademiyası",
    "elmlərdə": "Elmlər Akademiyası", "elmlerde": "Elmlər Akademiyası",
    # İnşaatçılar
    "insaatcilar": "İnşaatçılar", "inşaatçılar": "İnşaatçılar",
    "insaatcilara": "İnşaatçılar", "inşaatçılara": "İnşaatçılar",
    # 20 Yanvar
    "20 yanvar": "20 Yanvar", "20 yanvarda": "20 Yanvar", "iyirmi yanvar": "20 Yanvar",
    # Memar Əcəmi
    "memar ecemi": "Memar Əcəmi", "memar əcəmi": "Memar Əcəmi",
    "məmər əcəmi": "Memar Əcəmi", "memar acemi": "Memar Əcəmi",
    "memar ejemi": "Memar Əcəmi",
    # Nəsimi
    "nesimi": "Nəsimi", "nəsimi": "Nəsimi", "nəsimidə": "Nəsimi", "nesimide": "Nəsimi",
    # Azadlıq Prospekti
    "azadliq": "Azadlıq Prospekti", "azadlıq": "Azadlıq Prospekti",
    "azadlıqda": "Azadlıq Prospekti", "azadliqda": "Azadlıq Prospekti",
    "azadliq prospekti": "Azadlıq Prospekti", "azadlıq prospekti": "Azadlıq Prospekti",
    # Dərnəgül
    "dernegul": "Dərnəgül", "dərnəgül": "Dərnəgül",
    "dərnəgüldə": "Dərnəgül", "dernegulde": "Dərnəgül",
    # 8 Noyabr
    "8 noyabr": "8 Noyabr", "8 noyabrda": "8 Noyabr", "sekkiz noyabr": "8 Noyabr",
    # Xocəsən
    "xocesen": "Xocəsən", "xocəsən": "Xocəsən",
    "xocəsəndə": "Xocəsən", "xocesende": "Xocəsən",
    # Avtovağzal
    "avtovagzal": "Avtovağzal", "avtovağzal": "Avtovağzal",
    # Hərbə-Zorba (Hal)
    "hal": "Hal", "halda": "Hal",
}

def normalize_metro(text: str) -> str:
    """Normalizes metro station names in user text.
    Cleans suffixes like 'metrosu', 'metro', 'metroya yaxin' etc. first,
    then looks up the cleaned term in the alias map.
    Returns the canonical metro name or None."""
    cleaned = text.lower().strip()
    # Remove metro-related suffixes
    metro_suffixes = [
        "metrosuna yaxın", "metrosuna yaxin", "metroya yaxın", "metroya yaxin",
        "metro yaxınlığı", "metro yaxinligi", "metrosu yaxınlığı",
        "metrosu", "metrosuna", "metro", "m/st", "m.",
        "yaxınlığında", "yaxinliginda", "yaxın", "yaxin",
        "yaxınlığı", "yaxinligi",
    ]
    for suffix in metro_suffixes:
        cleaned = cleaned.replace(suffix, "").strip()

    # Remove trailing locative suffixes: -da, -də, -a, -ə, -dan, -dən
    cleaned = re.sub(r'(da|də|dan|dən)$', '', cleaned).strip()

    if cleaned in METRO_ALIASES:
        return METRO_ALIASES[cleaned]
    # Try partial match
    for alias, canonical in METRO_ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return canonical
    return None


def preprocess_user_text(text: str) -> str:
    """Preprocesses user text: detects metro references and normalizes them."""
    metro = normalize_metro(text)
    if metro:
        # Inject canonical metro name into text for better LLM + scraper results
        return f"{text} ({metro} metrosuna yaxın)"
    return text


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
    intent: str = Field(description="'kiraye' or 'satiliq' or 'unknown'")
    property_type: str = Field(description="'menzil','heyet_evi','ofis','torpaq','all'")
    city_region: str | None = Field(default=None, description="District or metro area")
    min_price: float | None = Field(default=None)
    max_price: float | None = Field(default=None)
    rooms: int | None = Field(default=None)
    metro_station: str | None = Field(default=None, description="Nearest metro station name")
    raw_query: str = Field(description="Normalized search keywords")


# Realistic browser headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "az,tr-TR;q=0.9,tr;q=0.8,en-US;q=0.7,en;q=0.6",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}


# --- SCRAPERS ---

def _build_search_query(params: PropertySearchParams) -> str:
    """Builds a search query string from params."""
    parts = []
    if params.metro_station:
        parts.append(params.metro_station)
    elif params.city_region:
        parts.append(params.city_region)
    if params.rooms:
        parts.append(f"{params.rooms} otaqli")
    if params.intent == "kiraye":
        parts.append("kiraye")
    elif params.intent == "satiliq":
        parts.append("satiliq")
    if not parts and params.raw_query:
        parts.append(params.raw_query)
    return " ".join(parts) if parts else "ev kiraye"


def search_tap_az(params: PropertySearchParams) -> list[Listing]:
    listings = []
    search_query = _build_search_query(params)
    encoded = urllib.parse.quote(search_query)

    # tap.az category-based URL for better results
    category = "dasinmaz-emlak-kiraye-evler" if params.intent == "kiraye" else "dasinmaz-emlak-satilan-evler" if params.intent == "satiliq" else "dasinmaz-emlak"
    url = f"https://tap.az/elanlar/{category}?q%5Bkeywords%5D={encoded}"

    headers = DEFAULT_HEADERS.copy()
    headers["Referer"] = "https://tap.az/"

    try:
        with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url)
            logger.info(f"tap.az status: {resp.status_code}")
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Multiple selector strategies
                items = soup.select(".products-i") or soup.select("article") or soup.select(".product-card")
                for item in items[:MAX_RESULTS_PER_SITE]:
                    link_el = item.select_one("a[href*='/elanlar/']") or item.select_one("a.products-i__link") or item.select_one("a")
                    title_el = item.select_one(".products-i__name") or item.select_one("h3") or item.select_one(".title")
                    price_el = item.select_one(".price-val") or item.select_one(".price")
                    img_el = item.select_one("img")
                    city_el = item.select_one(".products-i__datetime") or item.select_one(".location")
                    if not link_el: continue

                    href = link_el.get("href", "")
                    item_url = href if href.startswith("http") else f"https://tap.az{href}"
                    title = (title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)) or "Tap.az Elanı"
                    if len(title) < 3: continue
                    price = (price_el.get_text(strip=True) + " AZN" if price_el else "Qiymət yoxdur")
                    image_url = None
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy")
                    location = (city_el.get_text(strip=True) if city_el else params.city_region or params.metro_station or "Bakı")

                    listings.append(Listing(
                        title=title, price=price, location=location,
                        rooms=f"{params.rooms} otaqlı" if params.rooms else None,
                        url=item_url, image_url=image_url, source="tap.az"
                    ))
    except Exception as e:
        logger.error(f"Error tap.az: {e}")
    return listings


def search_bina_az(params: PropertySearchParams) -> list[Listing]:
    """bina.az - one of the largest real estate portals in Azerbaijan."""
    listings = []
    search_query = _build_search_query(params)
    encoded = urllib.parse.quote(search_query)

    # Build bina.az URL with filters
    intent_path = "kiraye/menziller" if params.intent == "kiraye" else "alqi-satqi/menziller" if params.intent == "satiliq" else "items"
    url = f"https://bina.az/{intent_path}?q={encoded}"

    headers = DEFAULT_HEADERS.copy()
    headers["Referer"] = "https://bina.az/"

    try:
        with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url)
            logger.info(f"bina.az status: {resp.status_code}")
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # bina.az uses .items-i cards
                items = soup.select(".items-i") or soup.select(".listing-card") or soup.select("article")
                for item in items[:MAX_RESULTS_PER_SITE]:
                    link_el = item.select_one("a[href*='/items/']") or item.select_one("a")
                    title_el = item.select_one(".card_params_h") or item.select_one(".name") or item.select_one("h3")
                    price_el = item.select_one(".price-val") or item.select_one(".price")
                    img_el = item.select_one("img")
                    location_el = item.select_one(".card_params_body") or item.select_one(".location")
                    if not link_el: continue

                    href = link_el.get("href", "")
                    item_url = href if href.startswith("http") else f"https://bina.az{href}"
                    title = ""
                    if title_el:
                        title = title_el.get_text(strip=True)
                    if not title:
                        title = link_el.get_text(strip=True)
                    if len(title) < 3: title = "Bina.az Elanı"

                    price = (price_el.get_text(strip=True) if price_el else "Qiymət yoxdur")
                    if "AZN" not in price.upper() and "azn" not in price.lower():
                        price += " AZN"

                    image_url = None
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-src") or img_el.get("data-lazy")
                    location = (location_el.get_text(strip=True) if location_el else params.city_region or params.metro_station or "Bakı")

                    listings.append(Listing(
                        title=title, price=price, location=location,
                        rooms=f"{params.rooms} otaqlı" if params.rooms else None,
                        url=item_url, image_url=image_url, source="bina.az"
                    ))
    except Exception as e:
        logger.error(f"Error bina.az: {e}")
    return listings


# --- YENIEMLAK METRO MAP ---
YENIEMLAK_METRO_MAP = {
    "Həzi Aslanov": 1, "Əhmədli": 2, "Xalqlar Dostluğu": 3, "Neftçilər": 4, "Qara Qarayev": 5,
    "Koroğlu": 6, "Ulduz": 7, "Nəriman Nərimanov": 8, "Gənclik": 9, "28 May": 10,
    "Nizami": 11, "Elmlər Akademiyası": 12, "İnşaatçılar": 13, "20 Yanvar": 14, "Memar Əcəmi": 15,
    "Nəsimi": 16, "Azadlıq Prospekti": 17, "Cəfər Cabbarlı": 18, "Xətai": 19, "Sahil": 20,
    "İçəri Şəhər": 21, "Bakmil": 22, "Dərnəgül": 23, "Avtovağzal": 24, "8 Noyabr": 25, "Xocəsən": 26
}

def search_yeniemlak_az(params: PropertySearchParams) -> list[Listing]:
    listings = []
    headers = DEFAULT_HEADERS.copy()
    headers["Referer"] = "https://yeniemlak.az/"

    # Try precise parameters first
    metro_id = YENIEMLAK_METRO_MAP.get(params.metro_station) if params.metro_station else None
    elan_nov = 2 if params.intent == "kiraye" else (1 if params.intent == "satiliq" else None)

    urls_to_try = []
    if metro_id:
        u = f"https://yeniemlak.az/elan/axtar?metro%5B%5D={metro_id}"
        if elan_nov: u += f"&elan_nov={elan_nov}"
        if params.rooms: u += f"&otaq={params.rooms}"
        if params.max_price: u += f"&qiymet2={int(params.max_price)}"
        urls_to_try.append(u)
        
        # Fallback 1: Metro without max price restriction
        u_broad = f"https://yeniemlak.az/elan/axtar?metro%5B%5D={metro_id}"
        if elan_nov: u_broad += f"&elan_nov={elan_nov}"
        urls_to_try.append(u_broad)

    # Keyword search fallback
    search_query = _build_search_query(params)
    encoded = urllib.parse.quote(search_query)
    kw_url = f"https://yeniemlak.az/elan/axtar?keyword={encoded}"
    if elan_nov: kw_url += f"&elan_nov={elan_nov}"
    urls_to_try.append(kw_url)

    seen_urls = set()
    try:
        with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            for url in urls_to_try:
                if len(listings) >= MAX_RESULTS_PER_SITE:
                    break
                resp = client.get(url)
                logger.info(f"yeniemlak.az status for {url}: {resp.status_code}")
                if resp.status_code != 200:
                    continue

                html = resp.text
                table_matches = re.findall(r'<table class="list".*?</table>', html, re.DOTALL | re.IGNORECASE)
                
                for t in table_matches:
                    href_match = re.search(r'href=["\'](/elan/[^"\'\s>]+)["\']', t, re.IGNORECASE)
                    if not href_match:
                        continue

                    href = href_match.group(1)
                    item_url = f"https://yeniemlak.az{href}"
                    if item_url in seen_urls:
                        continue
                    seen_urls.add(item_url)

                    price_match = re.search(r'<price>(.*?)</price>', t, re.IGNORECASE)
                    tip_match = re.search(r'<tip>(.*?)</tip>', t, re.IGNORECASE)
                    emlak_match = re.search(r'<emlak>(.*?)</emlak>', t, re.IGNORECASE)
                    img_match = re.search(r'<img[^>]+src=["\']([^"\'\s>]+)["\']', t, re.IGNORECASE)
                    room_match = re.search(r'<div class="params"><b>(\d+)</b> otaq</div>', t, re.IGNORECASE)

                    price_str = f"{price_match.group(1).strip()} AZN" if (price_match and price_match.group(1).strip()) else "Razılaşma yolu ilə"
                    tip_str = tip_match.group(1).strip() if tip_match else ("Kirayə" if params.intent == "kiraye" else "Satılır")
                    emlak_str = emlak_match.group(1).strip() if emlak_match else "Mənzil"
                    rooms_found = f"{room_match.group(1)} otaqlı" if room_match else (f"{params.rooms} otaqlı" if params.rooms else None)

                    image_url = None
                    if img_match:
                        src = img_match.group(1)
                        image_url = src if src.startswith("http") else f"https://yeniemlak.az{src}"

                    location_str = params.metro_station or params.city_region or "Bakı"
                    if "nerimanov" in href.lower(): location_str = "Nəriman Nərimanov m."
                    elif "28-may" in href.lower(): location_str = "28 May m."
                    elif "genclik" in href.lower(): location_str = "Gənclik m."
                    elif "ehmedli" in href.lower(): location_str = "Əhmədli m."
                    elif "neftciler" in href.lower(): location_str = "Neftçilər m."

                    title_str = f"{tip_str} {rooms_found or ''} {emlak_str}".strip()

                    listings.append(Listing(
                        title=title_str,
                        price=price_str,
                        location=location_str,
                        rooms=rooms_found,
                        url=item_url,
                        image_url=image_url,
                        source="yeniemlak.az"
                    ))
                    if len(listings) >= MAX_RESULTS_PER_SITE:
                        break
    except Exception as e:
        logger.error(f"Error yeniemlak.az: {e}")
    return listings


def search_emlak_az(params: PropertySearchParams) -> list[Listing]:
    listings = []
    search_query = _build_search_query(params)
    encoded = urllib.parse.quote(search_query)
    url = f"https://emlak.az/search?q={encoded}"

    headers = DEFAULT_HEADERS.copy()
    headers["Referer"] = "https://emlak.az/"

    try:
        with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url)
            logger.info(f"emlak.az status: {resp.status_code}")
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".listing-item, .post-block, .item, tr.item, article, .card")
                for item in items[:MAX_RESULTS_PER_SITE]:
                    link_el = item.select_one("a[href*='/']")
                    title_el = item.select_one(".title, .name, td.title, h3, h2")
                    price_el = item.select_one(".price, td.price, .cost")
                    img_el = item.select_one("img")
                    location_el = item.select_one(".location, .city, td.location, .address")
                    if not link_el: continue

                    href = link_el.get("href", "")
                    item_url = href if href.startswith("http") else f"https://emlak.az{href}"
                    title = (title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)) or ""
                    if len(title) < 3: title = f"Emlak.az İlanı"
                    price = (price_el.get_text(strip=True) if price_el else "Əlaqə saxlayın")
                    image_url = None
                    if img_el:
                        image_url = img_el.get("src") or img_el.get("data-src")
                        if image_url and not image_url.startswith("http"):
                            image_url = "https://emlak.az" + image_url
                    location = (location_el.get_text(strip=True) if location_el else params.city_region or "Bakı")

                    listings.append(Listing(
                        title=title, price=price, location=location,
                        rooms=f"{params.rooms} otaqlı" if params.rooms else None,
                        url=item_url, image_url=image_url, source="emlak.az"
                    ))
    except Exception as e:
        logger.error(f"Error emlak.az: {e}")
    return listings


def fetch_all_listings(params: PropertySearchParams) -> list[Listing]:
    scrapers = [
        ("bina.az", search_bina_az),
        ("yeniemlak.az", search_yeniemlak_az),
        ("tap.az", search_tap_az),
        ("emlak.az", search_emlak_az),
    ]
    all_results = []
    seen_urls = set()

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_source = {executor.submit(func, params): name for name, func in scrapers}
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                results = future.result()
                logger.info(f"{source}: {len(results)} nəticə tapıldı")
                for item in results:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_results.append(item)
            except Exception as e:
                logger.error(f"Scraper {source} error: {e}")
    return all_results


# --- AI SERVICES ---

# Full list of Baku metro station names for the LLM
BAKU_METRO_LIST = (
    "İçəri Şəhər, Sahil, 28 May, Gənclik, Nəriman Nərimanov, Bakmil, Ulduz, Koroğlu, "
    "Qara Qarayev, Neftçilər, Xalqlar Dostluğu, Əhmədli, Həzi Aslanov, "
    "Cəfər Cabbarlı, Nizami, Elmlər Akademiyası, İnşaatçılar, 20 Yanvar, "
    "Memar Əcəmi, Nəsimi, Azadlıq Prospekti, Dərnəgül, 8 Noyabr, Xocəsən, Avtovağzal, Hal"
)

SYSTEM_PROMPT = f"""Sən Azərbaycan emlak axtarış asistanısan. İstifadəçinin mesajını analiz edib axtarış parametrlərini JSON formatında çıxarmalısan.

METRO STANSİYALARI (Bakı):
{BAKU_METRO_LIST}

QAYDALAR:
1. İstifadəçi metro adını səhv yazsa belə (məs: "28 maya", "nərimanova", "gəncliyə", "bakmila", "elmlərdə", "memar ecemi", "xalqlarda", "dernegulde") düzgün metro adını tap.
2. "metro", "metrosu", "metroya yaxın", "metro yaxınlığı" kimi ifadələr eyni mənadadır.
3. Böyük-kiçik hərf, ə/e, ı/i, ö/o, ü/u, ş/s, ç/c, ğ/g fərqlərini nəzərə alma.
4. "neftçilərdə ev" = Neftçilər metrosuna yaxın, "xalqlarda ev" = Xalqlar Dostluğu, "əhmədliyə yaxın" = Əhmədli, "nizamidə ev" = Nizami.
5. Metro stansiyası aşkar edilərsə "metro_station" sahəsinə standart adını yaz, "city_region" sahəsinə isə ən yaxın rayonu yaz.
6. "raw_query" sahəsinə axtarış üçün ən uyğun açar sözləri yaz (metro adı + otaq + intent).

JSON FORMAT:
{{
  "intent": "kiraye" | "satiliq" | "unknown",
  "property_type": "menzil" | "heyet_evi" | "ofis" | "torpaq" | "all",
  "city_region": "Bakı" | "Nəsimi" | "Yasamal" | "Nizami" | "Xırdalan" | null,
  "min_price": number | null,
  "max_price": number | null,
  "rooms": number | null,
  "metro_station": "28 May" | "Gənclik" | ... | null,
  "raw_query": "axtarış açar sözləri"
}}"""


def transcribe_audio(audio_path: str | Path) -> str:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY təyin olunmayıb.")
    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", file=audio_file, language="az",
            prompt="Emlak araması: ev satışı, kirayə ev, mənzil, otaq, metro, Bakı, AZN"
        )
    return transcript.text.strip()


def parse_user_request(text: str) -> PropertySearchParams:
    # First, try local metro normalization
    detected_metro = normalize_metro(text)

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY yoxdur, sadə analiz istifadə olunur.")
        return _fallback_parse(text, detected_metro)

    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.1
        )
        data = json.loads(response.choices[0].message.content)
        # Override metro_station with local detection if LLM missed it
        if detected_metro and not data.get("metro_station"):
            data["metro_station"] = detected_metro
        return PropertySearchParams(**data)
    except Exception as e:
        logger.error(f"OpenAI API xətası: {e}")
        return _fallback_parse(text, detected_metro)


def _fallback_parse(text: str, detected_metro: str | None = None) -> PropertySearchParams:
    """Fallback parser when OpenAI is unavailable."""
    text_lower = text.lower()

    # Detect intent
    intent = "unknown"
    if any(w in text_lower for w in ["kiray", "icarə", "icara", "arenda"]):
        intent = "kiraye"
    elif any(w in text_lower for w in ["sat", "alım", "alim", "almaq"]):
        intent = "satiliq"

    # Detect rooms
    rooms = None
    rooms_match = re.search(r'(\d+)\s*otaq', text_lower)
    if rooms_match:
        rooms = int(rooms_match.group(1))

    # Detect price
    max_price = None
    price_match = re.search(r'(\d+)\s*(?:azn|manat)', text_lower)
    if price_match:
        max_price = float(price_match.group(1))

    # Detect region
    city_region = None
    regions = ["bakı", "baki", "gəncə", "gence", "sumqayıt", "sumqayit",
               "yasamal", "nəsimi", "nesimi", "xətai", "xetai", "sabunçu", "sabuncu",
               "binəqədi", "bineqedi", "suraxanı", "suraxani", "qaradağ", "qaradag",
               "xırdalan", "xirdalan", "abşeron", "abseron"]
    for r in regions:
        if r in text_lower:
            city_region = r.capitalize()
            break

    # Build raw query
    raw_parts = []
    if detected_metro:
        raw_parts.append(detected_metro)
    elif city_region:
        raw_parts.append(city_region)
    if rooms:
        raw_parts.append(f"{rooms} otaqli")
    if intent == "kiraye":
        raw_parts.append("kiraye")
    elif intent == "satiliq":
        raw_parts.append("satiliq")
    if not raw_parts:
        raw_parts.append(text[:50])

    return PropertySearchParams(
        intent=intent,
        property_type="all",
        city_region=city_region or "Bakı",
        min_price=None,
        max_price=max_price,
        rooms=rooms,
        metro_station=detected_metro,
        raw_query=" ".join(raw_parts)
    )


# --- FORMATTERS ---
def format_parsed_params_summary(params: PropertySearchParams) -> str:
    intent_str = "Kirayə" if params.intent == "kiraye" else ("Satılıq" if params.intent == "satiliq" else "Axtarış")
    type_str = {"menzil": "Mənzil", "heyet_evi": "Həyət evi", "ofis": "Ofis", "torpaq": "Torpaq"}.get(params.property_type, "Mənzil")
    details = []
    if params.metro_station:
        details.append(f"🚇 Ərazi: {params.metro_station} metrosuna yaxın")
    elif params.city_region:
        details.append(f"📍 Ərazi: {params.city_region}")
    if params.rooms:
        details.append(f"🚪 Otaq: {params.rooms} otaqlı")
    if params.max_price:
        details.append(f"💰 Maks. Qiymət: {int(params.max_price)} AZN")
    details_text = "\n".join(details) if details else "Ümumi axtarış"
    return f"🔍 <b>Axtarış:</b> {intent_str} {type_str}\n{details_text}"


def format_listing_message(listing: Listing) -> str:
    source_badge = {
        "tap.az": "🔵 tap.az",
        "bina.az": "🟣 bina.az",
        "emlak.az": "🔴 emlak.az",
        "yeniemlak.az": "🟠 yeniemlak.az"
    }.get(listing.source, listing.source)

    msg = f"🏠 <b>{listing.title}</b>\n\n"
    msg += f"💵 <b>Qiymət:</b> {listing.price}\n"
    msg += f"📍 <b>Ünvan:</b> {listing.location}\n"
    if listing.rooms:
        msg += f"🚪 <b>Otaq:</b> {listing.rooms}\n"
    msg += f"🌐 <b>Mənbə:</b> {source_badge}\n"
    msg += f"🔗 <a href='{listing.url}'>İlana saytda baxmaq üçün toxunun</a>"
    return msg


# --- TELEGRAM HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🏡 <b>Azərbaycan Emlak Axtarış Botuna Xoş Gəldiniz!</b>\n\n"
        "Mənə axtardığınız evi yazın və ya səsli mesaj göndərin:\n\n"
        "💬 <b>Yazılı nümunə:</b>\n"
        "<i>• Bakıda 2 otaqlı kirayə ev tap 500 azn\n"
        "• 28 May metrosuna yaxın 3 otaqlı mənzil\n"
        "• Nərimanovda kirayə ev\n"
        "• Əhmədlidə satılıq 1 otaqlı</i>\n\n"
        "🎙️ <b>Səsli mesaj:</b> Sadəcə danışın, mən anlayacağam!\n\n"
        "🔍 Axtarış mənbələri: <b>bina.az, tap.az, emlak.az, yeniemlak.az</b>"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 <b>İstifadə Qaydası:</b>\n\n"
        "İstər yazılı istər səsli olaraq axtardığınız evi bildirin!\n\n"
        "🚇 <b>Metro stansiyaları üzrə axtarış:</b>\n"
        "28 May, Gənclik, Nərimanov, Koroğlu, Nizami, Əhmədli, Həzi Aslanov, "
        "Memar Əcəmi, İnşaatçılar, Elmlər, Xalqlar Dostluğu, Neftçilər və s.\n\n"
        "Hətta səhv yazsanız belə (məs: <i>nerimanova yaxin, 28 maya, genclik metro</i>) mən düzgün anlayacağam! 😊"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def process_search_query(update: Update, user_text: str):
    await update.message.reply_chat_action(action=ChatAction.TYPING)

    # Preprocess: normalize metro names
    processed_text = preprocess_user_text(user_text)
    params = parse_user_request(processed_text)

    summary = format_parsed_params_summary(params)
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

    await update.message.reply_chat_action(action=ChatAction.TYPING)
    listings = fetch_all_listings(params)

    # Build direct search links for user convenience
    query_str = urllib.parse.quote(params.metro_station or params.city_region or params.raw_query or user_text)
    bina_link = f"https://bina.az/items?q={query_str}"
    tap_link = f"https://tap.az/elanlar/emlak?q%5Bkeywords%5D={query_str}"
    yeniemlak_link = f"https://yeniemlak.az/elan/axtar?keyword={query_str}"

    portal_links_html = (
        f"\n🌐 <b>Portallarda canlı axtarış keçidləri:</b>\n"
        f"• <a href='{yeniemlak_link}'>yeniemlak.az saytında bax</a>\n"
        f"• <a href='{bina_link}'>bina.az saytında bax</a>\n"
        f"• <a href='{tap_link}'>tap.az saytında bax</a>"
    )

    if not listings:
        await update.message.reply_text(
            "😔 <b>Axtarışınıza uyğun ilkin elan tapılmadı.</b>\n\n"
            "💡 <b>Məsləhətlər:</b>\n"
            "• Qiymət və ya otaq şərtini biraz genişləndirin\n"
            f"{portal_links_html}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
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
    if not voice:
        return
    await update.message.reply_chat_action(action=ChatAction.RECORD_VOICE)
    TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    temp_file_path = TEMP_AUDIO_DIR / f"voice_{update.message.message_id}.ogg"

    try:
        telegram_file = await context.bot.get_file(voice.file_id)
        await telegram_file.download_to_drive(custom_path=temp_file_path)
        transcribed_text = transcribe_audio(temp_file_path)
        await update.message.reply_text(
            f"🎙️ <b>Səsli mesajınız anlaşıldı:</b>\n<i>\"{transcribed_text}\"</i>",
            parse_mode=ParseMode.HTML
        )
        await process_search_query(update, transcribed_text)
    except Exception as e:
        logger.error(f"Voice handling error: {e}")
        await update.message.reply_text(
            "❌ Səsli mesaj analiz edilərkən xəta baş verdi. Zəhmət olmasa yazılı mesaj göndərin.",
            parse_mode=ParseMode.HTML
        )
    finally:
        if temp_file_path.exists():
            try:
                os.remove(temp_file_path)
            except Exception:
                pass


def main():
    print("🚀 Azerbaycan Emlak Telegram Botu başlatılıyor...")
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN təyin olunmayıb!")
        sys.exit(1)

    if not OPENAI_API_KEY:
        logger.warning("⚠️ OPENAI_API_KEY təyin olunmayıb. Bot sadə analiz rejimində işləyəcək.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))

    logger.info("Bot dinlemede...")
    app.run_polling()


if __name__ == "__main__":
    main()
