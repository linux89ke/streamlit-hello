import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import time
import os
from collections import defaultdict

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
    # captures patterns like DAV-DZ650, SM-A135F, etc.
    matches = re.findall(r"\b[A-Z0-9\-]{5,}\b", text.upper())
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

# =========================
# VALIDATION (EAN-13)
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
        for a in soup.select(".result__a"):
            results.append({
                "title": a.get_text(),
                "link": a.get("href")
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
        f'{product_name} specifications',
        f'{product_name} tech specs',
    ]

    gtin_scores = defaultdict(int)
    sources = defaultdict(list)

    for q in queries:
        st.write(f"🔎 {q}")

        results = serpapi_search(q)
        if not results:
            results = fallback_search(q)

        for r in results[:5]:
            url = r.get("link")
            if not url:
                continue

            st.write(f"➡️ {url}")

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
            "sources": []
        }

    best_gtin = max(gtin_scores, key=gtin_scores.get)

    confidence = min(1.0, gtin_scores[best_gtin] / 10)

    return {
        "brand": brand,
        "model": model,
        "gtin": best_gtin,
        "confidence": round(confidence, 2),
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
