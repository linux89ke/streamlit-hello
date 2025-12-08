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
                
                # Always use headless in cloud environment
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("--disable-software-rasterizer")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                
                # Try different methods to initialize driver
                driver = None
                
                # Method 1: Try webdriver-manager
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except Exception as e1:
                    st.info(f"Method 1 failed: {str(e1)}")
                    
                    # Method 2: Try system chromedriver
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                    except Exception as e2:
                        st.info(f"Method 2 failed: {str(e2)}")
                        
                        # Method 3: Try chromium (for Linux/Streamlit Cloud)
                        try:
                            chrome_options.binary_location = "/usr/bin/chromium"
                            driver = webdriver.Chrome(options=chrome_options)
                        except Exception as e3:
                            st.error(f"All methods failed. Last error: {str(e3)}")
                            raise Exception("Could not initialize Chrome driver")
                
                if not driver:
                    raise Exception("Failed to create driver instance")
                
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
                
                # Product Name (from h1)
                product_name = soup.find('h1')
                product_data['Product Name'] = product_name.text.strip() if product_name else "N/A"
                
                # Brand - Look in the breadcrumb or "Similar products from" section
                brand_elem = None
                # Method 1: Look for "Similar products from [Brand]" link
                similar_text = soup.find(text=re.compile(r'Similar products from', re.I))
                if similar_text:
                    brand_link = similar_text.find_next('a')
                    if brand_link:
                        brand_elem = brand_link
                
                # Method 2: Look in specifications section
                if not brand_elem:
                    spec_list = soup.find_all(['li', 'tr', 'div'])
                    for item in spec_list:
                        if 'Brand:' in item.text or 'brand:' in item.text.lower():
                            # Extract text after "Brand:"
                            text = item.text
                            if 'Brand:' in text:
                                brand_text = text.split('Brand:')[1].strip().split('\n')[0].strip()
                                if brand_text:
                                    product_data['Brand'] = brand_text
                                    break
                
                if not product_data.get('Brand') and brand_elem:
                    product_data['Brand'] = brand_elem.text.strip()
                elif not product_data.get('Brand'):
                    product_data['Brand'] = "N/A"
                
                # SKU - Look in specifications
                sku_found = False
                all_text = soup.get_text()
                sku_match = re.search(r'SKU:\s*([A-Z0-9]+)', all_text, re.I)
                if sku_match:
                    product_data['SKU'] = sku_match.group(1).strip()
                    sku_found = True
                
                if not sku_found:
                    # Try finding in list items
                    list_items = soup.find_all(['li', 'div', 'span'])
                    for item in list_items:
                        item_text = item.get_text()
                        if 'SKU:' in item_text:
                            sku = item_text.split('SKU:')[1].strip().split()[0]
                            product_data['SKU'] = sku
                            sku_found = True
                            break
                
                if not sku_found:
                    product_data['SKU'] = "N/A"
                
                # Model/Config - Look in specifications
                model_found = False
                model_match = re.search(r'Model:\s*([A-Z0-9]+)', all_text, re.I)
                if model_match:
                    product_data['Model/Config'] = model_match.group(1).strip()
                    model_found = True
                
                if not model_found:
                    list_items = soup.find_all(['li', 'div', 'span'])
                    for item in list_items:
                        item_text = item.get_text()
                        if 'Model:' in item_text:
                            model = item_text.split('Model:')[1].strip().split()[0]
                            product_data['Model/Config'] = model
                            model_found = True
                            break
                
                if not model_found:
                    product_data['Model/Config'] = "N/A"
                
                # Category - Parse breadcrumb navigation properly
                categories = []
                # Look for nav or breadcrumb elements
                nav_elements = soup.find_all('a', {'href': re.compile(r'^/')})
                
                for link in nav_elements:
                    href = link.get('href', '')
                    text = link.text.strip()
                    
                    # Only include category links (not footer, not product links)
                    if text and href.startswith('/') and not href.endswith('.html'):
                        # Check if it's a category link
                        if any(cat in href for cat in ['/electronics/', '/phones-tablets/', '/televisions/', 
                                                       '/computing/', '/home-office/', '/fashion/',
                                                       '/smart-tvs', '/category-']):
                            if text not in categories and text.lower() not in ['home', 'shop', 'all']:
                                categories.append(text)
                
                # Remove duplicates and limit
                seen = set()
                unique_cats = []
                for cat in categories:
                    cat_lower = cat.lower()
                    if cat_lower not in seen:
                        seen.add(cat_lower)
                        unique_cats.append(cat)
                
                product_data['Category'] = " > ".join(unique_cats[:6]) if unique_cats else "N/A"
                
                # Seller Name - Look for seller information section
                seller_found = False
                
                # Method 1: Look for href with "-store" or seller profile
                seller_links = soup.find_all('a', {'href': re.compile(r'/[^/]+-store/|/[^/]+/
                
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
st.markdown("Built with Streamlit & Selenium | Scrapes Jumia Kenya product information"))})
                for link in seller_links:
                    href = link.get('href', '')
                    # Check if this looks like a seller/store link
                    if any(x in href.lower() for x in ['-store/', 'seller', 'shop']) or \
                       (href.count('/') == 2 and not href.endswith('.html')):
                        seller_name = link.text.strip()
                        if seller_name and len(seller_name) < 50:  # Reasonable seller name length
                            product_data['Seller Name'] = seller_name
                            seller_found = True
                            break
                
                # Method 2: Search for "Seller Information" section
                if not seller_found:
                    seller_heading = soup.find(text=re.compile(r'Seller Information|Sold by', re.I))
                    if seller_heading:
                        seller_section = seller_heading.find_next(['a', 'div', 'span'])
                        if seller_section:
                            seller_name = seller_section.text.strip()
                            if seller_name:
                                product_data['Seller Name'] = seller_name
                                seller_found = True
                
                if not seller_found:
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
