import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import time
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
# GTIN EXTRACTION
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

def extract_from_snippet(snippet):
    return extract_gtins(snippet or "")

# =========================
# VALIDATION
# =========================
def validate_ean13(code):
    if len(code) != 13:
        return False
    digits = list(map(int, code))
    checksum = sum(digits[:-1:2]) + sum(d * 3 for d in digits[1:-1:2])
    return (10 - (checksum % 10)) % 10 == digits[-1]

# =========================
# SEARCH (SERPAPI)
# =========================
def serpapi_search(query):
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

# =========================
# FALLBACK SEARCH
# =========================
def fallback_search(query):
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

# =========================
# FETCH PAGE
# =========================
def fetch_page(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        return res.text
    except:
        return ""

# =========================
# MAIN ENGINE
# =========================
def find_product_data(product_name):
    product_name = enhance_query(product_name)

    brand = detect_brand(product_name)
    model = detect_model(product_name)

    queries = [
        f'"{product_name}" EAN',
        f'"{product_name}" UPC',
        f'{product_name} barcode',
        f'{product_name} EAN site:amazon.com',
        f'{product_name} UPC site:ebay.com',
        f'{product_name} barcode site:jumia.com',
        f'{product_name} barcode site:jiji.co.ke',
        f'{product_name} specifications',
    ]

    # Prioritize model search
    if model:
        queries.insert(0, f'"{model}" EAN')
        queries.insert(1, f'{model} UPC')

    gtin_scores = defaultdict(int)
    sources = defaultdict(list)

    for q in queries:
        st.write(f"🔎 {q}")

        results = serpapi_search(q)
        if not results:
            results = fallback_search(q)

        for r in results:
            raw_url = r.get("link")
            url = clean_url(raw_url)

            if not url or not is_valid_url(url):
                continue

            st.write(f"➡️ {url}")

            # Extract from snippet first (fast win)
            snippet_gtins = extract_from_snippet(r.get("snippet", ""))
            for g in snippet_gtins:
                gtin_scores[g] += 2
                sources[g].append(url)

            html = fetch_page(url)
            if not html:
                continue

            gtins = extract_gtins(html)

            for g in gtins:
                score = 1

                if validate_ean13(g):
                    score += 2

                if brand and brand.lower() in html.lower():
                    score += 1

                gtin_scores[g] += score
                sources[g].append(url)

            time.sleep(1.5)

    if not gtin_scores:
        return {
            "brand": brand,
            "model": model,
            "gtin": None,
            "confidence": 0,
            "status": "not_found",
            "reason": "GTIN not publicly indexed",
            "sources": []
        }

    best_gtin = max(gtin_scores, key=gtin_scores.get)
    confidence = min(1.0, gtin_scores[best_gtin] / 10)

    return {
        "brand": brand,
        "model": model,
        "gtin": best_gtin,
        "confidence": round(confidence, 2),
        "status": "found",
        "sources": sources[best_gtin]
    }

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="GTIN Finder PRO", layout="wide")

st.title("🔍 GTIN Finder PRO (QC Ready)")
st.caption("Search scraping + smart detection + scoring")

product = st.text_input("Enter product name")

if st.button("Find Product Data"):
    if not product:
        st.warning("Enter a product name")
    else:
        with st.spinner("Analyzing product across web..."):
            result = find_product_data(product)

        st.subheader("📦 Result")
        st.json(result)

        if result["gtin"]:
            st.success(f"GTIN Found: {result['gtin']} (Confidence: {result['confidence']})")
        else:
            st.warning("No GTIN found — returning best structured data")

        if result["sources"]:
            st.subheader("🔗 Sources")
            for s in result["sources"]:
                st.write(s)
