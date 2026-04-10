import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import os
import pandas as pd
from collections import defaultdict
import urllib.parse as urlparse

# =========================
# CONFIG
# =========================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

BRANDS = [
    "sony", "samsung", "nike", "adidas", "apple", "hp", "lenovo",
    "lg", "bosch", "philips", "tecno", "infinix"
]

BAD_SITES = [
    "sony.com",
    "sony-asia.com",
    "manual",
    "support",
]

# =========================
# HELPERS
# =========================
def clean_url(url):
    if "duckduckgo.com" in url:
        parsed = urlparse.urlparse(url)
        qs = urlparse.parse_qs(parsed.query)
        return qs.get("uddg", [url])[0]
    return url

def is_valid_url(url):
    return not any(b in url.lower() for b in BAD_SITES)

# =========================
# BRAND + MODEL DETECTION
# =========================
def detect_brand(text):
    text = text.lower()
    for b in BRANDS:
        if b in text:
            return b.title()
    return None

def detect_model(text):
    text = text.upper()
    match = re.search(r"(DAV[-\s]?DZ[-\s]?\d{3})", text)
    if match:
        return match.group(1).replace(" ", "").replace("--", "-")
    matches = re.findall(r"\b[A-Z0-9\-]{5,}\d+\b", text)
    return matches[0] if matches else None

def enhance_query(name):
    name = name.lower()
    if "sony" in name and "dz" in name:
        return name.replace("dz", "dav-dz")
    return name

# =========================
# GTIN EXTRACTION & VALIDATION
# =========================
def extract_gtins(text):
    patterns = [
        r"\b\d{12}\b",
        r"\b\d{13}\b",
        r"\b\d{14}\b",
    ]
    results = set()
    for p in patterns:
        results.update(re.findall(p, text))
    return list(results)

def validate_ean13(code):
    if len(code) != 13:
        return False
    digits = list(map(int, code))
    checksum = sum(digits[:-1:2]) + sum(d * 3 for d in digits[1:-1:2])
    return (10 - (checksum % 10)) % 10 == digits[-1]

# =========================
# SEARCH APIs & SCRAPERS
# =========================
def upcitemdb_search(query):
    """Tier 1: Fastest method using free UPCItemDB API"""
    url = "https://api.upcitemdb.com/prod/trial/search"
    params = {"s": query, "match_mode": "0", "type": "product"}
    try:
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "OK" and data.get("items"):
                results = []
                for item in data["items"]:
                    gtin = item.get("ean") or item.get("upc")
                    if gtin:
                        results.append((gtin, item.get("title", "Unknown Title")))
                return results
    except Exception:
        pass
    return []

def scrape_amazon_direct(query):
    """Tier 1.5: Attempt to directly scrape Amazon search results"""
    url = f"https://www.amazon.com/s?k={urllib.parse.quote(query)}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            return extract_gtins(res.text)
    except:
        pass
    return []

def serpapi_search(query):
    """Tier 2: Fast snippet search via Google (Requires API Key)"""
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return []
    url = "https://serpapi.com/search"
    params = {"q": query, "api_key": api_key, "engine": "google"}
    try:
        res = requests.get(url, params=params)
        data = res.json()
        return data.get("organic_results", [])
    except:
        return []

def fallback_search(query):
    """Tier 3: Free DuckDuckGo Scraping"""
    url = f"https://duckduckgo.com/html/?q={query}"
    try:
        res = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(res.text, "lxml")
        results = []
        for r in soup.select(".result"):
            a = r.select_one(".result__a")
            snippet = r.select_one(".result__snippet")
            if a:
                results.append({
                    "title": a.get_text(),
                    "link": a.get("href"),
                    "snippet": snippet.get_text() if snippet else ""
                })
        return results[:5]
    except:
        return []

