import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Jumia Product Scraper", page_icon="🛒", layout="wide")

st.title("🛒 Jumia Product Information Scraper (Robust)")
st.markdown("Enter a Jumia product URL below to extract details, images, and prices.")

# --- SIDEBAR: SETUP INSTRUCTIONS ---
with st.sidebar:
    st.header("📦 Deployment Info")
    st.info("If deploying to Streamlit Cloud, ensure you have these files:")
    with st.expander("requirements.txt"):
        st.code("""streamlit
selenium
beautifulsoup4
pandas""", language="text")
    with st.expander("packages.txt"):
        st.code("""chromium
chromium-driver""", language="text")

# --- 1. DRIVER SETUP FUNCTION ---
def get_driver():
    """Initializes the Chrome Driver with dual-environment support (Cloud & Local)."""
    chrome_options = Options()
    # Headless mode is critical for cloud environments
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    # 1. Try Streamlit Cloud Path (Linux default)
    try:
        service = Service(executable_path="/usr/bin/chromedriver")
        chrome_options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception:
        # 2. Fallback to Local/Automatic Path (Windows/Mac)
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            st.error(f"Failed to initialize driver: {e}")
            return None
            
    # Stealth mode to avoid detection
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# --- 2. SCRAPING FUNCTION ---
def scrape_jumia(url):
    """Scrapes data from the given Jumia URL."""
    driver = get_driver()
    if not driver:
        return None

    try:
        driver.get(url)
        # Wait for the H1 tag to ensure page load
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        
        # Scroll down to trigger lazy loading of images
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2) 
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Get text with separators to avoid merging words
        all_text = soup.get_text(separator=' ', strip=True) 
        
        data = {}

        # 1. Product Name
        name_tag = soup.find('h1')
        data['Product Name'] = name_tag.text.strip() if name_tag else "N/A"
        
        # 2. Brand (Robust Fallback)
        data['Brand'] = "N/A"
        # Strategy A: Look for explicit brand link inside common containers
        brand_node = soup.find('div', class_='-pvxs')
        if brand_node:
            brand_link = brand_node.find('a')
            if brand_link:
                data['Brand'] = brand_link.text.strip()
        
        # Strategy B: Regex from Title if A fails
        if data['Brand'] == "N/A":
            match = re.search(r'^([A-Z][a-z0-9]{2,})\s+', data['Product Name'])
            if match: data['Brand'] = match.group(1).strip()

        # 3. Seller Name (Updated for 2024/2025 layout)
        data['Seller Name'] = "N/A"
        try:
            # Look for the block containing 'Seller Information' or 'Score'
            seller_block = driver.find_element(By.XPATH, "//div[contains(text(), 'Seller Information') or contains(., 'Seller Score')]")
            # Find the first link inside this block or immediately preceding it
            seller_link = seller_block.find_element(By.XPATH, "./preceding::a[contains(@href, '/seller/')][1]")
            data['Seller Name'] = seller_link.text.strip()
        except:
            # Fallback: Just find any link with '/seller/' in href
            seller_tag = soup.find('a', href=re.compile(r'/seller/'))
            if seller_tag:
                data['Seller Name'] = seller_tag.text.strip()

        # 4. SKU (Fixed: Removed re.I to stop capturing 'Weight')
        sku_match = re.search(r'SKU[:\s]*([A-Z0-9]+)', all_text) 
        if sku_match:
            data['SKU'] = sku_match.group(1).strip()
        else:
            # Fallback to extracting from URL
            data['SKU'] = url.split('-')[-1].replace('.html', '')

        # 5. Model/Config
        model_match = re.search(r'\b([A-Z]{2,}\d{3,}[A-Z0-9]*)\b', data['Product Name'])
        data['Model/Config'] = model_match.group(1) if model_match else "N/A"

        # 6. Category
        cats = []
        try:
            # Jumia breadcrumbs often use <nav> or specific classes
            breadcrumb_links = soup.select('nav[aria-label="Breadcrumb"] a')
            if not breadcrumb_links:
                breadcrumb_links = soup.select('.br-c a') # Alternate class
            
            for link in breadcrumb_links:
                txt = link.text.strip()
                if txt and txt.lower() not in ['home', 'jumia']:
                    cats.append(txt)
        except: pass
        data['Category'] = " > ".join(list(dict.fromkeys(cats)))

        # 7. Images (Broadened Search)
        imgs = []
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src')
            if src:
                if src.startswith('//'): src = 'https:' + src
                # Filter for jumia product images (exclude tiny icons/trackers)
                if 'jumia.is' in src and ('/product/' in src or '/unsafe/' in src):
                    if src not in imgs:
                        imgs.append(src)
        data['Image URLs'] = imgs
        
        return data

    except Exception as e:
        st.error(f"Scraping Error: {str(e)}")
        return None
    finally:
        driver.quit()

# --- 3. MAIN UI LOGIC ---

url_input = st.text_input("Enter Jumia Product URL:", placeholder="https://www.jumia.co.ke/...")

# 'Fetch' button logic
if st.button("Fetch Product Data", type="primary"):
    if not url_input or "jumia.co.ke" not in url_input:
        st.error("Please enter a valid Jumia Kenya URL")
    else:
        # Clear previous state if new search
        if 'product_data' in st.session_state:
            del st.session_state['product_data']
            
        with st.spinner("Initializing robust driver & fetching data..."):
            scraped_data = scrape_jumia(url_input)
            
            if scraped_data:
                # SAVE TO SESSION STATE
                st.session_state['product_data'] = scraped_data
                st.session_state['url'] = url_input
                st.success("Data fetched!")

# --- 4. DISPLAY LOGIC (Run if data exists in session state) ---
if 'product_data' in st.session_state:
    data = st.session_state['product_data']
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📋 Product Details")
        # Prepare table data
        display_dict = {k: v for k, v in data.items() if k != 'Image URLs'}
        df_display = pd.DataFrame([{'Attribute': k, 'Value': v} for k, v in display_dict.items()])
        st.table(df_display.set_index('Attribute'))

    with col2:
        st.subheader("🖼️ Preview")
        if data['Image URLs']:
            st.image(data['Image URLs'][0], caption="Main Image", use_column_width=True)
            with st.expander("View all found image links"):
                for link in data['Image URLs']:
                    st.write(link)
        else:
            st.warning("No images found.")

    st.markdown("---")
    
    # CSV Preparation
    # Note: We must wrap scalars in lists for the DataFrame
    csv_dict = {'URL': [st.session_state['url']]}
    for k, v in data.items():
        if k != 'Image URLs':
            csv_dict[k] = [v]
    
    # Add Image columns (up to 10)
    for i, img_url in enumerate(data['Image URLs'][:10], 1):
        csv_dict[f'Image {i}'] = [img_url]

    df_csv = pd.DataFrame(csv_dict)
    csv = df_csv.to_csv(index=False).encode('utf-8')

    # This button will NOT cause the data to disappear because we use Session State
    st.download_button(
        label="📥 Download Data as CSV",
        data=csv,
        file_name=f"jumia_{data['SKU']}.csv",
        mime="text/csv"
    )

    # Optional: Clear results button
    if st.button("Clear Results"):
        del st.session_state['product_data']
        st.rerun()
