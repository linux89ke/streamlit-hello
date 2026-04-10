import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import time
import os

# =========================
# CONFIG
# =========================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# =========================
# GTIN EXTRACTION
# =========================
def extract_gtins(text):
    patterns = [
        r"\b\d{12}\b",  # UPC
        r"\b\d{13}\b",  # EAN
        r"\b\d{14}\b",  # GTIN-14
    ]
    results = set()
    for p in patterns:
        matches = re.findall(p, text)
        results.update(matches)
    return list(results)

# =========================
# SIMPLE CHECKSUM (EAN-13)
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
    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google"
    }

    try:
        res = requests.get(url, params=params)
        data = res.json()
        results = []

        for r in data.get("organic_results", []):
            results.append({
                "title": r.get("title"),
                "link": r.get("link"),
                "snippet": r.get("snippet", "")
            })

        return results

    except:
        return []

# =========================
# FALLBACK: SIMPLE SEARCH (DuckDuckGo HTML)
# =========================
def fallback_search(query):
    url = f"https://duckduckgo.com/html/?q={query}"
    try:
        res = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(res.text, "html.parser")

        results = []
        for a in soup.select(".result__a"):
            results.append({
                "title": a.get_text(),
                "link": a.get("href"),
                "snippet": ""
            })

        return results[:5]
    except:
        return []

# =========================
# FETCH PAGE CONTENT
# =========================
def fetch_page(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        return res.text
    except:
        return ""

# =========================
# MAIN GTIN SEARCH
# =========================
def find_gtin(product_name):
    queries = [
        f'"{product_name}" EAN',
        f'"{product_name}" UPC',
        f'"{product_name}" barcode',
        f'"{product_name}" GTIN',
    ]

    all_gtins = {}

    for q in queries:
        st.write(f"🔎 Searching: {q}")

        results = serpapi_search(q)
        if not results:
            results = fallback_search(q)

        for r in results[:5]:
            url = r["link"]
            st.write(f"➡️ Checking: {url}")

            html = fetch_page(url)
            if not html:
                continue

            gtins = extract_gtins(html)

            for g in gtins:
                if validate_ean13(g):
                    all_gtins[g] = all_gtins.get(g, 0) + 2
                else:
                    all_gtins[g] = all_gtins.get(g, 0) + 1

            time.sleep(2)  # polite delay

    return sorted(all_gtins.items(), key=lambda x: x[1], reverse=True)

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="GTIN Finder", layout="wide")

st.title("🔍 GTIN Finder (Search Scraping)")
st.write("Find EAN / UPC / GTIN from product name using search scraping")

product = st.text_input("Enter product name")

if st.button("Find GTIN"):
    if not product:
        st.warning("Enter a product name")
    else:
        with st.spinner("Searching across the web..."):
            results = find_gtin(product)

        if results:
            st.success("Results found!")

            for gtin, score in results[:10]:
                st.write(f"**GTIN:** {gtin} | Score: {score}")
        else:
            st.error("No GTIN found")
