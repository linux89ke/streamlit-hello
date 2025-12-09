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
from io import BytesIO

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Scraper", page_icon="🛒", layout="wide")

st.title("Scraper (V7.2 )")
st.markdown("Enter product URLs via text or Excel upload for batch processing.")

# --- SIDEBAR: SETUP INSTRUCTIONS ---
with st.sidebar:
    st.header("Usage")
    st.info("Either Paste multiple links or upload Excel file with links")


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

# --- 2. URL INPUT HANDLING FUNCTION ---
def get_urls_from_input(url_text, uploaded_file):
    """Parses URLs from text input and uploaded Excel file, checking for both KE and UG domains."""
    urls = set()
    VALID_DOMAINS = ["jumia.co.ke", "jumia.ug"]

    # 1. Process Text Input
    if url_text:
        text_urls = re.split(r'[\n, ]', url_text)
        for url in text_urls:
            url = url.strip()
            if any(domain in url for domain in VALID_DOMAINS) and url.startswith("http"):
                urls.add(url)
    
    # 2. Process File Upload
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file, header=None)
            else: 
                df = pd.read_csv(uploaded_file, header=None)
                
            for col in df.columns:
                for cell in df[col].astype(str):
                    if any(domain in cell for domain in VALID_DOMAINS) and cell.startswith("http"):
                        urls.add(cell)

        except Exception as e:
            st.error(f"Error reading file: {e}")
    
    return list(urls)

# --- 3. SCRAPING FUNCTION (V7.1) ---
def scrape_jumia(url):
    """Scrapes data with maximum robustness."""
    driver = get_driver()
    if not driver:
        return {'URL': url, 'Product Name': 'DRIVER_ERROR'}

    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2) 
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = {'URL': url, 'Product Name': 'N/A', 'Brand': 'N/A', 'Seller Name': 'N/A', 'Category': 'N/A', 'SKU': 'N/A', 'Image URLs': []}

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


        # 3. Seller Name 
        data['Seller Name'] = "N/A"
        try:
            seller_stats_container = soup.find('div', class_='-hr -pas')
            if seller_stats_container:
                seller_name_tag = seller_stats_container.find('p', class_='-m -pbs')
                if seller_name_tag:
                    data['Seller Name'] = seller_name_tag.text.strip()
        except Exception:
            pass
        
        if data['Seller Name'].lower() in ['details', 'follow', 'sell on jumia', 'n/a']:
             data['Seller Name'] = "N/A"


        # 4. Category 
        cats = []
        try:
            category_container = soup.find('div', class_='brcbs')
            if category_container:
                category_links = category_container.find_all('a')
            else:
                category_links = driver.find_elements(By.XPATH, "//ol//li//a | //nav//li//a | //div[contains(@class, 'brcbs')]//a")
            
            for link in category_links:
                txt = link.text.strip()
                if txt and txt.lower() not in ['home', 'jumia', ''] and txt != data['Product Name']:
                    cats.append(txt)
        except Exception:
            pass
            
        full_category = " > ".join(list(dict.fromkeys(cats))) if cats else "N/A"
        
        # Assign only the first level to the 'Category' field
        data['Category'] = full_category.split(' > ')[0]


        # 5. SKU 
        data['SKU'] = "N/A"
        all_text = soup.get_text(separator=' ', strip=True) 
        sku_match = re.search(r'SKU[:\s]*([A-Z0-9]+)', all_text) 
        if sku_match:
            data['SKU'] = sku_match.group(1).strip()
        
        # Fallback for SKU (from URL)
        if data['SKU'] == "N/A":
             match = re.search(r'-([A-Z0-9]+)\.html', url)
             if match:
                 data['SKU'] = match.group(1)

        # 6. Images 
        data['Image URLs'] = []
        for img in soup.find_all('img'):
            src = img.get('data-src') or img.get('src')
            if src and 'jumia.is' in src and ('/product/' in src or '/unsafe/' in src):
                if src.startswith('//'): src = 'https:' + src
                if src not in data['Image URLs']: data['Image URLs'].append(src)
        
        return data

    except Exception as e:
        st.error(f"Scraping Error for {url}: {str(e)}")
        return {'URL': url, 'Product Name': 'SCRAPE_FAILED', 'Error': str(e)}
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

