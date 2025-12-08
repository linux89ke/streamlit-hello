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

st.set_page_config(page_title="Jumia Product Scraper", page_icon="🛒", layout="wide")

st.title("🛒 Jumia Product Information Scraper")
st.markdown("Enter a Jumia product URL to extract product details")

# Installation instructions
with st.expander("📦 Streamlit Cloud Setup (packages.txt/requirements.txt)"):
    st.code("""
# requirements.txt:
streamlit
selenium
beautifulsoup4
pandas

# packages.txt: (for Streamlit Cloud on Linux)
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
                
                # Streamlined Driver Initialization
                try:
                    # Attempt Streamlit Cloud/Linux path setup
                    service = Service(executable_path="/usr/bin/chromedriver")
                    chrome_options.binary_location = "/usr/bin/chromium"
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    st.info("Using Streamlit Cloud/Linux configuration.")
                except:
                    # Fallback for local environments (requires local setup)
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                        st.info("Using local Chrome configuration.")
                    except Exception as e_local:
                        st.error(f"Could not initialize Chrome driver. Local Error: {str(e_local)}")
                        raise Exception("Failed to create driver instance.")
                
                if not driver:
                    raise Exception("Failed to create driver instance")
                
                # Hide webdriver property
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            with st.spinner("Fetching product data..."):
                # Load the page
                driver.get(url)
                
                # Wait for main product content to load (e.g., the title h1)
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "h1"))
                    )
                except:
                    st.warning("Page loading timeout. Continuing with available content.")
                
                # Scroll down slightly to ensure dynamic content loads (like seller info)
                driver.execute_script("window.scrollTo(0, 300);")
                time.sleep(2) 
                
                # Get page source and parse
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # --- EXTRACT DATA ---
                product_data = {}
                all_text = soup.get_text()

                # 1. Product Name (from h1)
                product_name = soup.find('h1')
                product_data['Product Name'] = product_name.text.strip() if product_name else "N/A"
                
                # 2. Brand
                brand_text = "N/A"
                # Look for the brand link associated with the label
                brand_link_elem = soup.find('a', href=re.compile(r'/catalog/\?q='))
                if brand_link_elem:
                    # Brand is often the first part of the link text or the link itself
                    brand_text = brand_link_elem.text.strip()
                elif 'Brand:' in all_text:
                    # Fallback to regex search
                    match = re.search(r'Brand:\s*([A-Za-z0-9\s]+?)(?:\||\n)', all_text, re.I | re.DOTALL)
                    if match:
                        brand_text = match.group(1).strip()
                
                product_data['Brand'] = brand_text
                
                # 3. Seller Name
                seller_name = "N/A"
                # The seller name is often wrapped in a tag near "Seller Score"
                seller_elem = soup.find('a', href=re.compile(r'/seller/'))
                if seller_elem:
                    seller_name = seller_elem.text.strip()
                elif 'Seller Score' in all_text:
                    # Fallback: search text near the score
                    match = re.search(r'([A-Z0-9\s]+)\s*\d+%', all_text)
                    if match:
                        seller_name = match.group(1).strip()
                
                product_data['Seller Name'] = seller_name
                
                # 4. SKU and 5. Model/Config - Search through text and URL
                
                # SKU: Try to extract from URL if not found in page text (Jumia often uses the product ID as the SKU)
                product_data['SKU'] = url.split('-')[-1].split('.')[0] if '.' in url.split('-')[-1] else "N/A"
                
                # Check page text for a formal SKU
                sku_match = re.search(r'SKU:\s*([A-Z0-9]+)', all_text, re.I)
                if sku_match:
                    product_data['SKU'] = sku_match.group(1).strip()

                # Model/Config: Often present in the h1 text itself or specifications
                model_match = re.search(r'Model:\s*([A-Z0-9\-\/]+)', all_text, re.I)
                # If not found, try to infer from product name (e.g., HTC4300QFS)
                config = "N/A"
                if model_match:
                    config = model_match.group(1).strip()
                elif product_name and product_data['Brand'] != "N/A":
                    # Try to find a code that looks like a model number in the title
                    title_parts = product_data['Product Name'].replace(product_data['Brand'], '').strip().split()
                    potential_model = [p for p in title_parts if re.search(r'[A-Z0-9]{5,}', p)]
                    if potential_model:
                        config = potential_model[0]
                
                product_data['Model/Config'] = config
                
                # 6. Category - Parse breadcrumb navigation
                categories = []
                # Jumia breadcrumb links use class '_aj'
                nav_elements = soup.find_all('a', class_='_aj') 
                
                for link in nav_elements:
                    text = link.text.strip()
                    # Filter out 'Home' and the last element if it matches the product name
                    if text and text.lower() not in ['home', 'jumia'] and text not in product_data['Product Name']:
                        categories.append(text)
                
                # Remove duplicates while preserving order
                unique_cats = list(dict.fromkeys(categories))
                product_data['Category'] = " > ".join(unique_cats) if unique_cats else "N/A"
                
                # 7. Image URLs
                images = []
                # Find the main image using common Jumia image attributes
                img_elements = soup.find_all('img', src=re.compile(r'jumia\.is/product/'))
                
                for img in img_elements:
                    img_url = img.get('data-src') or img.get('src')
                    if img_url and 'jumia.is' in img_url:
                        # Ensure the URL is absolute
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
                
                # Filter data for display table based on user request
                display_data = {
                    'Product Name': product_data['Product Name'],
                    'Brand': product_data['Brand'],
                    'Category': product_data['Category'],
                    'Seller Name': product_data['Seller Name'],
                    'SKU': product_data['SKU'],
                    'Model/Config': product_data['Model/Config'],
                }
                
                # Create two columns
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📋 Requested Product Details")
                    
                    # Convert dict to DataFrame for clean display
                    display_df = pd.DataFrame([{'Key': k, 'Value': v} for k, v in display_data.items()])
                    st.table(display_df.set_index('Key'))

                with col2:
                    st.subheader("🖼️ Product Images")
                    if product_data['Image URLs']:
                        images = product_data['Image URLs']
                        st.write(f"Found **{len(images)}** images.")
                        
                        # Display first image as preview
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
            
            # Troubleshooting tips
            with st.expander("🔧 Troubleshooting"):
                st.markdown("""
                **Common issues and solutions:**
                
                1. **If deploying to Streamlit Cloud:** Ensure your `packages.txt` and `requirements.txt` files are correct as per the instructions above.
                2. **"Failed to create driver instance" (Local):** Make sure you have Google Chrome installed and that your Selenium version is recent (`pip install --upgrade selenium`).
                3. **Elements not found:** The website structure may have changed. The scraper needs to be updated to match new Jumia HTML classes/tags.
                """)
        
        finally:
            # Make sure browser is closed
            if driver:
                try:
                    driver.quit()
                except:
                    pass

# Add footer
st.markdown("---")
st.markdown("Built with **Streamlit** & **Selenium** | Scrapes Jumia Kenya product information")
