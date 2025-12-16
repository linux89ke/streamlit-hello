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
st.set_page_config(page_title="Scraper Pro", page_icon="🛒", layout="wide")

st.title(" Scraper")
st.markdown("Extract product data")

# --- SIDEBAR: SETUP ---
with st.sidebar:
    st.header("⚙️ Configuration")
    st.info("Paste links or upload an Excel file.")
    show_browser = st.checkbox("Show Browser (Debug Mode)", value=False, help="Uncheck for faster, headless scraping.")

# --- 1. DRIVER SETUP FUNCTION ---
@st.cache_resource
def install_driver():
    """Caches the driver installation to speed up re-runs."""
    return ChromeDriverManager().install()

def get_driver():
    """Initializes Chrome Driver with cross-platform compatibility."""
    chrome_options = Options()
    
    if not show_browser:
        chrome_options.add_argument("--headless=new") 
        
    # Standard Anti-Detection Arguments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(install_driver())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        try:
            # Fallback for Linux/Server environments
            chrome_options.binary_location = "/usr/bin/chromium"
            service = Service("/usr/bin/chromedriver")
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e2:
            st.error(f"CRITICAL: Failed to initialize driver.\nError: {e2}")
            return None
            
    if driver:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

# --- 2. URL INPUT HANDLING ---
def get_urls_from_input(url_text, uploaded_file):
    urls = set()
    VALID_DOMAINS = ["jumia.co.ke", "jumia.ug"]

    if url_text:
        text_urls = re.split(r'[\n, ]', url_text)
        for url in text_urls:
            url = url.strip()
            if any(domain in url for domain in VALID_DOMAINS) and url.startswith("http"):
                urls.add(url)
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file, header=None)
            else: 
                df = pd.read_csv(uploaded_file, header=None)
            for cell in df.values.flatten():
                cell_str = str(cell)
                if any(domain in cell_str for domain in VALID_DOMAINS) and cell_str.startswith("http"):
                    urls.add(cell_str)
        except Exception as e:
            st.error(f"Error reading file: {e}")
    
    return list(urls)

# --- 3. ROBUST SCRAPING FUNCTION ---
def scrape_jumia(url):
    driver = get_driver()
    if not driver:
        return {'URL': url, 'Product Name': 'DRIVER_ERROR'}

    data = {
        'URL': url, 
        'Product Name': 'N/A', 
        'Brand': 'N/A', 
        'Seller Name': 'N/A', 
        'Category': 'N/A', 
        'SKU': 'N/A', 
        'Image URLs': [],
        ' ': '',  # The blank column content
        'Express': 'No' 
    }

    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1.0) 
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. Product Name
        name_tag = soup.find('h1')
        if name_tag:
            data['Product Name'] = name_tag.text.strip()

        # 2. Brand
        brand_label = soup.find(string=re.compile(r"Brand:\s*"))
        if brand_label and brand_label.parent:
            brand_link = brand_label.parent.find('a')
            if brand_link:
                data['Brand'] = brand_link.text.strip()
            else:
                data['Brand'] = brand_label.parent.get_text().replace('Brand:', '').strip().split('|')[0].strip()
        
        if data['Brand'] in ["N/A", ""] or "jumia" in data['Brand'].lower():
             data['Brand'] = data['Product Name'].split()[0]

        # 3. Seller Name
        seller_section = soup.select_one('div.-hr.-pas, div.seller-details')
        if seller_section:
            seller_p = seller_section.find('p', class_='-m')
            if seller_p:
                data['Seller Name'] = seller_p.text.strip()
        
        if any(x in data['Seller Name'].lower() for x in ['details', 'follow', 'sell on jumia', 'n/a']):
             data['Seller Name'] = "N/A"

        # 4. Category
        breadcrumbs = soup.select('div.brcbs a, nav.brcbs a, .osh-breadcrumb a')
        cats = [b.text.strip() for b in breadcrumbs if b.text.strip().lower() not in ['home', 'jumia', '']]
        cats = [c for c in cats if c != data['Product Name']]
        full_category = " > ".join(dict.fromkeys(cats))
        data['Category'] = full_category.split(' > ')[0] if full_category else "N/A"

        # 5. SKU
        page_text = soup.get_text()
        sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', page_text) 
        if sku_match:
            data['SKU'] = sku_match.group(1).strip()
        if data['SKU'] == "N/A":
             url_sku_match = re.search(r'-([A-Z0-9]+)\.html', url)
             if url_sku_match:
                 data['SKU'] = url_sku_match.group(1)

        # 6. Images
        images = soup.find_all('img')
        for img in images:
            src = img.get('data-src') or img.get('src')
            if src and 'jumia.is' in src and '/product/' in src:
                if src.startswith('//'): src = 'https:' + src
                if src not in data['Image URLs']: 
                    data['Image URLs'].append(src)

        # 7. JUMIA EXPRESS DETECTION
        express_indicator = soup.find('svg', attrs={'aria-label': 'Jumia Express'})
        if express_indicator:
            data['Express'] = "Yes"
        
    except Exception as e:
        data['Product Name'] = "SCRAPE_FAILED"
        st.error(f"Error scraping {url}: {e}")
    finally:
        driver.quit()
        
    return data

# --- MAIN APP LOGIC ---

if 'all_product_data' not in st.session_state:
    st.session_state['all_product_data'] = []

st.markdown("---")
col_text, col_file = st.columns(2)

with col_text:
    url_text = st.text_area("Paste URLs:", height=150)

with col_file:
    uploaded_file = st.file_uploader("Upload Excel/CSV:", type=['xlsx', 'csv'])

col_btn, col_stop = st.columns([1, 4])
start_btn = col_btn.button("Start Scraping", type="primary")

if start_btn:
    urls_to_scrape = get_urls_from_input(url_text, uploaded_file)
    
    if not urls_to_scrape:
        st.warning("⚠️ No valid URLs found.")
    else:
        st.session_state['all_product_data'] = []
        total_urls = len(urls_to_scrape)
        progress_bar = st.progress(0)
        
        for i, url in enumerate(urls_to_scrape):
            scraped_data = scrape_jumia(url)
            if scraped_data.get('Product Name') not in ['DRIVER_ERROR', 'SCRAPE_FAILED']:
                st.session_state['all_product_data'].append(scraped_data)
            progress_bar.progress((i + 1) / total_urls)
        
        st.success(" Complete!")
        st.rerun()

# --- RESULTS DISPLAY ---

if st.session_state['all_product_data']:
    st.markdown("---")
    st.subheader(f"Results")

    display_data = []
    for item in st.session_state['all_product_data']:
        row = item.copy()
        row['Image URL'] = item['Image URLs'][0] if item['Image URLs'] else "N/A"
        del row['Image URLs']
        display_data.append(row)
    
    df = pd.DataFrame(display_data)
    
    # Updated Column Order: Added a blank column ' ' between Image URL and Express
    cols = ['Seller Name', 'SKU', 'Product Name', 'Brand', 'Category', 'Image URL', ' ', 'Express', 'URL']
    
    # Ensure existing columns are selected (handle potential missing keys gracefully)
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]

    st.dataframe(df, use_container_width=True)

    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name="jumia_express_results_v2.csv",
        mime="text/csv",
        type="primary"
    )
    
    if st.button(" Clear Results"):
        st.session_state['all_product_data'] = []
        st.rerun()
