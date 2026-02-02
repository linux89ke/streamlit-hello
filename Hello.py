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
st.set_page_config(page_title="Marketplace Data Tool", page_icon="📊", layout="wide")
st.title("🛒 E-Commerce Data Extractor (V10.1 - Stable)")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    region_choice = st.selectbox("Select Region:", ("Region 1 (KE)", "Region 2 (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    st.markdown("---")
    show_browser = st.checkbox("Show Browser (Debug Mode)", value=False)
    max_workers = st.slider("Parallel Workers:", 1, 3, 2, help="More workers = faster but may cause timeouts")
    timeout_seconds = st.slider("Page Timeout (seconds):", 10, 30, 20)
    st.info(f"⚡ Using {max_workers} workers with {timeout_seconds}s timeout")

# --- 1. DRIVER SETUP WITH BETTER ERROR HANDLING ---
@st.cache_resource
def get_driver_path():
    """Cache driver installation."""
    try:
        return ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    except Exception:
        try:
            return ChromeDriverManager().install()
        except Exception as e:
            st.error(f"Could not install driver: {e}")
            return None

def get_chrome_options(headless=True):
    """Configure Chrome options for stability."""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    
    # Essential stability arguments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-notifications")
    
    # Reduce resource usage
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    
    # Disable images for faster loading
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Detect browser binary
    possible_paths = [
        "/usr/bin/chromium", 
        "/usr/bin/chromium-browser", 
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            break
    
    return chrome_options

def get_driver(headless=True, timeout=20):
    """Create WebDriver with comprehensive error handling."""
    chrome_options = get_chrome_options(headless)
    driver = None
    
    try:
        driver_path = get_driver_path()
        if not driver_path:
            return None
            
        service = Service(driver_path)
        service.log_path = os.devnull  # Suppress logs
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
    except Exception as e:
        try:
            # Fallback without explicit service
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e2:
            return None

    if driver:
        try:
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.set_page_load_timeout(timeout)
            driver.implicitly_wait(5)
        except Exception:
            pass
    
    return driver

# --- 2. INPUT PROCESSING ---
def process_inputs(text_input, file_input, default_domain):
    """Process inputs efficiently."""
    raw_items = set()
    
    if text_input:
        items = re.split(r'[\n,]', text_input)
        raw_items.update(i.strip() for i in items if i.strip())
    
    if file_input:
        try:
            df = pd.read_excel(file_input, header=None) if file_input.name.endswith('.xlsx') \
                 else pd.read_csv(file_input, header=None)
            
            raw_items.update(
                str(cell).strip() 
                for cell in df.values.flatten() 
                if str(cell).strip() and str(cell).lower() != 'nan'
            )
        except Exception as e:
            st.error(f"Error reading file: {e}")

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

# --- 3. SCRAPING WITH RETRY LOGIC ---
def extract_product_data(soup, data, is_sku_search, target):
    """Extract product data from HTML."""
    
    # Product Name
    h1 = soup.find('h1')
    data['Product Name'] = h1.text.strip() if h1 else "N/A"

    # Brand
    brand_label = soup.find(string=re.compile(r"Brand:\s*"))
    if brand_label and brand_label.parent:
        brand_link = brand_label.parent.find('a')
        data['Brand'] = brand_link.text.strip() if brand_link else \
                       brand_label.parent.get_text().replace('Brand:', '').split('|')[0].strip()
    
    if data['Brand'] in ["N/A", ""] or "generic" in data['Brand'].lower():
        data['Brand'] = data['Product Name'].split()[0] if data['Product Name'] != "N/A" else "N/A"

    # Seller
    seller_box = soup.select_one('div.-hr.-pas, div.seller-details')
    if seller_box:
        p_tag = seller_box.find('p', class_='-m')
        if p_tag:
            seller_text = p_tag.text.strip()
            if not any(x in seller_text.lower() for x in ['details', 'follow', 'sell on']):
                data['Seller Name'] = seller_text

    # Category
    breadcrumbs = soup.select('.osh-breadcrumb a, .brcbs a')
    cats = [b.text.strip() for b in breadcrumbs if b.text.strip()]
    data['Category'] = cats[1] if len(cats) > 1 else (cats[0] if cats else "N/A")

    # SKU
    sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
    if sku_match:
        data['SKU'] = sku_match.group(1)
    elif is_sku_search:
        data['SKU'] = target.get('original_sku', 'N/A')

    # Images
    for img in soup.find_all('img', limit=5):
        src = img.get('data-src') or img.get('src')
        if src and '/product/' in src:
            if src.startswith('//'):
                src = 'https:' + src
            if src not in data['Image URLs']:
                data['Image URLs'].append(src)
                break

    # Express
    if soup.find('svg', attrs={'aria-label': 'Jumia Express'}):
        data['Express'] = "Yes"
    
    return data

def scrape_item_with_retry(target, headless=True, timeout=20, max_retries=2):
    """Scrape with retry logic for failed attempts."""
    for attempt in range(max_retries):
        result = scrape_item(target, headless, timeout)
        
        # If successful or SKU not found, return immediately
        if result['Product Name'] not in ['ERROR_FETCHING', 'TIMEOUT', 'SYSTEM_ERROR']:
            return result
        
        # Wait before retry
        if attempt < max_retries - 1:
            time.sleep(2)
    
    return result

def scrape_item(target, headless=True, timeout=20):
    """Scrape a single item with comprehensive error handling."""
    driver = None
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
        driver = get_driver(headless, timeout)
        if not driver:
            data['Product Name'] = 'SYSTEM_ERROR'
            return data

        # Navigate to URL
        try:
            driver.get(url)
        except TimeoutException:
            data['Product Name'] = 'TIMEOUT'
            return data
        except WebDriverException as e:
            data['Product Name'] = 'CONNECTION_ERROR'
            return data
        
        # Handle SKU search
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
                    try:
                        driver.get(product_links[0].get_attribute("href"))
                    except TimeoutException:
                        data['Product Name'] = 'TIMEOUT'
                        return data
            except TimeoutException:
                data['Product Name'] = 'TIMEOUT'
                return data
            except Exception:
                pass

        # Wait for page content
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "h1"))
            )
        except TimeoutException:
            data['Product Name'] = 'TIMEOUT'
            return data
        
        # Quick scroll and wait
        try:
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(0.5)
        except Exception:
            pass
        
        # Parse HTML
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = extract_product_data(soup, data, is_sku_search, target)

    except TimeoutException:
        data['Product Name'] = "TIMEOUT"
    except WebDriverException:
        data['Product Name'] = "CONNECTION_ERROR"
    except Exception as e:
        data['Product Name'] = "ERROR_FETCHING"
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    
    return data

