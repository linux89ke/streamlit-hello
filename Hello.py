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
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Marketplace Data Tool", page_icon="📊", layout="wide")
st.title("🛒 E-Commerce Data Extractor (V10.0 - Optimized)")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    region_choice = st.selectbox("Select Region:", ("Region 1 (KE)", "Region 2 (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    st.markdown("---")
    show_browser = st.checkbox("Show Browser (Debug Mode)", value=False)
    max_workers = st.slider("Parallel Workers (faster but more resources):", 1, 5, 3)
    st.info(f"⚡ Using {max_workers} parallel workers")

# --- 1. OPTIMIZED DRIVER SETUP ---
@st.cache_resource
def get_driver_path():
    """Cache driver installation to avoid repeated downloads."""
    try:
        return ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    except Exception:
        return ChromeDriverManager().install()

def get_chrome_options(headless=True):
    """Centralized Chrome options for consistency and reusability."""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    
    # Performance & Stability optimizations
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")  # Reduces overhead in headless
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Disable images for faster loading (if images aren't critical during scrape)
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # Disable images
        "profile.default_content_setting_values.notifications": 2,  # Disable notifications
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Detect browser binary
    possible_paths = ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome-stable"]
    for path in possible_paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            break
    
    return chrome_options

def get_driver(headless=True):
    """Create and return a configured WebDriver instance."""
    chrome_options = get_chrome_options(headless)
    driver = None
    
    try:
        driver_path = get_driver_path()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e2:
            st.error(f"CRITICAL DRIVER ERROR: {e}\nFallback Error: {e2}")
            return None

    if driver:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # Set page load timeout to avoid hanging
        driver.set_page_load_timeout(30)
    
    return driver

# --- 2. OPTIMIZED INPUT PROCESSING ---
def process_inputs(text_input, file_input, default_domain):
    """Process and deduplicate inputs more efficiently."""
    raw_items = set()
    
    # Process text input
    if text_input:
        items = re.split(r'[\n,]', text_input)
        raw_items.update(i.strip() for i in items if i.strip())
    
    # Process file input
    if file_input:
        try:
            df = pd.read_excel(file_input, header=None) if file_input.name.endswith('.xlsx') \
                 else pd.read_csv(file_input, header=None)
            
            # Flatten and filter in one go
            raw_items.update(
                str(cell).strip() 
                for cell in df.values.flatten() 
                if str(cell).strip() and str(cell).lower() != 'nan'
            )
        except Exception as e:
            st.error(f"Error reading file: {e}")

    # Build final targets
    final_targets = []
    for item in raw_items:
        clean_val = item.replace("SKU:", "").strip()
        
        if "http" in clean_val or "www." in clean_val:
            if not clean_val.startswith("http"):
                clean_val = "https://" + clean_val
            final_targets.append({"type": "url", "value": clean_val})
        elif len(clean_val) > 3:
            search_url = f"https://www.{default_domain}/catalog/?q={clean_val}"
            final_targets.append({"type": "sku", "value": search_url, "original_sku": clean_val})
    
    return final_targets

# --- 3. OPTIMIZED SCRAPING ENGINE ---
def extract_product_data(soup, data, is_sku_search, target):
    """Extract all product data from parsed HTML (separate from driver operations)."""
    
    # Product Name
    h1 = soup.find('h1')
    data['Product Name'] = h1.text.strip() if h1 else "N/A"

    # Brand - optimized extraction
    brand_label = soup.find(string=re.compile(r"Brand:\s*"))
    if brand_label and brand_label.parent:
        brand_link = brand_label.parent.find('a')
        data['Brand'] = brand_link.text.strip() if brand_link else \
                       brand_label.parent.get_text().replace('Brand:', '').split('|')[0].strip()
    
    if data['Brand'] in ["N/A", ""] or "generic" in data['Brand'].lower():
        data['Brand'] = data['Product Name'].split()[0] if data['Product Name'] != "N/A" else "N/A"

    # Seller Name
    seller_box = soup.select_one('div.-hr.-pas, div.seller-details')
    if seller_box:
        p_tag = seller_box.find('p', class_='-m')
        if p_tag:
            seller_text = p_tag.text.strip()
            if not any(x in seller_text.lower() for x in ['details', 'follow', 'sell on']):
                data['Seller Name'] = seller_text

    # Category - optimized
    breadcrumbs = soup.select('.osh-breadcrumb a, .brcbs a')
    cats = [b.text.strip() for b in breadcrumbs if b.text.strip()]
    data['Category'] = cats[1] if len(cats) > 1 else (cats[0] if cats else "N/A")

    # SKU
    sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
    if sku_match:
        data['SKU'] = sku_match.group(1)
    elif is_sku_search:
        data['SKU'] = target['original_sku']

    # Images - only extract first one for speed (usually sufficient)
    for img in soup.find_all('img', limit=5):  # Limit search
        src = img.get('data-src') or img.get('src')
        if src and '/product/' in src:
            if src.startswith('//'):
                src = 'https:' + src
            if src not in data['Image URLs']:
                data['Image URLs'].append(src)
                break  # Only need first image for speed

    # Express delivery check
    if soup.find('svg', attrs={'aria-label': 'Jumia Express'}):
        data['Express'] = "Yes"
    
    return data

def scrape_item(target, headless=True):
    """Scrape a single item - now optimized for parallel execution."""
    driver = get_driver(headless)
    if not driver:
        return {'Product Name': 'SYSTEM_ERROR', 'Input Source': target.get('original_sku', target['value'])}

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
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1"))
                )
                
                if "There are no results for" in driver.page_source:
                    data['Product Name'] = "SKU_NOT_FOUND"
                    return data
                
                product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                if product_links:
                    driver.get(product_links[0].get_attribute("href"))
            except Exception:
                pass

        # Wait for page load
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        
        # Minimal scroll (reduce wait time)
        driver.execute_script("window.scrollTo(0, 600);")
        time.sleep(0.8)  # Reduced from 1.5s
        
        # Parse HTML
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Extract all data
        data = extract_product_data(soup, data, is_sku_search, target)

    except Exception as e:
        data['Product Name'] = "ERROR_FETCHING"
    finally:
        driver.quit()
    
    return data

# --- 4. PARALLEL PROCESSING ---
def scrape_items_parallel(targets, max_workers, headless=True):
    """Scrape multiple items in parallel using ThreadPoolExecutor."""
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_target = {
            executor.submit(scrape_item, target, headless): target 
            for target in targets
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_target):
            try:
                result = future.result()
                if result and result['Product Name'] not in ["SYSTEM_ERROR", "SKU_NOT_FOUND"]:
                    results.append(result)
            except Exception as e:
                st.warning(f"Task failed: {e}")
    
    return results

# --- MAIN APP ---
if 'scraped_results' not in st.session_state:
    st.session_state['scraped_results'] = []

col_txt, col_upl = st.columns(2)
with col_txt:
    text_in = st.text_area("Paste SKUs/Links:", height=150)
with col_upl:
    file_in = st.file_uploader("Upload Excel/CSV:", type=['xlsx', 'csv'])

if st.button("🚀 Start Extraction", type="primary"):
    targets = process_inputs(text_in, file_in, domain)
    
    if not targets:
        st.warning("No valid data found.")
    else:
        st.session_state['scraped_results'] = []
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text(f"Processing {len(targets)} items using {max_workers} parallel workers...")
        
        # Time the operation
        start_time = time.time()
        
        # Process in batches for better progress tracking
        batch_size = max_workers * 2
        all_results = []
        
        for i in range(0, len(targets), batch_size):
            batch = targets[i:i + batch_size]
            batch_results = scrape_items_parallel(batch, max_workers, not show_browser)
            all_results.extend(batch_results)
            
            # Update progress
            progress = min((i + len(batch)) / len(targets), 1.0)
            progress_bar.progress(progress)
            status_text.text(
                f"Processed {min(i + len(batch), len(targets))}/{len(targets)} items..."
            )
        
        elapsed = time.time() - start_time
        st.session_state['scraped_results'] = all_results
        
        status_text.success(
            f"✅ Done! Processed {len(targets)} items in {elapsed:.1f}s "
            f"({len(targets)/elapsed:.1f} items/sec)"
        )
        st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state['scraped_results']:
    st.markdown("---")
    
    # Prepare export data
    export_rows = []
    for item in st.session_state['scraped_results']:
        row = item.copy()
        row['Image URL'] = row['Image URLs'][0] if row['Image URLs'] else "N/A"
        del row['Image URLs']
        export_rows.append(row)
    
    df = pd.DataFrame(export_rows)
    
    # Reorder columns
    cols = ['Seller Name', 'SKU', 'Product Name', 'Brand', 'Category', 'Image URL', ' ', 'Express', 'Input Source']
    df = df[[c for c in cols if c in df.columns]]
    
    # Display stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Items", len(df))
    with col2:
        st.metric("Unique Brands", df['Brand'].nunique())
    with col3:
        st.metric("Express Items", (df['Express'] == 'Yes').sum())
    
    # Display table
    st.dataframe(df, use_container_width=True)
    
    # Download button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Download CSV",
        csv,
        "jumia_data.csv",
        "text/csv",
        key='download-csv'
    )
