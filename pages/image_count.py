import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
import pandas as pd
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Jumia Warranty & Image Tool", page_icon="🛡️", layout="wide")
st.title("🛡️ Jumia Product Detail Extractor")
st.markdown("Extracts **Warranty Information** and **All Gallery Images** from Jumia products.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    region_choice = st.selectbox("Select Region:", ("Kenya (KE)", "Uganda (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    max_workers = st.slider("Parallel Workers:", 1, 5, 3)
    timeout_seconds = st.slider("Page Timeout:", 10, 30, 20)

# --- DRIVER SETUP ---
@st.cache_resource
def get_driver_path():
    try:
        return ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    except:
        return ChromeDriverManager().install()

def get_chrome_options():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"
    )
    return chrome_options

def get_driver(timeout=20):
    try:
        service = Service(get_driver_path())
        driver = webdriver.Chrome(service=service, options=get_chrome_options())
        driver.set_page_load_timeout(timeout)
        return driver
    except:
        return None

# --- EXTRACTION LOGIC ---
def extract_product_data(soup, data):

    # Product Name
    h1 = soup.find('h1')
    data['Product Name'] = h1.text.strip() if h1 else "N/A"

    # -------- WARRANTY --------
    warranty_info = "No Warranty Listed"

    specs = soup.select("table tr")
    for row in specs:
        txt = row.get_text(" ", strip=True)
        if "warranty" in txt.lower():
            warranty_info = txt
            break

    if warranty_info == "No Warranty Listed":
        elements = soup.find_all(string=re.compile(r'warranty', re.I))
        for el in elements:
            t = el.strip()
            if 5 < len(t) < 120:
                warranty_info = t
                break

    if warranty_info == "No Warranty Listed":
        match = re.search(r'(\d+\s*(month|year|day)s?\s+warranty)', soup.get_text(), re.I)
        if match:
            warranty_info = match.group(1)

    data['Warranty'] = warranty_info

    # -------- IMAGES (FIXED) --------
    img_links = set()

    # method A — all img attributes
    for img in soup.find_all("img"):
        for attr in ["data-src", "data-lazy", "data-zoom-image", "src"]:
            src = img.get(attr)
            if not src:
                continue

            if src.startswith("//"):
                src = "https:" + src

            if "/product/" in src or "cms" in src:
                src = re.sub(r'filters:.*?/', '', src)
                img_links.add(src)

    # method B — gallery anchors
    for a in soup.select("#product-galleries a[href]"):
        href = a.get("href")
        if href and "/product/" in href:
            if href.startswith("//"):
                href = "https:" + href
            img_links.add(href)

    # method C — script embedded images
    for script in soup.find_all("script"):
        if script.string and "product" in script.string.lower():
            matches = re.findall(r'https://[^"]+/product/[^"]+\.(?:jpg|jpeg|png|webp)', script.string, re.I)
            for m in matches:
                img_links.add(m)

    img_links = sorted(img_links)
    data['Image Count'] = len(img_links)
    data['All Image Links'] = " | ".join(img_links)

    # -------- SKU --------
    sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-_\/]+)', soup.get_text(), re.I)
    if sku_match:
        data['SKU'] = sku_match.group(1)

    return data

# --- SCRAPING ENGINE ---
def scrape_item(target, timeout=20):
    driver = get_driver(timeout)
    url = target['value']

    data = {
        'Input': target.get('original_sku', url),
        'Product Name': 'Pending',
        'SKU': 'N/A',
        'Warranty': 'N/A',
        'Image Count': 0,
        'All Image Links': ''
    }

    if not driver:
        data['Product Name'] = 'DRIVER_ERROR'
        return data

    try:
        driver.get(url)

        if target['type'] == 'sku':
            try:
                first_prod = WebDriverWait(driver, 7).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a"))
                )
                driver.get(first_prod.get_attribute("href"))
            except:
                data['Product Name'] = 'SKU_NOT_FOUND'
                driver.quit()
                return data

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )

        time.sleep(2)  # allow gallery to load

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = extract_product_data(soup, data)

    except Exception as e:
        data['Product Name'] = f"ERROR: {str(e)[:30]}"

    finally:
        driver.quit()

    return data

# --- MAIN INTERFACE ---
col1, col2 = st.columns(2)

with col1:
    input_text = st.text_area("Paste URLs or SKUs (One per line):", height=150)

with col2:
    input_file = st.file_uploader("Or Upload File:", type=['csv', 'xlsx'])

if st.button("🚀 Start Processing", type="primary"):

    raw_inputs = []

    if input_text:
        raw_inputs.extend([i.strip() for i in input_text.split('\n') if i.strip()])

    if input_file:
        df_file = pd.read_excel(input_file, header=None) if input_file.name.endswith('.xlsx') else pd.read_csv(input_file, header=None)
        raw_inputs.extend(df_file.iloc[:,0].astype(str).tolist())

    targets = []

    for item in list(set(raw_inputs)):
        if "http" in item:
            targets.append({"type": "url", "value": item})
        else:
            search_url = f"https://www.{domain}/catalog/?q={item}"
            targets.append({"type": "sku", "value": search_url, "original_sku": item})

    if targets:
        progress_bar = st.progress(0)
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(scrape_item, t, timeout_seconds): t for t in targets
            }

            for i, future in enumerate(as_completed(future_to_url)):
                results.append(future.result())
                progress_bar.progress((i + 1) / len(targets))

        df_final = pd.DataFrame(results)

        c1, c2, c3 = st.columns(3)
        c1.metric("Items Processed", len(df_final))
        c2.metric("Warranty Found", len(df_final[df_final['Warranty'] != 'No Warranty Listed']))
        c3.metric("Avg Images/Prod", round(df_final['Image Count'].mean(), 1))

        st.dataframe(df_final, use_container_width=True)

        csv = df_final.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Report", csv, "jumia_details.csv")

    else:
        st.warning("No valid inputs found.")

st.info("💡 Image links are pipe-separated ( | ) for easy Excel split.")
