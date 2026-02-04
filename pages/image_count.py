import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
import pandas as pd
import re
import time
import os
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
    st.markdown("---")
    max_workers = st.slider("Parallel Workers:", 1, 5, 3)
    timeout_seconds = st.slider("Page Timeout:", 10, 30, 20)

# --- 1. DRIVER SETUP ---
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
    # Disable images to speed up scraping (Note: We parse the URLs from HTML, so we don't need to 'see' them)
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return chrome_options

def get_driver(timeout=20):
    try:
        service = Service(get_driver_path())
        driver = webdriver.Chrome(service=service, options=get_chrome_options())
        driver.set_page_load_timeout(timeout)
        return driver
    except Exception:
        return None

# --- 2. EXTRACTION LOGIC (The Core Change) ---
def extract_product_data(soup, data):
    """Specific logic for Warranty and Images."""
    
    # 1. Product Name
    h1 = soup.find('h1')
    data['Product Name'] = h1.text.strip() if h1 else "N/A"

    # 2. Warranty Extraction
    # Strategy: Search in 'Specifications' list and general text for 'Warranty' keywords
    warranty_info = "No Warranty Listed"
    # Look for list items or table cells containing 'warranty'
    elements = soup.find_all(['li', 'td', 'span', 'p'], string=re.compile(r'warranty', re.IGNORECASE))
    
    for el in elements:
        text = el.get_text().strip()
        if len(text) < 100: # Avoid grabbing huge paragraphs
            warranty_info = text
            break
    
    # Fallback: search raw text for patterns like "1 Year Warranty"
    if warranty_info == "No Warranty Listed":
        match = re.search(r'(\d+\s*(?:month|year|day)s?\s+(?:manufacturer\s+)?warranty)', soup.get_text(), re.IGNORECASE)
        if match:
            warranty_info = match.group(1)
            
    data['Warranty'] = warranty_info

    # 3. All Image Links
    # Jumia uses a gallery. We target 'data-src' in the gallery thumbnails or main image.
    img_links = []
    # Find all images in the product gallery/main section
    image_elements = soup.select('div#product-galleries img[data-src], div.-ps-rel img[data-src], div.itm img[data-src]')
    
    for img in image_elements:
        src = img.get('data-src') or img.get('src')
        if src and '/product/' in src:
            # Clean URL
            if src.startswith('//'): src = 'https:' + src
            # Convert to high-res if it's a thumbnail (Jumia specific URL cleaning)
            src = re.sub(r'filters:format\(.*?\)/', '', src) # Remove format filters
            if src not in img_links:
                img_links.append(src)

    data['Image Count'] = len(img_links)
    data['All Image Links'] = " | ".join(img_links) # Separated by pipe for easy splitting later
    
    # 4. SKU
    sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
    if sku_match:
        data['SKU'] = sku_match.group(1)

    return data

# --- 3. SCRAPING ENGINE ---
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
        # If SKU search, click the first result
        if target['type'] == 'sku':
            try:
                first_prod = WebDriverWait(driver, 7).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a.core"))
                )
                driver.get(first_prod.get_attribute("href"))
            except:
                data['Product Name'] = 'SKU_NOT_FOUND'
                return data

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        
        # Parse
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = extract_product_data(soup, data)

    except Exception as e:
        data['Product Name'] = f"ERROR: {str(e)[:30]}"
    finally:
        driver.quit()
    
    return data

# --- 4. MAIN INTERFACE ---
col1, col2 = st.columns(2)
with col1:
    input_text = st.text_area("Paste URLs or SKUs (One per line):", height=150)
with col2:
    input_file = st.file_uploader("Or Upload File:", type=['csv', 'xlsx'])

if st.button("🚀 Start Processing", type="primary"):
    # Process Inputs
    raw_inputs = []
    if input_text:
        raw_inputs.extend([i.strip() for i in input_text.split('\n') if i.strip()])
    if input_file:
        try:
            df_file = pd.read_excel(input_file, header=None) if input_file.name.endswith('.xlsx') else pd.read_csv(input_file, header=None)
            raw_inputs.extend(df_file.iloc[:,0].astype(str).tolist())
        except: st.error("File read error.")

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
            future_to_url = {executor.submit(scrape_item, t, timeout_seconds): t for t in targets}
            
            for i, future in enumerate(as_completed(future_to_url)):
                res = future.result()
                results.append(res)
                progress_bar.progress((i + 1) / len(targets))

        # Display Results
        st.markdown("---")
        df_final = pd.DataFrame(results)
        
        # Stats
        c1, c2, c3 = st.columns(3)
        c1.metric("Items Processed", len(df_final))
        c2.metric("Warranty Found", len(df_final[df_final['Warranty'] != 'No Warranty Listed']))
        c3.metric("Avg Images/Prod", round(df_final['Image Count'].mean(), 1) if not df_final.empty else 0)

        st.dataframe(df_final, use_container_width=True)
        
        csv = df_final.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Report", csv, "jumia_details.csv", "text/csv")
    else:
        st.warning("No valid inputs found.")

st.info("💡 **Note:** 'All Image Links' are separated by a pipe (`|`). You can split them into columns using Excel's 'Text to Columns' feature.")