# --- MAIN APP LOGIC ---

# Initialize session state for all results
if 'all_product_data' not in st.session_state:
    st.session_state['all_product_data'] = []

st.markdown("---")

col_text, col_file = st.columns(2)

with col_text:
    url_text = st.text_area("Paste URLs (one per line, comma, or space separated):", height=200, 
                            placeholder="https://www.jumia.co.ke/product-1...\nhttps://www.jumia.ug/product-2...")

with col_file:
    uploaded_file = st.file_uploader("Upload Excel/CSV file with URLs:", type=['xlsx', 'csv'])
    st.markdown("*(The file will be searched for any cell containing a Jumia product URL)*")


if st.button("Fetch Product Data", type="primary"):
    urls_to_scrape = get_urls_from_input(url_text, uploaded_file)
    
    if not urls_to_scrape:
        st.error("Please enter valid Jumia URLs or upload a file containing them.")
        st.session_state['all_product_data'] = []
    else:
        # Clear previous results before starting batch
        st.session_state['all_product_data'] = []
        total_urls = len(urls_to_scrape)
        
        st.info(f"Starting batch scrape for **{total_urls}** unique URLs...")
        progress_bar = st.progress(0)
        
        for i, url in enumerate(urls_to_scrape):
            # Update progress
            progress = (i + 1) / total_urls
            progress_bar.progress(progress)
            
            # Scrape data
            scraped_data = scrape_jumia(url)
            
            if scraped_data and scraped_data.get('Product Name') not in ['DRIVER_ERROR', 'SCRAPE_FAILED']:
                st.session_state['all_product_data'].append(scraped_data)

        progress_bar.empty()
        st.success(f"Batch scrape finished! Successfully processed **{len(st.session_state['all_product_data'])}** items.")
        st.rerun() 

# --- DISPLAY RESULTS AND DOWNLOAD ---

if st.session_state['all_product_data']:
    data_list = st.session_state['all_product_data']
    
    # 1. Prepare data for the final horizontal table
    processed_rows = []
    for item in data_list:
        first_image_url = item['Image URLs'][0] if item['Image URLs'] else "N/A"
        
        # Create row in the required format
        row = {
            'Seller Name': item.get('Seller Name', 'N/A'),
            'SKU': item.get('SKU', 'N/A'),
            'Product Name': item.get('Product Name', 'N/A'),
            'Brand': item.get('Brand', 'N/A'),
            'Category': item.get('Category', 'N/A'), # Uses the Level One category
            'Image URL': first_image_url,
            'Original URL': item.get('URL', 'N/A')
        }
        processed_rows.append(row)

    df_final = pd.DataFrame(processed_rows)
    
    # Define the final column order (config removed)
    column_order = ['Seller Name', 'SKU', 'Product Name', 'Brand', 'Category', 'Image URL', 'Original URL']
    df_final = df_final[column_order]

    # 2. Display the horizontal table
    st.markdown("---")
    st.subheader("✅ Extracted Product Data")
    st.markdown("Results ready for copying or downloading.")
    st.dataframe(df_final, use_container_width=True, hide_index=True)

    # 3. Download CSV
    @st.cache_data
    def convert_df_to_csv(df):
        # Cache the conversion to prevent repeated computation
        return df.to_csv(index=False).encode('utf-8')

    csv_data = convert_df_to_csv(df_final)

    st.download_button(
        label="📥 Download Results as CSV",
        data=csv_data,
        file_name="jumia_batch_results.csv",
        mime="text/csv"
    )

    if st.button("Clear All Results"):
        st.session_state['all_product_data'] = []
        st.rerun()

st.markdown("---")
st.markdown("Built with **Streamlit** & **Selenium** ")
