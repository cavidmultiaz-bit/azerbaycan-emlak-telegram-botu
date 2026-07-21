import logging
from services.parser import parse_user_request
from scrapers.aggregator import fetch_all_listings
from services.formatter import format_parsed_params_summary, format_listing_message

logging.basicConfig(level=logging.INFO)

def run_test():
    test_queries = [
        "Mənə 2 otaqlı kirayə ev tap Bakıda 500 manata qədər",
        "Nəsimi rayonunda satılıq həyət evi 100000 azn"
    ]
    
    for query in test_queries:
        print(f"\n==========================================")
        print(f"🧪 Test Sorğusu: '{query}'")
        print(f"==========================================")
        
        # 1. Test LLM Parser
        params = parse_user_request(query)
        summary = format_parsed_params_summary(params)
        print(f"\n{summary}\n")
        
        # 2. Test Aggregated Scraper
        listings = fetch_all_listings(params)
        print(f"✅ Tapılan Ümumi Elan Sayı: {len(listings)}\n")
        
        for idx, listing in enumerate(listings[:3], 1):
            print(f"--- İlan #{idx} ---")
            print(format_listing_message(listing))
            print()

if __name__ == "__main__":
    run_test()
