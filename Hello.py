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

st.set_page_config(page_title="Jumia Product Scraper", page_icon="🛒", layout="wide")

st.title("🛒 Jumia Product Information Scraper")
st.markdown("Enter a Jumia product URL to extract product details")

# Installation instructions
with st.expander("📦 Installation Instructions"):
    st.code("""
# Install required packages:
pip install streamlit selenium beautifulsoup4 pandas webdriver-manager

# Or if webdriver-manager doesn't work, download ChromeDriver manually from:
# https://chromedriver.chromium.org/downloads
    """, language="bash")

# Input field for URL
url = st.text_input("Enter Jumia Product URL:", placeholder="https://www.jumia.co.ke/...")

# Options
use_headless = st.checkbox("Run in headless mode (no browser window)", value=True)

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
                
                if use_headless:
                    chrome_options.add_argument("--headless")
                
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                
                # Try to use webdriver-manager
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except:
                    # Fallback to system chromedriver
                    driver = webdriver.Chrome(options=chrome_options)
                
                # Hide webdriver property
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            with st.spinner("Fetching product data..."):
                # Load the page
                driver.get(url)
                
                # Wait for page to load
                time.sleep(3)
                
                # Wait for main content
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "h1"))
                    )
                except:
                    pass
                
                # Get page source and parse
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Extract data
                product_data = {}
                
                # Product Name
                product_name = soup.find('h1')
                product_data['Product Name'] = product_name.text.strip() if product_name else "N/A"
                
                # Brand
                brand_elem = None
                # Try multiple methods to find brand
                brand_patterns = [
                    soup.find('a', {'href': re.compile(r'/[^/]+-\d+/$')}),
                    soup.find(text=re.compile(r'Brand:', re.I))
                ]
                
                for pattern in brand_patterns:
                    if pattern:
                        if hasattr(pattern, 'find_next'):
                            brand_elem = pattern.find_next('a')
                        else:
                            brand_elem = pattern
                        break
                
                product_data['Brand'] = brand_elem.text.strip() if brand_elem else "N/A"
                
                # SKU
                sku_elem = soup.find(text=re.compile(r'SKU:', re.I))
                if sku_elem:
                    sku_parent = sku_elem.find_parent()
                    sku_text = sku_parent.text.replace('SKU:', '').strip() if sku_parent else "N/A"
                    product_data['SKU'] = sku_text
                else:
                    product_data['SKU'] = "N/A"
                
                # Model/Config
                model_elem = soup.find(text=re.compile(r'Model:', re.I))
                if model_elem:
                    model_parent = model_elem.find_parent()
                    model_text = model_parent.text.replace('Model:', '').strip() if model_parent else "N/A"
                    product_data['Model/Config'] = model_text
                else:
                    product_data['Model/Config'] = "N/A"
                
                # Category (from breadcrumbs)
                breadcrumb_links = soup.find_all('a', {'href': True})
                categories = []
                for link in breadcrumb_links:
                    href = link.get('href', '')
                    if any(cat in href for cat in ['/electronics/', '/phones-tablets/', '/computing/', '/category-']):
                        text = link.text.strip()
                        if text and text not in categories and text != 'Home':
                            categories.append(text)
                
                product_data['Category'] = " > ".join(categories[:5]) if categories else "N/A"
                
                # Seller Name
                seller_elem = soup.find('a', {'href': re.compile(r'/[^/]+/$')})
                if seller_elem and 'store' in seller_elem.get('href', '').lower():
                    product_data['Seller Name'] = seller_elem.text.strip()
                else:
                    # Alternative method
                    seller_section = soup.find(text=re.compile(r'Seller', re.I))
                    if seller_section:
                        seller_link = seller_section.find_next('a')
                        product_data['Seller Name'] = seller_link.text.strip() if seller_link else "N/A"
                    else:
                        product_data['Seller Name'] = "N/A"
                
                # Image URLs
                images = []
                img_elements = soup.find_all('img', {'src': True})
                
                for img in img_elements:
                    img_url = img.get('src') or img.get('data-src')
                    if img_url and 'product' in img_url and 'jumia.is' in img_url:
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        if img_url not in images:
                            images.append(img_url)
                
                product_data['Image URLs'] = images
                
                # Close browser
                driver.quit()
                driver = None
                
                # Display results
                st.success("✅ Product data fetched successfully!")
                
                # Create two columns
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📋 Product Details")
                    st.write(f"**Product Name:** {product_data['Product Name']}")
                    st.write(f"**Brand:** {product_data['Brand']}")
                    st.write(f"**SKU:** {product_data['SKU']}")
                    st.write(f"**Model/Config:** {product_data['Model/Config']}")
                    st.write(f"**Category:** {product_data['Category']}")
                    st.write(f"**Seller Name:** {product_data['Seller Name']}")
                
                with col2:
                    st.subheader("🖼️ Product Images")
                    if images:
                        st.write(f"Found {len(images)} images")
                        # Display first image as preview
                        try:
                            st.image(images[0], caption="Main Product Image", use_column_width=True)
                        except:
                            st.warning("Could not display image preview")
                    else:
                        st.warning("No images found")
                
                # Display all image URLs
                if images:
                    st.subheader("📷 All Image URLs")
                    for i, img_url in enumerate(images, 1):
                        st.code(img_url, language=None)
                
                # Create downloadable CSV
                st.subheader("💾 Download Data")
                
                # Prepare data for CSV
                csv_data = {
                    'Seller Name': [product_data['Seller Name']],
                    'SKU': [product_data['SKU']],
                    'Product Name': [product_data['Product Name']],
                    'Brand': [product_data['Brand']],
                    'Category': [product_data['Category']],
                    'Model/Config': [product_data['Model/Config']],
                }
                
                # Add image URLs
                for i, img_url in enumerate(images[:10], 1):
                    csv_data[f'Image URL {i}'] = [img_url]
                
                df = pd.DataFrame(csv_data)
                csv = df.to_csv(index=False)
                
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv,
                    file_name=f"jumia_product_{product_data['SKU']}.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.exception(e)
            
            # Troubleshooting tips
            with st.expander("🔧 Troubleshooting"):
                st.markdown("""
                **Common issues and solutions:**
                
                1. **ChromeDriver not found:**
                   - Install: `pip install webdriver-manager`
                   - Or download manually from https://chromedriver.chromium.org/
                
                2. **Chrome browser not installed:**
                   - Install Google Chrome browser
                
                3. **Still getting errors:**
                   - Try unchecking "Run in headless mode"
                   - Make sure Chrome and ChromeDriver versions match
                   - Run: `pip install --upgrade selenium`
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
st.markdown("Built with Streamlit & Selenium | Scrapes Jumia Kenya product information")
