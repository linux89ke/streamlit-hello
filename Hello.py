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
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Marketplace Data Tool", page_icon="📊", layout="wide")
st.title("🛒 E-Commerce Data Extractor (V9.1 - Driver Fix)")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    region_choice = st.selectbox("Select Region:", ("Region 1 (KE)", "Region 2 (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    st.markdown("---")
    show_browser = st.checkbox("Show Browser (Debug Mode)", value=False)

# --- 1. ROBUST DRIVER SETUP ---
@st.cache_resource
def get_driver_path():
    """Attempt to install the correct driver for Chromium."""
    try:
        # Try installing specifically for Chromium
        return ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    except Exception:
        # If that fails, try standard Chrome (sometimes Chromium is aliased)
        return ChromeDriverManager().install()

def get_driver():
    chrome_options = Options()
    if not show_browser:
        chrome_options.add_argument("--headless=new") 
    
    # Critical Stability Arguments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # 1. DETECT BROWSER LOCATION
    # We explicitly look for the binary to avoid the "Driver Error" mismatch
    possible_paths = ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome-stable"]
    binary_path = None
    for path in possible_paths:
        if os.path.exists(path):
            binary_path = path
            break
    
    if binary_path:
        chrome_options.binary_location = binary_path

    driver = None
    try:
        # 2. ATTEMPT TO INSTALL MATCHING DRIVER
        driver_path = get_driver_path()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
    except Exception as e:
        # 3. FALLBACK (Only if automatic setup fails)
        try:
            # If explicit paths failed, try generic initialization
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e2:
            st.error(f"CRITICAL DRIVER ERROR: {e}\nFallback Error: {e2}")
            return None

    if driver:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

# --- 2. INPUT PROCESSING ---
def process_inputs(text_input, file_input, default_domain):
    raw_items = set()
    if text_input:
        items = re.split(r'[\n,]', text_input)
        for i in items:
            if i.strip(): raw_items.add(i.strip())
            
    if file_input:
        try:
            if file_input.name.endswith('.xlsx'):
                df = pd.read_excel(file_input, header=None)
            else:
                df = pd.read_csv(file_input, header=None)
            for cell in df.values.flatten():
                cell_str = str(cell).strip()
                if cell_str and cell_str.lower() != 'nan':
                    raw_items.add(cell_str)
        except Exception as e:
            st.error(f"Error reading file: {e}")

    final_targets = []
    for item in raw_items:
        clean_val = item.replace("SKU:", "").strip()
        if "http" in clean_val or "www." in clean_val:
            if not clean_val.startswith("http"): clean_val = "https://" + clean_val
            final_targets.append({"type": "url", "value": clean_val})
        elif len(clean_val) > 3: 
            search_url = f"https://www.{default_domain}/catalog/?q={clean_val}"
            final_targets.append({"type": "sku", "value": search_url, "original_sku": clean_val})
            
    return final_targets

# --- 3. SCRAPING ENGINE ---
def scrape_item(target):
    driver = get_driver()
    if not driver: return {'Product Name': 'SYSTEM_ERROR'}

    url = target['value']
    is_sku_search = target['type'] == 'sku'
    
    data = {
        'Input Source': target.get('original_sku', url),
        'Product Name': 'N/A', 
        'Brand': 'N/A', 
        'Seller Name': 'N/A', 
        'Category': 'N/A', 
        'SKU': 'N/A', 
        'Image URLs': [], 
        ' ': '', 
        'Express': 'No'
    }

    try:
        driver.get(url)
        if is_sku_search:
            try:
                WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
                if "There are no results for" in driver.page_source:
                    data['Product Name'] = "SKU_NOT_FOUND"
                    driver.quit()
                    return data
                product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                if product_links:
                    driver.get(product_links[0].get_attribute("href"))
            except Exception:
                pass

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        driver.execute_script("window.scrollTo(0, 600);")
        time.sleep(1.5)
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Extraction
        h1 = soup.find('h1')
        data['Product Name'] = h1.text.strip() if h1 else "N/A"

        brand_label = soup.find(string=re.compile(r"Brand:\s*"))
        if brand_label and brand_label.parent:
            brand_link = brand_label.parent.find('a')
            data['Brand'] = brand_link.text.strip() if brand_link else brand_label.parent.get_text().replace('Brand:', '').split('|')[0].strip()
        if data['Brand'] in ["N/A", ""] or "generic" in data['Brand'].lower():
             data['Brand'] = data['Product Name'].split()[0]

        seller_box = soup.select_one('div.-hr.-pas, div.seller-details')
        if seller_box:
            p_tag = seller_box.find('p', class_='-m')
            if p_tag: data['Seller Name'] = p_tag.text.strip()
        if any(x in data['Seller Name'].lower() for x in ['details', 'follow', 'sell on', 'n/a']):
             data['Seller Name'] = "N/A"

        breadcrumbs = soup.select('.osh-breadcrumb a, .brcbs a')
        cats = [b.text.strip() for b in breadcrumbs if b.text.strip()]
        data['Category'] = cats[1] if len(cats) > 1 else (cats[0] if cats else "N/A")

        sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
        if sku_match: data['SKU'] = sku_match.group(1)
        elif is_sku_search: data['SKU'] = target['original_sku']

        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src')
            if src and '/product/' in src:
                if src.startswith('//'): src = 'https:' + src
                if src not in data['Image URLs']: data['Image URLs'].append(src)

        if soup.find('svg', attrs={'aria-label': 'Jumia Express'}):
            data['Express'] = "Yes"

    except Exception:
        data['Product Name'] = "ERROR_FETCHING"
    finally:
        driver.quit()
    return data

# --- MAIN APP ---
if 'scraped_results' not in st.session_state: st.session_state['scraped_results'] = []

col_txt, col_upl = st.columns(2)
with col_txt: text_in = st.text_area("Paste SKUs/Links:", height=150)
with col_upl: file_in = st.file_uploader("Upload Excel/CSV:", type=['xlsx', 'csv'])

if st.button("🚀 Start Extraction", type="primary"):
    targets = process_inputs(text_in, file_in, domain)
    if not targets:
        st.warning("No valid data found.")
    else:
        st.session_state['scraped_results'] = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        for i, target in enumerate(targets):
            status_text.text(f"Processing {i+1}/{len(targets)}: {target.get('original_sku', 'Link')}")
            result = scrape_item(target)
            if result and result['Product Name'] not in ["SYSTEM_ERROR", "SKU_NOT_FOUND"]:
                st.session_state['scraped_results'].append(result)
            progress_bar.progress((i + 1) / len(targets))
        status_text.success("Done!")
        st.rerun()

if st.session_state['scraped_results']:
    st.markdown("---")
    export_rows = []
    for item in st.session_state['scraped_results']:
        row = item.copy()
        row['Image URL'] = row['Image URLs'][0] if row['Image URLs'] else "N/A"
        del row['Image URLs']
        export_rows.append(row)
    df = pd.DataFrame(export_rows)
    cols = ['Seller Name', 'SKU', 'Product Name', 'Brand', 'Category', 'Image URL', ' ', 'Express', 'Input Source']
    df = df[[c for c in cols if c in df.columns]]
    st.dataframe(df, use_container_width=True)
    st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "data.csv", "text/csv")
