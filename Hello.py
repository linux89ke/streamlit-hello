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
st.set_page_config(page_title="Marketplace Data Tool", page_icon="📊", layout="wide")

st.title("🛒 E-Commerce Data Extractor")
st.markdown("Batch process **Product URLs** or **SKUs** from Excel/Text.")

# --- SIDEBAR: CONFIGURATION ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Generic Labels for Regions
    region_choice = st.selectbox(
        "Select Region:",
        ("Region 1 (KE)", "Region 2 (UG)")
    )
    # Map selection to actual domains internally
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    
    st.markdown("---")
    show_browser = st.checkbox("Show Browser (Debug Mode)", value=False)

# --- 1. DRIVER SETUP ---
@st.cache_resource
def install_driver():
    return ChromeDriverManager().install()

def get_driver():
    chrome_options = Options()
    if not show_browser:
        chrome_options.add_argument("--headless=new") 
    
    # Stability Arguments
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
            # Server/Cloud Fallback
            chrome_options.binary_location = "/usr/bin/chromium"
            service = Service("/usr/bin/chromedriver")
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception:
            return None

    if driver:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# --- 2. INPUT PROCESSING (URL vs SKU) ---
def process_inputs(text_input, file_input, default_domain):
    """
    Scans text and excel files. Distinguishes between direct Links and SKUs.
    """
    raw_items = set()
    
    # 1. Process Text Box
    if text_input:
        items = re.split(r'[\n, ]', text_input)
        for i in items:
            clean_item = i.strip()
            if clean_item: raw_items.add(clean_item)
            
    # 2. Process Excel/CSV Upload
    if file_input:
        try:
            if file_input.name.endswith('.xlsx'):
                df = pd.read_excel(file_input, header=None)
            else:
                df = pd.read_csv(file_input, header=None)
            
            # Flatten entire sheet to find data
            for cell in df.values.flatten():
                cell_str = str(cell).strip()
                if cell_str and cell_str.lower() != 'nan':
                    raw_items.add(cell_str)
        except Exception as e:
            st.error(f"Error reading file: {e}")

    final_targets = []
    
    for item in raw_items:
        # If it looks like a URL
        if item.startswith("http"):
            final_targets.append({"type": "url", "value": item})
        # If it looks like a SKU (alphanumeric, usually 8+ chars, no spaces)
        elif len(item) > 4 and " " not in item: 
            # Construct search URL internally
            search_url = f"https://www.{default_domain}/catalog/?q={item}"
            final_targets.append({"type": "sku", "value": search_url, "original_sku": item})
            
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
        
        # --- SKU SEARCH HANDLING ---
        if is_sku_search:
            try:
                # Wait for results container
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.-paxs, article.prd"))
                )
                
                # Check for "No results found" message
                page_source = driver.page_source
                if "There are no results for" in page_source:
                    data['Product Name'] = "SKU_NOT_FOUND"
                    driver.quit()
                    return data

                # Find first product link in search results
                # Common classes: .core inside .prd or .info inside .prd
                product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                
                if product_links:
                    first_link = product_links[0].get_attribute("href")
                    driver.get(first_link) # Go to product page
                else:
                    data['Product Name'] = "SKU_NOT_FOUND"
                    driver.quit()
                    return data
                    
            except Exception:
                # If timeout, maybe it redirected directly? Check if H1 exists
                pass

        # --- PRODUCT PAGE SCRAPING ---
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        
        # Scroll to trigger lazy loading
        driver.execute_script("window.scrollTo(0, 600);")
        time.sleep(1.5)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # 1. Product Name
        h1 = soup.find('h1')
        data['Product Name'] = h1.text.strip() if h1 else "N/A"

        # 2. Brand
        # Look for "Brand: X" pattern
        brand_label = soup.find(string=re.compile(r"Brand:\s*"))
        if brand_label and brand_label.parent:
            # Check for link
            brand_link = brand_label.parent.find('a')
            if brand_link:
                data['Brand'] = brand_link.text.strip()
            else:
                # Text fallback
                txt = brand_label.parent.get_text().replace('Brand:', '').strip()
                data['Brand'] = txt.split('|')[0].strip() # Clean garbage text
        
        if data['Brand'] in ["N/A", ""] or "generic" in data['Brand'].lower():
             # Fallback: First word of product name
             data['Brand'] = data['Product Name'].split()[0]

        # 3. Seller
        # Look for the seller box (generic classes often used)
        seller_box = soup.select_one('div.-hr.-pas, div.seller-details')
        if seller_box:
            p_tag = seller_box.find('p', class_='-m')
            if p_tag: data['Seller Name'] = p_tag.text.strip()
        
        # Filter unwanted seller names
        if any(x in data['Seller Name'].lower() for x in ['details', 'follow', 'sell on', 'n/a']):
             data['Seller Name'] = "N/A"

        # 4. Category
        breadcrumbs = soup.select('.osh-breadcrumb a, .brcbs a')
        cats = [b.text.strip() for b in breadcrumbs if b.text.strip()]
        # Usually index 0 is Home, 1 is Main Cat
        data['Category'] = cats[1] if len(cats) > 1 else (cats[0] if cats else "N/A")

        # 5. SKU (Actual Product SKU)
        sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
        if sku_match: data['SKU'] = sku_match.group(1)
        elif is_sku_search: data['SKU'] = target['original_sku'] # Fallback to input

        # 6. Images
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src')
            # Filter logic for product images
            if src and '/product/' in src:
                if src.startswith('//'): src = 'https:' + src
                if src not in data['Image URLs']: data['Image URLs'].append(src)

        # 7. Express Detection (Internal Logic)
        # We look for the specific marker, but the user sees generic output
        express_svg = soup.find('svg', attrs={'aria-label': 'Jumia Express'})
        if express_svg:
            data['Express'] = "Yes"

    except Exception as e:
        data['Product Name'] = "ERROR_FETCHING"
    finally:
        driver.quit()
        
    return data

