import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import re
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Jumia Scraper Pro", page_icon="🛒", layout="wide")

st.title("🛒 Jumia Scraper (V8.3 - SKU Support)")
st.markdown("Extract data using **Product URLs** or just **SKUs**.")

# --- SIDEBAR: SETUP ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # 1. Store Selector (Critical for SKU searches)
    store_region = st.radio(
        "Default Store for SKUs:",
        ("Kenya (jumia.co.ke)", "Uganda (jumia.ug)"),
        index=0
    )
    domain = "jumia.co.ke" if "Kenya" in store_region else "jumia.ug"
    
    st.markdown("---")
    show_browser = st.checkbox("Show Browser (Debug)", value=False)

# --- 1. DRIVER SETUP ---
@st.cache_resource
def install_driver():
    return ChromeDriverManager().install()

def get_driver():
    chrome_options = Options()
    if not show_browser:
        chrome_options.add_argument("--headless=new") 
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        service = Service(install_driver())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception:
        try:
            # Linux/Cloud Fallback
            chrome_options.binary_location = "/usr/bin/chromium"
            service = Service("/usr/bin/chromedriver")
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            st.error(f"Driver Error: {e}")
            return None

    if driver:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# --- 2. INPUT PROCESSING (UPDATED FOR SKUs) ---
def process_inputs(text_input, file_input, default_domain):
    """
    detects if input is a URL or a SKU. 
    If SKU, constructs a search URL using the default domain.
    """
    raw_items = set()
    
    # Text Input
    if text_input:
        items = re.split(r'[\n, ]', text_input)
        for i in items:
            if i.strip(): raw_items.add(i.strip())
            
    # File Input
    if file_input:
        try:
            if file_input.name.endswith('.xlsx'):
                df = pd.read_excel(file_input, header=None)
            else:
                df = pd.read_csv(file_input, header=None)
            for cell in df.values.flatten():
                if str(cell).strip(): raw_items.add(str(cell).strip())
        except Exception as e:
            st.error(f"File Error: {e}")

    final_list = []
    
    for item in raw_items:
        # Case A: It's a full URL
        if item.startswith("http"):
            final_list.append({"type": "url", "value": item})
        # Case B: It's likely a SKU (alphanumeric, 8+ chars)
        elif len(item) > 5: 
            search_url = f"https://www.{default_domain}/catalog/?q={item}"
            final_list.append({"type": "sku", "value": search_url, "original_sku": item})
            
    return final_list

# --- 3. SCRAPING LOGIC ---
def scrape_jumia(target):
    driver = get_driver()
    if not driver: return None

    url = target['value']
    is_sku_search = target['type'] == 'sku'
    
    data = {
        'Input SKU/URL': target.get('original_sku', url),
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
        
        # --- HANDLE SKU SEARCH REDIRECTION ---
        if is_sku_search:
            # Wait to see if we get a product list or a direct product page
            try:
                # Check if we are on a search result page (look for product card)
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1"))
                )
                
                # If we see 'article.prd', we are on a list page. Click the first item.
                search_results = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                if search_results:
                    first_product_link = search_results[0].get_attribute("href")
                    driver.get(first_product_link) # Navigate to actual product
                elif "catalog" in driver.current_url:
                    data['Product Name'] = "SKU_NOT_FOUND"
                    return data
                    
            except Exception:
                pass # Might have redirected directly, proceed to scrape

        # --- STANDARD PRODUCT PAGE SCRAPING ---
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. Product Name
        data['Product Name'] = soup.find('h1').text.strip() if soup.find('h1') else "N/A"

        # 2. Brand
        brand_label = soup.find(string=re.compile(r"Brand:\s*"))
        if brand_label and brand_label.parent:
            data['Brand'] = brand_label.parent.get_text().replace('Brand:', '').strip().split('|')[0].strip()
        if data['Brand'] == "N/A": data['Brand'] = data['Product Name'].split()[0]

        # 3. Seller
        seller_section = soup.select_one('div.-hr.-pas, div.seller-details')
        if seller_section:
            seller_p = seller_section.find('p', class_='-m')
            if seller_p: data['Seller Name'] = seller_p.text.strip()

        # 4. Category
        cats = [b.text.strip() for b in soup.select('.osh-breadcrumb a, .brcbs a') if b.text.strip()]
        data['Category'] = cats[1] if len(cats) > 1 else "N/A"

        # 5. SKU
        sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
        if sku_match: data['SKU'] = sku_match.group(1)

        # 6. Images
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src')
            if src and 'jumia.is' in src and '/product/' in src:
                if src.startswith('//'): src = 'https:' + src
                if src not in data['Image URLs']: data['Image URLs'].append(src)

        # 7. Express
        if soup.find('svg', attrs={'aria-label': 'Jumia Express'}):
            data['Express'] = "Yes"

    except Exception as e:
        data['Product Name'] = "ERROR"
        # st.error(f"Error: {e}") 
    finally:
        driver.quit()
        
    return data

# --- MAIN APP ---

if 'results' not in st.session_state: st.session_state['results'] = []

col1, col2 = st.columns(2)
with col1: text_in = st.text_area("Enter SKUs or URLs:", height=150)
with col2: file_in = st.file_uploader("Upload File (Excel/CSV)")

if st.button("🚀 Start Scraping", type="primary"):
    targets = process_inputs(text_in, file_in, domain)
    
    if not targets:
        st.warning("No valid inputs found.")
    else:
        st.session_state['results'] = []
        prog = st.progress(0)
        
        for i, target in enumerate(targets):
            data = scrape_jumia(target)
            if data and data['Product Name'] not in ["ERROR", "SKU_NOT_FOUND"]:
                st.session_state['results'].append(data)
            prog.progress((i + 1) / len(targets))
        
        st.success("Done!")
        st.rerun()

# --- DISPLAY ---
if st.session_state['results']:
    st.markdown("### 📊 Scraped Data")
    
    clean_data = []
    for item in st.session_state['results']:
        row = item.copy()
        row['Image URL'] = row['Image URLs'][0] if row['Image URLs'] else ""
        del row['Image URLs']
        clean_data.append(row)
        
    df = pd.DataFrame(clean_data)
    
    # Column Order
    cols = ['Input SKU/URL', 'Seller Name', 'SKU', 'Product Name', 'Brand', 'Category', 'Image URL', ' ', 'Express']
    df = df[[c for c in cols if c in df.columns]]
    
    st.dataframe(df, use_container_width=True)
    
    st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "jumia_data.csv", "text/csv")
