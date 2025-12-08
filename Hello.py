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

st.set_page_config(page_title="Jumia Product Scraper (Final)", page_icon="🛒", layout="wide")

st.title("🛒 Jumia Product Information Scraper (Final Robust Version)")
st.markdown("Enter a Jumia product URL to extract product details.")

# Installation instructions for Streamlit Cloud
with st.expander("📦 Streamlit Cloud Setup (Deployment Files)"):
    st.code("""
# requirements.txt:
streamlit
selenium
beautifulsoup4
pandas

# packages.txt: (Required for Streamlit Cloud to install Chrome dependencies)
chromium
chromium-driver
    """, language="bash")

# Input field for URL
url = st.text_input("Enter Jumia Product URL:", placeholder="https://www.jumia.co.ke/...")

if st.button("Fetch Product Data", type="primary"):
    if not url:
        st.error("Please enter a valid URL")
    elif "jumia.co.ke" not in url:
        st.error("Please enter a valid Jumia Kenya URL")
    else:
        driver = None
        try:
            with st.spinner("Setting up browser..."):
                # Setup Chrome options
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
                
                # Streamlined Driver Initialization (Prioritizes Streamlit Cloud setup)
                try:
                    service = Service(executable_path="/usr/bin/chromedriver")
                    chrome_options.binary_location = "/usr/bin/chromium"
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except Exception as e_cloud:
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                    except Exception as e_local:
                        st.error(f"Could not initialize Chrome driver. Cloud Error: {str(e_cloud)}. Local Error: {str(e_local)}")
                        raise Exception("Failed to create driver instance.")
                
                if not driver:
                    raise Exception("Failed to create driver instance")
                
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            with st.spinner("Fetching product data..."):
                driver.get(url)
                
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
                
                driver.execute_script("window.scrollTo(0, 300);")
                time.sleep(2) 
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # --- EXTRACT DATA ---
                product_data = {}
                all_text = soup.get_text()

                # 1. Product Name (from h1)
                product_name_elem = soup.find('h1')
                product_name = product_name_elem.text.strip() if product_name_elem else "N/A"
                product_data['Product Name'] = product_name
                
                # 2. Brand (Using XPath fallback)
                brand_text = "N/A"
                try:
                    # XPath: Look for the <a> tag that is a child of the element containing the text 'Brand:'
                    brand_elem_xpath = driver.find_element(By.XPATH, "//div[contains(., 'Brand:')]/a")
                    brand_text = brand_elem_xpath.text.strip()
                except:
                    # Fallback to regex in case XPath fails
                    if product_name != "N/A":
                        brand_fallback = re.search(r'^([A-Z][a-z]{2,})\s+', product_name)
                        if brand_fallback:
                             brand_text = brand_fallback.group(1).strip()
                
                product_data['Brand'] = brand_text
                
                # 3. Seller Name (FINAL FIX using robust XPath)
                seller_name = "N/A"
                try:
                    # XPath: Find the link that precedes the 'Seller Score' container
                    # This targets the <a> tag holding the seller's name
                    seller_elem_xpath = driver.find_element(By.XPATH, "//div[contains(., 'Seller Score')]/ancestor::div[1]/preceding-sibling::div[1]/a[1]")
                    seller_name = seller_elem_xpath.text.strip()
                except:
                    # Fallback: Simple link search
                    seller_link = soup.find('a', href=re.compile(r'/seller/'))
                    if seller_link:
                        seller_name = seller_link.text.strip()
                
                product_data['Seller Name'] = seller_name
                
                # 4. SKU 
                sku_match = re.search(r'SKU:\s*([A-Z0-9]+)', all_text, re.I)
                if sku_match:
                    product_data['SKU'] = sku_match.group(1).strip()
                else:
                    product_data['SKU'] = url.split('-')[-1].split('.')[0] if '.' in url.split('-')[-1] else "N/A"

                # 5. Model/Config (Fixed cleanup issue by strict regex on title)
                config = "N/A"
                # Search for alphanumeric model numbers in the title (e.g., HTC4300QFS)
                model_in_title = re.search(r'([A-Z]{3,}\d{3,}[A-Z0-9]*)', product_name)
                if model_in_title:
                    config = model_in_title.group(1)
                
                product_data['Model/Config'] = config
                
                # 6. Category (FINAL FIX using robust XPath for breadcrumbs)
                categories = []
                try:
                    # XPath: Find all <a> tags within the ordered list (OL) structure of the breadcrumbs
                    category_links = driver.find_elements(By.XPATH, "//ol//li//a")
                    for link in category_links:
                        text = link.text.strip()
                        if text and text.lower() not in ['home', 'jumia'] and text != product_data['Product Name']:
                            categories.append(text)
                except Exception:
                    pass # If XPath fails, categories remains empty

                unique_cats = list(dict.fromkeys(categories))
                product_data['Category'] = " > ".join(unique_cats) if unique_cats else "N/A"
                
                # 7. Image URLs 
                images = []
                # Search for the primary image data attribute
                img_elements = soup.find_all('img', {'data-src': re.compile(r'jumia\.is/product/|jfs')})
                
                for img in img_elements:
                    img_url = img.get('data-src') or img.get('src')
                    if img_url and ('jumia.is' in img_url or 'jfs' in img_url):
                        if img_url.startswith('//'): 
                            img_url = 'https:' + img_url
                        if img_url not in images:
                            images.append(img_url)
                
                product_data['Image URLs'] = images
                
                # Close browser
                driver.quit()
                driver = None
                
                # --- DISPLAY RESULTS ---
                st.success("✅ Product data fetched successfully!")
                
                # Prepare data for display table
                display_data = {
                    'Product Name': product_data['Product Name'],
                    'Brand': product_data['Brand'],
                    'Category': product_data['Category'],
                    'Seller Name': product_data['Seller Name'],
                    'SKU': product_data['SKU'],
                    'Model/Config': product_data['Model/Config'],
                }
                
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📋 Requested Product Details")
                    
                    display_df = pd.DataFrame([{'Key': k, 'Value': v} for k, v in display_data.items()])
                    st.table(display_df.set_index('Key'))

                with col2:
                    st.subheader("🖼️ Product Images")
                    if product_data['Image URLs']:
                        images = product_data['Image URLs']
                        st.write(f"Found **{len(images)}** images.")
                        
                        try:
                            st.image(images[0], caption="Main Product Image Preview", use_column_width=True)
                        except:
                            st.warning("Could not display image preview")
                    else:
                        st.warning("No images found.")
                
                # Display all image URLs
                if product_data['Image URLs']:
                    st.subheader("📷 All Image URLs")
                    image_urls_markdown = "\n".join([f"- **Image {i+1}:** `{url}`" for i, url in enumerate(product_data['Image URLs'])])
                    st.markdown(image_urls_markdown)
                
                # Create downloadable CSV
                st.subheader("💾 Download Data")
                
                csv_data = {
                    'URL': [url],
                    **display_data
                }
                
                # Add image URLs to CSV data
                for i, img_url in enumerate(product_data['Image URLs'][:10], 1):
                    csv_data[f'Image URL {i}'] = [img_url]
                
                df = pd.DataFrame(csv_data)
                csv = df.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv,
                    file_name=f"jumia_product_{product_data['SKU'] or 'data'}.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"A critical error occurred: {str(e)}")
            st.exception(e)
            
            with st.expander("🔧 Troubleshooting"):
                st.markdown("""
                **Common issues and solutions:**
                
                1. **Selector Failure:** The website structure changed again. If the Brand/Seller/Category still fail, you'll need to manually inspect the current Jumia page and adjust the XPath or CSS selectors.
                2. **"Failed to create driver instance" (Local):** Ensure Chrome and the correct Chrome driver are installed locally.
                3. **Cloud Deployment:** Verify `packages.txt` and `requirements.txt`.
                """)
        
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

# Add footer
st.markdown("---")
st.markdown("Built with **Streamlit** & **Selenium** | Scrapes Jumia Kenya product information")
