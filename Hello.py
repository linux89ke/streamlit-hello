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
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="Jumia Product Scraper", page_icon="🛒", layout="wide")

st.title("🛒 Jumia Product Information Scraper")
st.markdown("Enter a Jumia product URL to extract product details.")

# --- SIDEBAR: SETUP INSTRUCTIONS ---
with st.sidebar:
    st.header("📦 Deployment Info")
    st.info("If deploying to Streamlit Cloud, ensure you have these files:")
    with st.expander("requirements.txt"):
        st.code("streamlit\nselenium\nbeautifulsoup4\npandas", language="text")
    with st.expander("packages.txt"):
        st.code("chromium\nchromium-driver", language="text")

# --- FUNCTIONS ---

def get_driver():
    """Initializes the Chrome Driver with dual-environment support."""
    chrome_options = Options()
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
    # 1. Try Streamlit Cloud Path
    try:
        service = Service(executable_path="/usr/bin/chromedriver")
        chrome_options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception:
        # 2. Fallback to Local/Automatic Path
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            st.error(f"Failed to initialize driver: {e}")
            return None
            
    # Stealth mode
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def scrape_jumia(url):
    """Scrapes data from the given Jumia URL."""
    driver = get_driver()
    if not driver:
        return None

    try:
        driver.get(url)
        # Wait for the H1 tag to ensure page load
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        
        # Scroll to trigger lazy loading
        driver.execute_script("window.scrollTo(0, 300);")
        time.sleep(2) 
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        all_text = soup.get_text()
        
        data = {}

        # 1. Product Name
        name_tag = soup.find('h1')
        data['Product Name'] = name_tag.text.strip() if name_tag else "N/A"
        
        # 2. Brand
        data['Brand'] = "N/A"
        try:
            brand_elem = driver.find_element(By.XPATH, "//div[contains(., 'Brand:')]/a")
            data['Brand'] = brand_elem.text.strip()
        except:
            # Fallback regex
            match = re.search(r'^([A-Z][a-z]{2,})\s+', data['Product Name'])
            if match: data['Brand'] = match.group(1).strip()

        # 3. Seller
        data['Seller Name'] = "N/A"
        try:
            seller_elem = driver.find_element(By.XPATH, "//div[contains(., 'Seller Score')]/ancestor::div[1]/preceding-sibling::div[1]/a[1]")
            data['Seller Name'] = seller_elem.text.strip()
        except:
             seller_link = soup.find('a', href=re.compile(r'/seller/'))
             if seller_link: data['Seller Name'] = seller_link.text.strip()

        # 4. SKU
        sku_match = re.search(r'SKU:\s*([A-Z0-9]+)', all_text, re.I)
        if sku_match:
            data['SKU'] = sku_match.group(1).strip()
        else:
            # Fallback to extracting from URL
            data['SKU'] = url.split('-')[-1].replace('.html', '')

        # 5. Model
        model_match = re.search(r'([A-Z]{3,}\d{3,}[A-Z0-9]*)', data['Product Name'])
        data['Model/Config'] = model_match.group(1) if model_match else "N/A"

        # 6. Category
        cats = []
        try:
            links = driver.find_elements(By.XPATH, "//ol//li//a")
            for link in links:
                txt = link.text.strip()
                if txt and txt.lower() not in ['home', 'jumia']:
                    cats.append(txt)
        except: pass
        data['Category'] = " > ".join(list(dict.fromkeys(cats)))

        # 7. Images
        imgs = []
        for img in soup.find_all('img', {'data-src': re.compile(r'jumia\.is/product/|jfs')}):
            src = img.get('data-src') or img.get('src')
            if src:
                if src.startswith('//'): src = 'https:' + src
                if src not in imgs: imgs.append(src)
        data['Image URLs'] = imgs
        
        return data

    except Exception as e:
        st.error(f"Scraping Error: {str(e)}")
        return None
    finally:
        driver.quit()

# --- MAIN APP LOGIC ---

url_input = st.text_input("Enter Jumia Product URL:", placeholder="https://www.jumia.co.ke/...")

# 'Fetch' button logic
if st.button("Fetch Product Data", type="primary"):
    if not url_input or "jumia.co.ke" not in url_input:
        st.error("Please enter a valid Jumia Kenya URL")
    else:
        with st.spinner("Initializing robust driver & fetching data..."):
            scraped_data = scrape_jumia(url_input)
            
            if scraped_data:
                # Save to Session State
                st.session_state['product_data'] = scraped_data
                st.session_state['url'] = url_input
                st.success("Data fetched!")

# --- DISPLAY LOGIC (Run if data exists in session state) ---
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
            st.info(f"Total Images Found: {len(data['Image URLs'])}")
        else:
            st.warning("No images found.")

    st.markdown("---")
    
    # CSV Preparation
    # Note: We must wrap scalars in lists for the DataFrame
    csv_dict = {'URL': [st.session_state['url']]}
    for k, v in data.items():
        if k != 'Image URLs':
            csv_dict[k] = [v]  # Wrap in list
    
    # Add Image columns
    for i, img_url in enumerate(data['Image URLs'][:10], 1):
        csv_dict[f'Image {i}'] = [img_url]

    df_csv = pd.DataFrame(csv_dict)
    csv = df_csv.to_csv(index=False).encode('utf-8')

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