def fetch_page(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        return res.text
    except:
        return ""

# =========================
# MAIN ENGINE
# =========================
@st.cache_data(ttl=3600)
def find_product_data_fast(product_name):
    original_name = product_name
    product_name = enhance_query(product_name)
    brand = detect_brand(product_name)
    model = detect_model(product_name)
    
    gtin_scores = defaultdict(int)
    sources = defaultdict(list)

    # 🚀 STEP 1: UPCItemDB API
    upc_results = upcitemdb_search(model if model else product_name)
    if upc_results:
        for gtin, title in upc_results:
            gtin_scores[gtin] += 10
            sources[gtin].append(f"UPCItemDB API (Matched: {title})")
        
        best_gtin = max(gtin_scores, key=gtin_scores.get)
        return {"input_product": original_name, "brand": brand, "model": model, "gtin": best_gtin, "confidence": 0.99, "status": "found_api", "sources": ", ".join(set(sources[best_gtin]))}

    # 🛒 STEP 1.5: Amazon Direct Scrape
    amazon_gtins = scrape_amazon_direct(f"{product_name} UPC EAN")
    if amazon_gtins:
        for g in amazon_gtins:
            score = 5
            if validate_ean13(g): score += 2
            gtin_scores[g] += score
            sources[g].append("Amazon Direct Scrape")

        best_gtin = max(gtin_scores, key=gtin_scores.get)
        return {"input_product": original_name, "brand": brand, "model": model, "gtin": best_gtin, "confidence": 0.85, "status": "found_amazon", "sources": ", ".join(set(sources[best_gtin]))}

    # ⚡ STEP 2: SEARCH ENGINE SNIPPETS
    queries = [f'{product_name} EAN site:amazon.com', f'{product_name} UPC', f'{product_name} barcode']
    if model: queries.insert(0, f'{model} EAN')

    for q in queries:
        results = serpapi_search(q)
        if not results: results = fallback_search(q)

        for r in results:
            url = clean_url(r.get("link"))
            snippet = r.get("snippet", "")
            gtins = extract_gtins(snippet)
            for g in gtins:
                score = 3
                if validate_ean13(g): score += 2
                gtin_scores[g] += score
                sources[g].append(url)

    if gtin_scores:
        best_gtin = max(gtin_scores, key=gtin_scores.get)
        confidence = min(1.0, gtin_scores[best_gtin] / 10)
        return {"input_product": original_name, "brand": brand, "model": model, "gtin": best_gtin, "confidence": round(confidence, 2), "status": "found_snippet", "sources": ", ".join(set(sources[best_gtin]))}

    # 🐢 STEP 3: DEEP PAGE SCRAPING
    for q in queries[:2]:
        results = fallback_search(q)
        for r in results[:3]: 
            url = clean_url(r.get("link"))
            if not is_valid_url(url): continue
            html = fetch_page(url)
            if not html: continue
            gtins = extract_gtins(html)
            for g in gtins:
                gtin_scores[g] += 1
                sources[g].append(url)

    if not gtin_scores:
        return {"input_product": original_name, "brand": brand, "model": model, "gtin": None, "confidence": 0, "status": "not_found", "sources": ""}

    best_gtin = max(gtin_scores, key=gtin_scores.get)
    return {"input_product": original_name, "brand": brand, "model": model, "gtin": best_gtin, "confidence": 0.5, "status": "found_deep_scrape", "sources": ", ".join(set(sources[best_gtin]))}

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="GTIN Finder PRO", layout="wide")

st.title("📦 GTIN Finder PRO (Bulk & Amazon Edition)")
st.caption("UPC API + Amazon Scraper + Snippet Scrape + Smart Cache")

st.write("### Enter Products")
product_input = st.text_area("Paste product names here (one per line):", height=150, placeholder="Sony WH-1000XM4\nNike Air Max 90\nSamsung Galaxy S23")

if st.button("Run Bulk Analysis"):
    # Clean input list
    products = [p.strip() for p in product_input.split('\n') if p.strip()]
    
    if not products:
        st.warning("Please enter at least one product.")
    else:
        st.info(f"Starting bulk processing for {len(products)} products...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results_data = []
        
        for i, prod in enumerate(products):
            status_text.text(f"Processing ({i+1}/{len(products)}): {prod}")
            
            # Fetch data
            res = find_product_data_fast(prod)
            results_data.append(res)
            
            # Update progress
            progress_bar.progress((i + 1) / len(products))
        
        status_text.success("Bulk processing complete!")
        
        # Display Results as DataFrame
        df = pd.DataFrame(results_data)
        st.write("### Results")
        st.dataframe(df, use_container_width=True)
        
        # CSV Export
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Download Results as CSV",
            data=csv,
            file_name='gtin_bulk_results.csv',
            mime='text/csv',
        )