# --- 4. PARALLEL PROCESSING ---
def scrape_items_parallel(targets, max_workers, headless=True, timeout=20):
    """Scrape multiple items in parallel."""
    results = []
    failed = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_target = {
            executor.submit(scrape_item_with_retry, target, headless, timeout): target 
            for target in targets
        }
        
        for future in as_completed(future_to_target):
            target = future_to_target[future]
            try:
                result = future.result()
                if result['Product Name'] in ["SYSTEM_ERROR", "TIMEOUT", "CONNECTION_ERROR"]:
                    failed.append({
                        'input': target.get('original_sku', target['value']),
                        'error': result['Product Name']
                    })
                elif result['Product Name'] != "SKU_NOT_FOUND":
                    results.append(result)
            except Exception as e:
                failed.append({
                    'input': target.get('original_sku', target['value']),
                    'error': str(e)
                })
    
    return results, failed

# --- MAIN APP ---
if 'scraped_results' not in st.session_state:
    st.session_state['scraped_results'] = []
if 'failed_items' not in st.session_state:
    st.session_state['failed_items'] = []

col_txt, col_upl = st.columns(2)
with col_txt:
    text_in = st.text_area("Paste SKUs/Links:", height=150, 
                           placeholder="Enter SKUs or URLs, one per line")
with col_upl:
    file_in = st.file_uploader("Upload Excel/CSV:", type=['xlsx', 'csv'])

if st.button("🚀 Start Extraction", type="primary"):
    targets = process_inputs(text_in, file_in, domain)
    
    if not targets:
        st.warning("⚠️ No valid data found. Please enter SKUs or URLs.")
    else:
        st.session_state['scraped_results'] = []
        st.session_state['failed_items'] = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text(f"🔄 Processing {len(targets)} items with {max_workers} workers...")
        start_time = time.time()
        
        # Process in batches
        batch_size = max_workers * 2
        all_results = []
        all_failed = []
        
        for i in range(0, len(targets), batch_size):
            batch = targets[i:i + batch_size]
            batch_results, batch_failed = scrape_items_parallel(
                batch, max_workers, not show_browser, timeout_seconds
            )
            
            all_results.extend(batch_results)
            all_failed.extend(batch_failed)
            
            progress = min((i + len(batch)) / len(targets), 1.0)
            progress_bar.progress(progress)
            status_text.text(
                f"🔄 Processed {min(i + len(batch), len(targets))}/{len(targets)} items..."
            )
        
        elapsed = time.time() - start_time
        st.session_state['scraped_results'] = all_results
        st.session_state['failed_items'] = all_failed
        
        success_count = len(all_results)
        failed_count = len(all_failed)
        
        if failed_count > 0:
            status_text.warning(
                f"⚠️ Completed with issues: {success_count} successful, {failed_count} failed "
                f"({elapsed:.1f}s)"
            )
        else:
            status_text.success(
                f"✅ Done! Processed {len(targets)} items in {elapsed:.1f}s "
                f"({len(targets)/elapsed:.1f} items/sec)"
            )
        
        time.sleep(1)
        st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state['scraped_results'] or st.session_state['failed_items']:
    st.markdown("---")
    
    # Show failed items if any
    if st.session_state['failed_items']:
        with st.expander(f"⚠️ Failed Items ({len(st.session_state['failed_items'])})", expanded=False):
            failed_df = pd.DataFrame(st.session_state['failed_items'])
            st.dataframe(failed_df, use_container_width=True)
            st.info("💡 Tip: Try reducing parallel workers or increasing timeout for better reliability.")
    
    # Show successful results
    if st.session_state['scraped_results']:
        export_rows = []
        for item in st.session_state['scraped_results']:
            row = item.copy()
            row['Image URL'] = row['Image URLs'][0] if row['Image URLs'] else "N/A"
            del row['Image URLs']
            export_rows.append(row)
        
        df = pd.DataFrame(export_rows)
        cols = ['Seller Name', 'SKU', 'Product Name', 'Brand', 'Category', 'Image URL', ' ', 'Express', 'Input Source']
        df = df[[c for c in cols if c in df.columns]]
        
        # Stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("✅ Successful", len(df))
        with col2:
            st.metric("🏷️ Unique Brands", df['Brand'].nunique())
        with col3:
            st.metric("⚡ Express Items", (df['Express'] == 'Yes').sum())
        with col4:
            st.metric("❌ Failed", len(st.session_state['failed_items']))
        
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download Results (CSV)",
            csv,
            f"jumia_data_{int(time.time())}.csv",
            "text/csv",
            key='download-csv'
        )

