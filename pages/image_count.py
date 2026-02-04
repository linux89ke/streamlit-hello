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
st.set_page_config(page_title="Real-Time Jumia Extractor", page_icon="🛡️", layout="wide")
st.title("🛡️ Real-Time Jumia Deep Data Extractor")
st.markdown("Results will appear below in **real-time** as they are scraped.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    region_choice = st.selectbox("Select Region:", ("Kenya (KE)", "Uganda (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    st.markdown("---")
    max_workers = st.slider("Parallel Workers:", 1, 5, 3)
    timeout_seconds = st.slider("Page Timeout:", 10, 45, 25)

# --- 1. DRIVER SETUP ---
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
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return chrome_options

def get_driver(timeout=25):
    try:
        service = Service(get_driver_path())
        driver = webdriver.Chrome(service=service, options=get_chrome_options())
        driver.set_page_load_timeout(timeout)
        return driver
    except:
        return None

# --- 2. EXTRACTION LOGIC ---
def extract_product_data(soup, data):
    h1 = soup.find('h1')
    data['Product Name'] = h1.text.strip() if h1 else "N/A"

    # Warranty Filter
    found_warranty = "No Warranty Listed"
    elements = soup.find_all(['li', 'td', 'span', 'p'], string=re.compile(r'warranty', re.IGNORECASE))
    labels_to_skip = ["warranty address", "warranty type", "warranty card", "warranty:"]
    for el in elements:
        text = el.get_text().strip()
        if any(label in text.lower() for label in labels_to_skip) and len(text) < 25:
            continue
        if len(text) < 120:
            found_warranty = text
            break
    data['Warranty'] = found_warranty

    # Image Gallery (Lazy-load fix)
    img_links = []
    gallery = soup.find('div', id='product-galleries') or soup.find('div', class_='-ps-rel')
    target_tags = gallery.find_all('img') if gallery else soup.find_all('img')
    for img in target_tags:
        url = img.get('data-src') or img.get('src')
        if url and '/product/' in url:
            if url.startswith('//'): url = 'https:' + url
            clean_url = re.sub(r'filters:format\(.*?\)/', '', url)
            if clean_url not in img_links:
                img_links.append(clean_url)

    data['Image Count'] = len(img_links)
    data['All Image Links'] = " | ".join(img_links)
    sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
    if sku_match: data['SKU'] = sku_match.group(1)
    return data

# --- 3. SCRAPING ENGINE ---
def scrape_item(index, target):
    driver = get_driver(25)
    url = target['value']
    data = {
        'order_index': index, # Used to sort back to original order
        'Input': target.get('original_sku', url), 
        'Product Name': 'Pending', 
        'Warranty': 'N/A', 
        'Image Count': 0,
        'SKU': 'N/A'
    }

    if not driver:
        data['Product Name'] = 'DRIVER_ERROR'
        return data

    try:
        driver.get(url)
        if target['type'] == 'sku':
            first_prod = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a.core")))
            driver.get(first_prod.get_attribute("href"))

        driver.execute_script("window.scrollTo(0, 600);")
        time.sleep(2) 
        
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = extract_product_data(soup, data)
    except Exception as e:
        data['Product Name'] = f"FAILED: {str(e)[:30]}"
    finally:
        driver.quit()
    return data

# --- 4. MAIN INTERFACE ---
input_text = st.text_area("Paste URLs or SKUs (One per line):", height=150)

if st.button("🚀 Start Real-Time Extraction", type="primary"):
    raw_inputs = [i.strip() for i in input_text.split('\n') if i.strip()]
    targets = []
    for idx, i in enumerate(raw_inputs):
        if "http" in i:
            targets.append({"index": idx, "type": "url", "value": i})
        else:
            targets.append({"index": idx, "type": "sku", "value": f"https://www.{domain}/catalog/?q={i}", "original_sku": i})

    if targets:
        # UI Placeholders
        progress_bar = st.progress(0)
        status_text = st.empty()
        table_placeholder = st.empty()
        
        results_list = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Map index to the task
            future_to_item = {executor.submit(scrape_item, t['index'], t): t for t in targets}
            
            completed = 0
            for future in as_completed(future_to_item):
                result = future.result()
                results_list.append(result)
                
                completed += 1
                progress = completed / len(targets)
                
                # Update Progress
                progress_bar.progress(progress)
                status_text.text(f"Processed {completed}/{len(targets)} items...")
                
                # Sort current results by order_index to keep UI tidy
                current_df = pd.DataFrame(results_list).sort_values('order_index').drop(columns=['order_index'])
                table_placeholder.dataframe(current_df, use_container_width=True)

        status_text.success(f"✅ Finished! Processed {len(targets)} items.")
        
        # Final Sorted DataFrame for download
        final_df = pd.DataFrame(results_list).sort_values('order_index').drop(columns=['order_index'])
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Final Ordered CSV", csv, "jumia_realtime_data.csv", "text/csv")
    else:
        st.warning("No valid inputs found.")
