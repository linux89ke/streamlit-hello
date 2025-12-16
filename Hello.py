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
st.set_page_config(page_title="Jumia Catalog Selector", page_icon="🛒", layout="wide")
st.title("🛒 Jumia Catalog Selector (V9.0)")
st.markdown("Step 1: Paste a category URL to load products. Step 2: Select items. Step 3: Process.")

# --- Custom CSS for Card Styling ---
st.markdown("""
<style>
    [data-testid="stImage"] {
        border-radius: 8px;
        overflow: hidden;
    }
    .sku-label {
        background-color: #333;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
        font-weight: bold;
        display: inline-block;
        margin-bottom: 5px;
    }
    .product-name {
        font-size: 0.9em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
    }
    /* Tighten up vertical spacing in grid */
    div[data-testid="column"] > div > div > div {
        gap: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# --- 1. DRIVER SETUP ---
@st.cache_resource
def install_driver():
    return ChromeDriverManager().install()

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        service = Service(install_driver())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        st.error(f"Driver Error: {e}")
        return None

# --- 2. CATALOG PAGE SCRAPER ---
def scrape_catalog_page(url):
    """Scrapes basic info from a grid of products on a category page."""
    driver = get_driver()
    if not driver: return []
    
    products_found = []
    try:
        driver.get(url)
        # Wait for product articles to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd"))
        )
        # Scroll down a bit to trigger lazy loading images
        driver.execute_script("window.scrollTo(0, 1000);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 2000);")
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Find all product cards
        cards = soup.find_all('article', class_='prd')
        
        for card in cards:
            try:
                # A. Get Link and extract generic SKU from it
                link_tag = card.find('a', class_='core')
                if not link_tag: continue
                product_url = link_tag.get('href')
                if product_url.startswith('/'): product_url = "https://www.jumia.co.ke" + product_url

                # Extract SKU from URL (e.g., ...-AC12345.html -> AC12345)
                sku_match = re.search(r'-([A-Z0-9]+)\.html', product_url)
                sku = sku_match.group(1) if sku_match else "N/A"

                # B. Get Image
                img_tag = card.find('img')
                img_url = img_tag.get('data-src') or img_tag.get('src')
                
                # C. Get Name
                name_tag = card.find('h3', class_='name')
                name = name_tag.text.strip() if name_tag else "Unknown Product"
                
                if img_url and sku != "N/A":
                    products_found.append({
                        'sku': sku,
                        'name': name,
                        'image': img_url,
                        'url': product_url
                    })
            except Exception:
                continue
                
    except Exception as e:
        st.error(f"Error loading catalog: {e}")
    finally:
        driver.quit()
    
    return products_found

# --- MAIN APP LOGIC ---

# Initialize Session State
if 'catalog_items' not in st.session_state:
    st.session_state['catalog_items'] = []
if 'selected_urls' not in st.session_state:
    st.session_state['selected_urls'] = []

# STEP 1: INPUT URL
st.header("1. Fetch Product List")
catalog_url = st.text_input("Paste Category or Search Result URL:", placeholder="https://www.jumia.co.ke/televisions/")

if st.button("Fetch Products", type="primary"):
    if "jumia" not in catalog_url:
        st.error("Please enter a valid Jumia URL.")
    else:
        with st.spinner("Fetching products from page..."):
            # Clear previous states
            st.session_state['catalog_items'] = []
            st.session_state['selected_urls'] = []
            # Scrape
            items = scrape_catalog_page(catalog_url)
            if items:
                st.session_state['catalog_items'] = items
                st.success(f"Found {len(items)} products!")
            else:
                st.warning("No products found on this page.")

# STEP 2: DISPLAY Grid & Selections
if st.session_state['catalog_items']:
    st.markdown("---")
    st.header("2. Select Products")
    st.caption("Tick the checkboxes of the products you want to investigate further.")
    
    items = st.session_state['catalog_items']
    
    # Grid Layout Parameters
    COLS_PER_ROW = 5
    
    # Create chunks for grid rows
    for i in range(0, len(items), COLS_PER_ROW):
        row_items = items[i:i+COLS_PER_ROW]
        cols = st.columns(COLS_PER_ROW)
        
        for j, col in enumerate(cols):
            if j < len(row_items):
                item = row_items[j]
                with col:
                    # 1. Display Image
                    st.image(item['image'], use_container_width=True)
                    
                    # 2. Display SKU (styled like a label using HTML)
                    st.markdown(f'<div class="sku-label">{item["sku"]}</div>', unsafe_allow_html=True)
                    
                    # 3. Selection Checkbox with Name truncated
                    # We use the SKU as the unique key for the checkbox state
                    is_checked = st.checkbox(
                        label=item['name'], # Display full name next to checkbox
                        key=f"select_{item['sku']}" # Unique ID for Streamlit state
                    )


# STEP 3: PROCESS SELECTION
st.markdown("---")
st.header("3. Process Selected")

# A hidden container that only shows when items are selected
results_container = st.container()

if st.button("Generate List of Selected URLs", type="primary"):
    selected_links = []
    
    # Iterate through scraped items and check their corresponding checkbox state
    for item in st.session_state['catalog_items']:
        checkbox_key = f"select_{item['sku']}"
        # Check if the checkbox with this key exists in session state and is True
        if st.session_state.get(checkbox_key, False):
            selected_links.append({
                'SKU': item['sku'],
                'Product Name': item['name'],
                'Product URL': item['url']
            })
            
    st.session_state['selected_urls'] = selected_links

# Display results if they exist
if st.session_state['selected_urls']:
    with results_container:
        st.success(f"You selected {len(st.session_state['selected_urls'])} items.")
        
        df_selected = pd.DataFrame(st.session_state['selected_urls'])
        st.dataframe(df_selected, use_container_width=True)

        # Prepare text list for easy copying to the main scraper
        url_list_text = "\n".join([d['Product URL'] for d in st.session_state['selected_urls']])
        st.text_area("Copy these URLs for the main scraper:", value=url_list_text, height=200)

    # Alternative: Button to clear selection
    if st.button("Clear Selection"):
        # Reset checkbox states
        for item in st.session_state['catalog_items']:
             st.session_state[f"select_{item['sku']}"] = False
        st.session_state['selected_urls'] = []
        st.rerun()
