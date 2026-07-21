# 🏡 Azerbaycan Emlak Telegram Botu (Satış & Kirayə)

Bu proje, Telegram üzerinden gelen **sesli mesajları** (STT - Speech to Text) veya **yazılı metinleri** yapay zeka (LLM) ile analiz edip Azerbaycan'ın 4 büyük emlak portalında (`tap.az`, `arenda.az`, `emlak.az`, `yeniemlak.az`) eş zamanlı arama yapan ve uygun ilanları fotoğraflı/detaylı kartlar olarak müşteriye sunan akıllı bir Telegram botudur.

---

## 🚀 Özellikler

1. **🎙️ Sesli Mesaj Desteği (Whisper STT):**
   - Müşteri ses kaydı gönderdiğinde (`.ogg`), ses OpenAI Whisper modeli ile yüksek doğrulukla Azerbaycan dilinde metne çevrilir.
2. **🧠 Yapay Zeka Parametre Analizi (NLU - GPT-4o-mini):**
   - "Mənə 2 otaqlı kirayə ev tap Bakıda 500 manata qədər" gibi karmaşık isteklerden niyet (`kiraye`/`satiliq`), emlak tipi (`menzil`/`heyet_evi`), otaq sayısı, şehir/bölge ve fiyat aralığı otomatik süzülür.
3. **🌐 Çoklu Portal Arama Motoru (Aggregator):**
   - **tap.az** (Emlak kategorisi)
   - **arenda.az**
   - **emlak.az**
   - **yeniemlak.az**
   - 4 siteye aynı anda (parallel ThreadPool) istek atılarak en güncel ilanlar çekilir ve tek listede birleştirilir.
4. **📱 Şık Telegram İlan Kartları:**
   - İlanların başlığı, fiyatı, konumu, otaq sayısı, fotoğrafı ve ilan direkt linki Telegram mesajı olarak iletilir.

---

## 📁 Proje Klasör Yapısı

```
Azerbaycan_Emlak_Telegram_Botu/
├── main.py                 # Botu başlatan ana giriş noktası
├── config.py               # Ortam değişkenleri ve yapılandırma
├── requirements.txt        # Python bağımlılıkları
├── .env.example            # Örnek konfigürasyon şablonu
├── filo.json               # Proje filo kartı
├── bot/
│   ├── __init__.py
│   └── handlers.py         # Telegram komut (/start, /help) ve mesaj işleyicileri
├── services/
│   ├── __init__.py
│   ├── transcriber.py      # Ses kaydını metne dönüştürme (Whisper API)
│   ├── parser.py           # Metinden emlak arama parametrelerini çıkarma (LLM)
│   └── formatter.py        # Telegram mesajlarını biçimlendirici
├── scrapers/
│   ├── __init__.py
│   ├── base.py             # Ortak veri modelleri (Listing) ve varsayılan başlıklar
│   ├── tap_az.py           # tap.az arama tarayıcısı
│   ├── arenda_az.py        # arenda.az arama tarayıcısı
│   ├── emlak_az.py         # emlak.az arama tarayıcısı
│   ├── yeniemlak.az.py     # yeniemlak.az arama tarayıcısı
│   └── aggregator.py       # 4 siteyi paralel tarayan birleştirici
└── test_pipeline.py        # Modül test betiği
```

---

## ⚙️ Kurulum ve Çalıştırma

### 1. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
```

### 2. `.env` Dosyasını Oluşturun
`.env.example` dosyasını `.env` olarak kopyalayın ve API anahtarlarınızı girin:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
OPENAI_API_KEY=sk-proj-xxxxxx
```

### 3. Botu Çalıştırın
```bash
python main.py
```

---

## 🧪 Test Etme (`test_pipeline.py`)

Telegram botunu çalıştırmadan önce arama motorunu ve yapay zeka analizini doğrudan terminalde test etmek için:

```bash
python test_pipeline.py
```
