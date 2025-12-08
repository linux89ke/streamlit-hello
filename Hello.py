import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

st.set_page_config(page_title="Jumia Product Scraper", page_icon="🛒", layout="wide")

st.title("🛒 Jumia Product Information Scraper")
st.markdown("Enter a Jumia product URL to extract product details")

# Input field for URL
url = st.text_input("Enter Jumia Product URL:", placeholder="https://www.jumia.co.ke/...")

if st.button("Fetch Product Data", type="primary"):
    if not url:
        st.error("Please enter a valid URL")
    elif "jumia.co.ke" not in url:
        st.error("Please enter a valid Jumia Kenya URL")
    else:
        with st.spinner("Fetching product data..."):
            try:
                # Fetch the webpage
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract data
                product_data = {}
                
                # Product Name (from title or h1)
                product_name = soup.find('h1')
                product_data['Product Name'] = product_name.text.strip() if product_name else "N/A"
                
                # Brand (from breadcrumb or specific element)
                brand_elem = soup.find('a', {'class': re.compile('breadcrumb|brand', re.I)})
                if not brand_elem:
                    # Try to extract from product name or page
                    brand_search = soup.find_all('a', href=re.compile(r'/[^/]+/$'))
                    for elem in brand_search:
                        if 'brand' in elem.get('class', []) or '/brand/' in elem.get('href', ''):
                            brand_elem = elem
                            break
                
                # Alternative: look for "Brand:" label
                if not brand_elem:
                    brand_label = soup.find(text=re.compile(r'Brand:', re.I))
                    if brand_label:
                        brand_elem = brand_label.find_next('a')
                
                product_data['Brand'] = brand_elem.text.strip() if brand_elem else "N/A"
                
                # SKU
                sku_elem = soup.find(text=re.compile(r'SKU:', re.I))
                if sku_elem:
                    sku_text = sku_elem.find_next().text.strip()
                    product_data['SKU'] = sku_text
                else:
                    product_data['SKU'] = "N/A"
                
                # Model/Config
                model_elem = soup.find(text=re.compile(r'Model:', re.I))
                if model_elem:
                    model_text = model_elem.find_next().text.strip()
                    product_data['Model/Config'] = model_text
                else:
                    product_data['Model/Config'] = "N/A"
                
                # Category (from breadcrumbs)
                breadcrumbs = soup.find_all('a', {'class': re.compile('breadcrumb', re.I)})
                if breadcrumbs:
                    categories = [b.text.strip() for b in breadcrumbs if b.text.strip()]
                    product_data['Category'] = " > ".join(categories)
                else:
                    product_data['Category'] = "N/A"
                
                # Seller Name
                seller_elem = soup.find('a', href=re.compile(r'/[^/]+-store/'))
                if not seller_elem:
                    seller_elem = soup.find(text=re.compile(r'Seller|Store', re.I))
                    if seller_elem:
                        seller_elem = seller_elem.find_next('a')
                
                product_data['Seller Name'] = seller_elem.text.strip() if seller_elem else "N/A"
                
                # Image URLs
                images = []
                img_elements = soup.find_all('img', {'src': re.compile(r'jumia\.is.*product')})
                
                for img in img_elements:
                    img_url = img.get('src') or img.get('data-src')
                    if img_url and 'product' in img_url:
                        # Convert to high quality URL
                        if 'fit-in' in img_url:
                            images.append(img_url)
                        elif img_url.startswith('//'):
                            images.append('https:' + img_url)
                        elif not img_url.startswith('http'):
                            images.append('https://ke.jumia.is' + img_url)
                        else:
                            images.append(img_url)
                
                # Remove duplicates while preserving order
                images = list(dict.fromkeys(images))
                product_data['Image URLs'] = images
                
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
                        st.image(images[0], caption="Main Product Image", use_column_width=True)
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
                    'Image URL 1': [images[0] if len(images) > 0 else ''],
                    'Image URL 2': [images[1] if len(images) > 1 else ''],
                    'Image URL 3': [images[2] if len(images) > 2 else ''],
                    'Image URL 4': [images[3] if len(images) > 3 else ''],
                    'Image URL 5': [images[4] if len(images) > 4 else ''],
                }
                
                df = pd.DataFrame(csv_data)
                csv = df.to_csv(index=False)
                
                st.download_button(
                    label="📥 Download as CSV",
                    data=csv,
                    file_name=f"product_{product_data['SKU']}.csv",
                    mime="text/csv"
                )
                
            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching URL: {str(e)}")
            except Exception as e:
                st.error(f"Error parsing product data: {str(e)}")
                st.exception(e)

# Add footer
st.markdown("---")
st.markdown("Built with Streamlit | Scrapes Jumia Kenya product information")
