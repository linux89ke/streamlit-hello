import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import os
from collections import defaultdict
import urllib.parse as urlparse

# =========================
# CONFIG
# =========================
HEADERS = {
    "User-Agent": "Mozilla/5.0"
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

    # Specific Sony pattern fix
    match = re.search(r"(DAV[-\s]?DZ[-\s]?\d{3})", text)
    if match:
        return match.group(1).replace(" ", "").replace("--", "-")

    # General fallback
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
# SEARCH APIs
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
                # Grab EAN or UPC from the top matches
                for item in data["items"]:
                    gtin = item.get("ean") or item.get("upc")
                    if gtin:
                        results.append((gtin, item.get("title", "Unknown Title")))
                return results
    except Exception:
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
# MAIN ENGINE (HYBRID API + SCRAPE)
# =========================
@st.cache_data(ttl=3600)
def find_product_data_fast(product_name):
    product_name = enhance_query(product_name)

    brand = detect_brand(product_name)
    model = detect_model(product_name)
    
    gtin_scores = defaultdict(int)
    sources = defaultdict(list)

    # 🚀 STEP 1: UPCItemDB API (INSTANT WIN)
    st.write("⚡ Checking UPCItemDB Database API...")
    upc_results = upcitemdb_search(model if model else product_name)
    
    if upc_results:
        for gtin, title in upc_results:
            gtin_scores[gtin] += 10  # Massive score boost for dedicated API
            sources[gtin].append(f"UPCItemDB API (Matched: {title})")
        
        best_gtin = max(gtin_scores, key=gtin_scores.get)
        return {
            "brand": brand,
            "model": model,
            "gtin": best_gtin,
            "confidence": 0.99,
            "status": "found_instant_api",
            "sources": sources[best_gtin]
        }

    # ⚡ STEP 2: SEARCH ENGINE SNIPPETS
    queries = [
        f'{product_name} EAN',
        f'{product_name} UPC',
        f'{product_name} barcode',
    ]

    if model:
        queries.insert(0, f'{model} EAN')

    for q in queries:
        st.write(f"🔍 Searching snippets: {q}")

        results = serpapi_search(q)
        if not results:
            results = fallback_search(q)

        for r in results:
            url = clean_url(r.get("link"))
            snippet = r.get("snippet", "")
            gtins = extract_gtins(snippet)

            for g in gtins:
                score = 3
                if validate_ean13(g):
                    score += 2

                gtin_scores[g] += score
                sources[g].append(url)

    if gtin_scores:
        best_gtin = max(gtin_scores, key=gtin_scores.get)
        confidence = min(1.0, gtin_scores[best_gtin] / 10)

        return {
            "brand": brand,
            "model": model,
            "gtin": best_gtin,
            "confidence": round(confidence, 2),
            "status": "found_snippet",
            "sources": sources[best_gtin]
        }

    # 🐢 STEP 3: DEEP PAGE SCRAPING (FALLBACK)
    st.write("🐢 No GTIN in snippets, deep scraping pages...")

    for q in queries[:2]:
        results = fallback_search(q)

        for r in results[:3]: 
            url = clean_url(r.get("link"))
            if not is_valid_url(url):
                continue

            html = fetch_page(url)
            if not html:
                continue

            gtins = extract_gtins(html)
            for g in gtins:
                gtin_scores[g] += 1
                sources[g].append(url)

    if not gtin_scores:
        return {
            "brand": brand,
            "model": model,
            "gtin": None,
            "confidence": 0,
            "status": "not_found",
            "reason": "GTIN not found anywhere",
            "sources": []
        }

    best_gtin = max(gtin_scores, key=gtin_scores.get)

    return {
        "brand": brand,
        "model": model,
        "gtin": best_gtin,
        "confidence": 0.5,
        "status": "found_deep_scrape",
        "sources": sources[best_gtin]
    }

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="GTIN Finder PRO", layout="wide")

st.title("🔍 GTIN Finder PRO (Lightning Mode)")
st.caption("UPC API + Snippet Scrape + Smart Cache")

product = st.text_input("Enter product name (e.g., 'Sony WH-1000XM4' or 'Nike Air Max')")

if st.button("Find Product Data"):
    if not product:
        st.warning("Enter a product name")
    else:
        with st.spinner("Analyzing product across web APIs..."):
            result = find_product_data_fast(product)

        st.subheader("📦 Result")
        st.json(result)

        if result["gtin"]:
            st.success(f"GTIN Found: {result['gtin']} (Confidence: {result['confidence']})")
        else:
            st.warning("No GTIN found — returning best structured data")

        if result["sources"]:
            st.subheader("🔗 Sources")
            for s in set(result["sources"]):
                st.write(s)