# --- MAIN APP LOGIC ---

if 'scraped_results' not in st.session_state:
    st.session_state['scraped_results'] = []

col_txt, col_upl = st.columns(2)
with col_txt:
    text_in = st.text_area("Paste SKUs or Links (one per line):", height=150)
with col_upl:
    file_in = st.file_uploader("Upload Excel/CSV:", type=['xlsx', 'csv'])
    st.caption("Supported formats: .xlsx, .csv")

btn_col, _ = st.columns([1, 4])
if btn_col.button("🚀 Start Extraction", type="primary"):
    
    # Process inputs based on selected domain
    targets = process_inputs(text_in, file_in, domain)
    
    if not targets:
        st.warning("No valid data found. Please check your inputs.")
    else:
        st.info(f"Queued {len(targets)} items for processing...")
        st.session_state['scraped_results'] = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, target in enumerate(targets):
            display_name = target.get('original_sku', 'Link')
            status_text.text(f"Processing {i+1}/{len(targets)}: {display_name}")
            
            result = scrape_item(target)
            
            if result and result['Product Name'] not in ["SYSTEM_ERROR", "SKU_NOT_FOUND"]:
                st.session_state['scraped_results'].append(result)
            
            progress_bar.progress((i + 1) / len(targets))
            
        status_text.success("Batch processing complete!")
        time.sleep(1)
        st.rerun()

# --- RESULT TABLE ---
if st.session_state['scraped_results']:
    st.markdown("---")
    st.subheader("📊 Extracted Data")

    # Clean up for display
    export_rows = []
    for item in st.session_state['scraped_results']:
        row = item.copy()
        row['Image URL'] = row['Image URLs'][0] if row['Image URLs'] else "N/A"
        del row['Image URLs']
        export_rows.append(row)
    
    df = pd.DataFrame(export_rows)
    
    # Final Column Ordering
    desired_order = ['Seller Name', 'SKU', 'Product Name', 'Brand', 'Category', 'Image URL', ' ', 'Express', 'Input Source']
    final_cols = [c for c in desired_order if c in df.columns]
    df = df[final_cols]

    st.dataframe(df, use_container_width=True)

    # Download Button
    csv_data = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Results (CSV)",
        data=csv_data,
        file_name="marketplace_data.csv",
        mime="text/csv",
        type="primary"
    )

    if st.button("Clear Data"):
        st.session_state['scraped_results'] = []
        st.rerun()
