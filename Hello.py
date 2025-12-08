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

st.title("🛒 Jumia Product Information Scraper (V5.0 - Final)")
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
    # Essential options for headless execution/Cloud deployment
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

# --- 2. SCRAPING FUNCTION (V5.0 FINAL) ---
def scrape_jumia(url):
    """Scrapes data with maximum robustness for Seller and Category (v5.0)."""
    driver = get_driver()
    if not driver:
        return None

    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2) 
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = {}

        # 1. Product Name
        name_tag = soup.find('h1')
        data['Product Name'] = name_tag.text.strip() if name_tag else "N/A"
        
        # 2. Brand 
        data['Brand'] = "N/A"
        brand_label = soup.find(string=re.compile(r"Brand:\s*"))
        if brand_label:
            brand_parent = brand_label.find_parent('div')
            if brand_parent:
                brand_link = brand_parent.find('a')
                if brand_link:
                    data['Brand'] = brand_link.text.strip()
                else:
                    data['Brand'] = brand_parent.get_text().replace('Brand:', '').strip().split()[0]
        
        if data['Brand'] == "N/A" or data['Brand'].lower() == 'jumia':
             data['Brand'] = data['Product Name'].split()[0]


        # 3. Seller Name (V5.0 FIX: Multiple Fallbacks)
        data['Seller Name'] = "N/A"
        
        # Strategy A: Find the link near "Seller Information" (Primary)
        seller_header = soup.find(string=re.compile(r"Seller Information|Seller details|Sold by"))
        if seller_header:
            container = seller_header.find_parent('div').find_parent('div')
            if container:
                all_links = container.find_all('a', href=True)
                for link in all_links:
                    text = link.text.strip()
                    # Filter out common button/label text
                    if text and text not in ['Details', 'Follow', 'Visit Store', 'Official Store'] and ('/seller/' in link.get('href') or '/sp-' in link.get('href')):
                        data['Seller Name'] = text
                        break
        
        # Strategy B: Find any link with /seller/ in the entire page (Fallback)
        if data['Seller Name'] == "N/A":
             seller_tag = soup.find('a', href=re.compile(r'/seller/|/sp-'))
             if seller_tag:
                 seller_text = seller_tag.text.strip()
                 if seller_text not in ['Details', 'Follow', 'Visit Store']:
                    data['Seller Name'] = seller_text
                 else:
                    # If it's a button, try to find the actual seller name near the button
                    seller_name_near = seller_tag.find_previous_sibling()
                    if seller_name_near and seller_name_near.name in ['span', 'div']:
                        data['Seller Name'] = seller_name_near.text.strip()


        # 4. Category (V5.0 FIX: Broadest XPath targeting structure)
        cats = []
        try:
            # Broadest XPath targeting common list/nav structures near the top
            category_xpath = "//ol//li//a | //nav//li//a | //div[contains(@class, 'br-c')]//a"
            category_links = driver.find_elements(By.XPATH, category_xpath)
            
            for link in category_links:
                txt = link.text.strip()
                # Ensure the link is not the product name itself, Home, or Jumia
                if txt and txt.lower() not in ['home', 'jumia'] and txt != data['Product Name']:
                    cats.append(txt)
        except Exception:
            pass
            
        data['Category'] = " > ".join(list(dict.fromkeys(cats))) if cats else "N/A"

        # 5. SKU & Model (Specifications Section Strategy - Reliable)
        data['SKU'] = "N/A"
        data['Model/Config'] = "N/A"
        
        # Look in spec list items
        specs_list = soup.find_all('li', class_='-pvxs') 
        for item in specs_list:
            text = item.get_text(strip=True)
            if 'SKU' in text:
                data['SKU'] = text.replace('SKU', '').replace(':', '').strip()
            elif 'Model' in text:
                 data['Model/Config'] = text.replace('Model', '').replace(':', '').strip()
        
        # Fallback for SKU (from URL)
        if data['SKU'] == "N/A":
             match = re.search(r'-([A-Z0-9]+)\.html', url)
             if match:
                 data['SKU'] = match.group(1)

        # 6. Images (Confirmed Working)
        imgs = []
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src')
            if src and 'jumia.is' in src and ('/product/' in src or '/unsafe/' in src):
                if src.startswith('//'): src = 'https:' + src
                if src not in imgs: imgs.append(src)
        data['Image URLs'] = imgs
        
        return data

    except Exception as e:
        st.error(f"Scraping Error: {str(e)}")
        return None
    finally:
        # Ensures the browser closes cleanly
        if driver:
            try:
                driver.quit()
            except:
                pass

# --- 3. MAIN UI LOGIC (Uses Session State) ---

# Initialize session state if not already done
if 'product_data' not in st.session_state:
    st.session_state['product_data'] = None

url_input = st.text_input("Enter Jumia Product URL:", placeholder="https://www.jumia.co.ke/...")

# 'Fetch' button logic
if st.button("Fetch Product Data", type="primary"):
    if not url_input or "jumia.co.ke" not in url_input:
        st.error("Please enter a valid Jumia Kenya URL")
    else:
        st.session_state['product_data'] = None
            
        with st.spinner("Initializing robust driver & fetching data..."):
            scraped_data = scrape_jumia(url_input)
            
            if scraped_data:
                # Store data in session state for persistence
                st.session_state['product_data'] = scraped_data
                st.session_state['url'] = url_input
                st.success("Data fetched!")

# --- 4. DISPLAY LOGIC (Run if data exists in session state) ---
if st.session_state.product_data:
    data = st.session_state.product_data
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📋 Product Details")
        display_dict = {k: v for k, v in data.items() if k != 'Image URLs'}
        df_display = pd.DataFrame([{'Attribute': k, 'Value': v} for k, v in display_dict.items()])
        st.table(df_display.set_index('Attribute'))

    with col2:
        st.subheader("🖼️ Product Images")
        if data['Image URLs']:
            st.image(data['Image URLs'][0], caption="Main Image Preview", use_column_width=True)
            with st.expander(f"View all {len(data['Image URLs'])} image links"):
                for link in data['Image URLs']:
                    st.write(link)
        else:
            st.warning("No images found.")

    st.markdown("---")
    
    # CSV Preparation
    csv_dict = {'URL': [st.session_state.url]}
    for k, v in data.items():
        if k != 'Image URLs':
            csv_dict[k] = [v]
    
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

    if st.button("Clear Results"):
        del st.session_state['product_data']
        st.rerun()
