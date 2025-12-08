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

st.title("🛒 Jumia Product Information Scraper (V6.2 - FINAL)")
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
    try:
        service = Service(executable_path="/usr/bin/chromedriver")
        chrome_options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception:
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            st.error(f"Failed to initialize driver: {e}")
            return None
            
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# --- 2. SCRAPING FUNCTION (V6.2 FINAL) ---
def scrape_jumia(url):
    """Scrapes data with maximum robustness, excluding Model/Config."""
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


        # 3. Seller Name (V6.2 DEFINITIVE FIX)
        data['Seller Name'] = "N/A"
        
        try:
            # Target the container with the seller stats
            seller_stats_container = soup.find('div', class_='-hr -pas')
            if seller_stats_container:
                # Find the seller name in the specific <p> tag ('-m -pbs')
                seller_name_tag = seller_stats_container.find('p', class_='-m -pbs')
                if seller_name_tag:
                    data['Seller Name'] = seller_name_tag.text.strip()
            
        except Exception:
            pass
        
        # Fallback/Cleanup: If the specific tags are missing or text is generic
        if data['Seller Name'].lower() in ['details', 'follow', 'sell on jumia', 'n/a']:
             data['Seller Name'] = "N/A"


        # 4. Category (V6.1 FIX: Definitive Fix using 'brcbs' class)
        cats = []
        try:
            category_container = soup.find('div', class_='brcbs')
            if category_container:
                category_links = category_container.find_all('a')
            else:
                # Fallback to general search (usually not hit now)
                category_links = driver.find_elements(By.XPATH, "//ol//li//a | //nav//li//a | //div[contains(@class, 'brcbs')]//a")
            
            for link in category_links:
                txt = link.text.strip()
                if txt and txt.lower() not in ['home', 'jumia', ''] and txt != data['Product Name']:
                    cats.append(txt)
        except Exception:
            pass
            
        data['Category'] = " > ".join(list(dict.fromkeys(cats))) if cats else "N/A"

        # 5. SKU 
        data['SKU'] = "N/A"
        
        # Look in spec list items
        specs_list = soup.find_all('li', class_='-pvxs') 
        for item in specs_list:
            text = item.get_text(strip=True)
            if 'SKU' in text:
                data['SKU'] = text.replace('SKU', '').replace(':', '').strip()
        
        # Fallback for SKU (from URL)
        if data['SKU'] == "N/A":
             match = re.search(r'-([A-Z0-9]+)\.html', url)
             if match:
                 data['SKU'] = match.group(1)

        # 6. Images 
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
