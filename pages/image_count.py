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
st.set_page_config(page_title="Jumia Deep Data Tool", page_icon="🛡️", layout="wide")
st.title("🛡️ Jumia Product Detail Extractor")
st.markdown("Fixed: Now triggers **Lazy Loading** to prevent zero image results.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    region_choice = st.selectbox("Select Region:", ("Kenya (KE)", "Uganda (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    st.markdown("---")
    max_workers = st.slider("Parallel Workers:", 1, 5, 3)
    timeout_seconds = st.slider("Page Timeout:", 10, 45, 25)

@st.cache_resource
def get_driver_path():
    try:
        return ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    except Exception:
        return ChromeDriverManager().install()

def get_chrome_options():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # FIX: We removed the "disable images" preference to allow lazy-load scripts to run
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return chrome_options

def get_driver(timeout=25):
    try:
        service = Service(get_driver_path())
        driver = webdriver.Chrome(service=service, options=get_chrome_options())
        driver.set_page_load_timeout(timeout)
        return driver
    except Exception:
        return None

# --- EXTRACTION LOGIC ---
def extract_product_data(soup, data):
    h1 = soup.find('h1')
    data['Product Name'] = h1.text.strip() if h1 else "N/A"

    # Warranty Extraction
    warranty_info = "No Warranty Listed"
    elements = soup.find_all(['li', 'td', 'span', 'p'], string=re.compile(r'warranty', re.IGNORECASE))
    for el in elements:
        text = el.get_text().strip()
        if len(text) < 100: 
            warranty_info = text
            break
    if warranty_info == "No Warranty Listed":
        match = re.search(r'(\d+\s*(?:month|year|day)s?\s+(?:manufacturer\s+)?warranty)', soup.get_text(), re.IGNORECASE)
        if match: warranty_info = match.group(1)
    data['Warranty'] = warranty_info

    # Image Extraction (Targeting data-src for Lazy Load)
    img_links = []
    # Jumia specific gallery containers
    image_elements = soup.select('div#product-galleries img[data-src], div.-ps-rel img[data-src], div.itm img[data-src]')
    
    for img in image_elements:
        # Check data-src first, fallback to src
        src = img.get('data-src') or img.get('src')
        if src and '/product/' in src:
            if src.startswith('//'): src = 'https:' + src
            src = re.sub(r'filters:format\(.*?\)/', '', src)
            if src not in img_links:
                img_links.append(src)

    data['Image Count'] = len(img_links)
    data['All Image Links'] = " | ".join(img_links)
    
    sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
    if sku_match: data['SKU'] = sku_match.group(1)
    return data

# --- SCRAPING ENGINE ---
def scrape_item(index, target, timeout=25):
    driver = get_driver(timeout)
    url = target['value']
    data = {'order_index': index, 'Input': target.get('original_sku', url), 'Product Name': 'Pending', 'SKU': 'N/A', 'Warranty': 'N/A', 'Image Count': 0, 'All Image Links': ''}

    if not driver:
        data['Product Name'] = 'DRIVER_ERROR'
        return data

    try:
        driver.get(url)
        if target['type'] == 'sku':
            first_prod = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a.core")))
            driver.get(first_prod.get_attribute("href"))

        # --- FIX: Trigger Lazy Loading ---
        driver.execute_script("window.scrollTo(0, 500);") # Scroll to gallery area
        time.sleep(2) # Wait for JS to load images
        
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = extract_product_data(soup, data)
    except Exception as e:
        data['Product Name'] = f"ERROR: {str(e)[:30]}"
    finally:
        driver.quit()
    return data

# --- MAIN INTERFACE ---
input_text = st.text_area("Paste URLs or SKUs (One per line):", height=150)

if st.button("🚀 Start Ordered Processing", type="primary"):
    raw_inputs = [i.strip() for i in input_text.split('\n') if i.strip()]
    targets = [{"index": idx, "type": "url", "value": i} if "http" in i else {"index": idx, "type": "sku", "value": f"https://www.{domain}/catalog/?q={i}", "original_sku": i} for idx, i in enumerate(raw_inputs)]

    if targets:
        progress_bar = st.progress(0)
        table_placeholder = st.empty()
        results_list = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(scrape_item, t['index'], t, timeout_seconds): t for t in targets}
            for i, future in enumerate(as_completed(future_to_url)):
                results_list.append(future.result())
                progress_bar.progress((i + 1) / len(targets))
                
                # Update Real-Time table sorted by input order
                current_df = pd.DataFrame(results_list).sort_values('order_index').drop(columns=['order_index'])
                table_placeholder.dataframe(current_df, use_container_width=True)

        final_df = pd.DataFrame(results_list).sort_values('order_index').drop(columns=['order_index'])
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Ordered Report", csv, "jumia_details.csv", "text/csv")
