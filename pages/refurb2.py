import streamlit as st
from PIL import Image
import requests
from io import BytesIO
import numpy as np

# Page config
st.set_page_config(
    page_title="Refurbished Tag Generator",
    page_icon="🏷️",
    layout="wide"
)

# Title and description
st.title("🏷️ Refurbished Product Tag Generator")
st.markdown("Upload a product image and add a refurbished grade tag to it!")

# Sidebar for tag selection
st.sidebar.header("Tag Settings")
tag_type = st.sidebar.selectbox(
    "Select Refurbished Grade:",
    ["Renewed", "Refurbished", "Grade A", "Grade B", "Grade C"]
)

st.sidebar.markdown("---")
st.sidebar.header("Processing Mode")
processing_mode = st.sidebar.radio(
    "Choose mode:",
    ["Single Image", "Bulk Processing"]
)

# Tag file mapping - will check multiple locations
import os
import re
from bs4 import BeautifulSoup

def get_tag_path(filename):
    """Check multiple possible locations for tag files"""
    possible_paths = [
        filename,  # Same directory as script
        os.path.join(os.path.dirname(__file__), filename),  # Script directory
        os.path.join(os.getcwd(), filename),  # Current working directory
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # If not found, return the filename (will show error)
    return filename

tag_files = {
    "Renewed": "RefurbishedStickerUpdated-Renewd.png",
    "Refurbished": "RefurbishedStickerUpdate-No-Grading.png",
    "Grade A": "Refurbished-StickerUpdated-Grade-A.png",
    "Grade B": "Refurbished-StickerUpdated-Grade-B.png",
    "Grade C": "Refurbished-StickerUpdated-Grade-C.png"
}

@st.cache_resource
def get_driver_path():
    """Cache driver installation."""
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType
        return ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    except Exception:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            return ChromeDriverManager().install()
        except Exception:
            return None

def get_chrome_options(headless=True):
    """Configure Chrome options for stability."""
    from selenium.webdriver.chrome.options import Options
    
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Detect browser binary
    possible_paths = [
        "/usr/bin/chromium", 
        "/usr/bin/chromium-browser", 
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            break
    
    return chrome_options

def get_driver(headless=True):
    """Create WebDriver with comprehensive error handling."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        st.error("Selenium not installed. Install with: pip install selenium webdriver-manager")
        return None
    
    chrome_options = get_chrome_options(headless)
    driver = None
    
    try:
        driver_path = get_driver_path()
        if driver_path:
            service = Service(driver_path)
            service.log_path = os.devnull
            driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception:
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            return None

    if driver:
        try:
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.set_page_load_timeout(20)
            driver.implicitly_wait(5)
        except Exception:
            pass
    
    return driver

def search_jumia_by_sku(sku, base_url, search_url):
    """Search Jumia by SKU using Selenium to bypass 403 errors"""
    driver = None
    
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
    except ImportError:
        st.error("Selenium not installed. Install with: pip install selenium webdriver-manager")
        return None
    
    try:
        # Create driver
        driver = get_driver(headless=True)
        if not driver:
            st.error("Could not initialize browser driver")
            return None
        
        # Go to search URL
        driver.get(search_url)
        
        # Wait for page to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1"))
            )
        except TimeoutException:
            st.error("Page load timeout")
            return None
        
        # Check if no results
        if "There are no results for" in driver.page_source or "No results found" in driver.page_source:
            st.warning(f"No products found for SKU: {sku}")
            return None
        
        # Find first product link
        try:
            product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
            if not product_links:
                product_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='.html']")
            
            if product_links:
                product_url = product_links[0].get_attribute("href")
                driver.get(product_url)
                
                # Wait for product page to load
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
                
                import time
                time.sleep(1)  # Let images load
                
                # Get page source and parse
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Extract image URL
                image_url = None
                
                # Method 1: og:image meta tag
                og_image = soup.find('meta', property='og:image')
                if og_image and og_image.get('content'):
                    image_url = og_image['content']
                
                # Method 2: Find main product images
                if not image_url:
                    for img in soup.find_all('img', limit=15):
                        src = img.get('data-src') or img.get('src')
                        if src and ('/product/' in src or '/unsafe/' in src or 'jumia.is' in src):
                            if src.startswith('//'):
                                src = 'https:' + src
                            elif src.startswith('/'):
                                src = base_url + src
                            image_url = src
                            break
                
                if image_url:
                    # Download the image
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Referer': base_url,
                    }
                    
                    img_response = requests.get(image_url, headers=headers, timeout=15)
                    img_response.raise_for_status()
                    
                    return Image.open(BytesIO(img_response.content)).convert("RGBA")
                else:
                    st.warning("Found product but could not extract image")
                    return None
            else:
                st.warning(f"No products found for SKU: {sku}")
                return None
                
        except Exception as e:
            st.error(f"Error finding product: {str(e)}")
            return None
            
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

# Main content area
if processing_mode == "Single Image":
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📤 Upload Product Image")
        
        # Upload method selection
        upload_method = st.radio(
            "Choose upload method:",
            ["Upload from device", "Load from URL", "Load from SKU"]
        )
        
        product_image = None
        
        if upload_method == "Upload from device":
            uploaded_file = st.file_uploader(
                "Choose an image file",
                type=["png", "jpg", "jpeg", "webp"]
            )
            if uploaded_file is not None:
                product_image = Image.open(uploaded_file).convert("RGBA")
        
        elif upload_method == "Load from URL":
            image_url = st.text_input("Enter image URL:")
            if image_url:
                try:
                    response = requests.get(image_url)
                    product_image = Image.open(BytesIO(response.content)).convert("RGBA")
                    st.success("✅ Image loaded successfully!")
                except Exception as e:
                    st.error(f"❌ Error loading image: {str(e)}")
        
        else:  # Load from SKU
            sku_input = st.text_input(
                "Enter Product SKU:",
                placeholder="e.g., GE840EA6C62GANAFAMZ"
            )
            
            jumia_site = st.radio(
                "Select Jumia Site:",
                ["Jumia Kenya", "Jumia Uganda"],
                horizontal=True
            )
            
            if sku_input:
                # Determine the base URL
                if jumia_site == "Jumia Kenya":
                    base_url = "https://www.jumia.co.ke"
                    search_url = f"https://www.jumia.co.ke/catalog/?q={sku_input}"
                else:
                    base_url = "https://www.jumia.ug"
                    search_url = f"https://www.jumia.ug/catalog/?q={sku_input}"
                
                if st.button("🔍 Search and Extract Image", use_container_width=True):
                    with st.spinner(f"Searching {jumia_site} for SKU..."):
                        product_image = search_jumia_by_sku(sku_input, base_url, search_url)
                        if product_image:
                            st.success("✅ Image found and loaded successfully!")
                        else:
                            st.error("❌ Could not find product with this SKU")

    with col2:
        st.subheader("✨ Preview")
        
        if product_image is not None:
            # Process single image (existing logic)
            # Load the selected tag
            try:
                tag_filename = tag_files[tag_type]
                tag_path = get_tag_path(tag_filename)
                
                if not os.path.exists(tag_path):
                    st.error(f"❌ Tag file not found: {tag_filename}")
                    st.info("""
                    **Please make sure the tag PNG files are in the same directory as this app.**
                    
                    Required files:
                    - RefurbishedStickerUpdated-Renewd.png
                    - RefurbishedStickerUpdate-No-Grading.png
                    - Refurbished-StickerUpdated-Grade-A.png
                    - Refurbished-StickerUpdated-Grade-B.png
                    - Refurbished-StickerUpdated-Grade-C.png
                    """)
                    st.stop()
                
                tag_image = Image.open(tag_path).convert("RGBA")
                
                # Get original dimensions
                orig_prod_width, orig_prod_height = product_image.size
                canvas_width, canvas_height = tag_image.size
                
                # Calculate sizes
                banner_height = int(canvas_height * 0.095)
                vert_tag_width = int(canvas_width * 0.18)
                
                # Available area for product
                available_width = canvas_width - vert_tag_width
                available_height = canvas_height - banner_height
                
                # Scale product with padding
                padding_factor = 0.74
                fit_width = int(available_width * padding_factor)
                fit_height = int(available_height * padding_factor)
                
                product_aspect_ratio = orig_prod_height / orig_prod_width
                
                # Try fitting by width
                new_prod_width = fit_width
                new_prod_height = int(new_prod_width * product_aspect_ratio)
                
                # If too tall, fit by height
                if new_prod_height > fit_height:
                    new_prod_height = fit_height
                    new_prod_width = int(new_prod_height / product_aspect_ratio)
                
                # Resize product
                product_resized = product_image.resize((new_prod_width, new_prod_height), Image.Resampling.LANCZOS)
                
                # Create result
                result_image = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
                
                # Center product
                prod_x = (available_width - new_prod_width) // 2
                prod_y = (available_height - new_prod_height) // 2
                
                # Paste product FIRST
                if product_resized.mode == 'RGBA':
                    result_image.paste(product_resized, (prod_x, prod_y), product_resized)
                else:
                    result_image.paste(product_resized, (prod_x, prod_y))
                
                # Then paste the tag template ON TOP
                if tag_image.mode == 'RGBA':
                    result_image.paste(tag_image, (0, 0), tag_image)
                else:
                    result_image.paste(tag_image, (0, 0))
                
                # Display the result
                st.image(result_image, use_container_width=True)
                
                # Download button
                st.markdown("---")
                
                # Convert image to bytes as JPEG
                buf = BytesIO()
                result_image.save(buf, format="JPEG", quality=95)
                buf.seek(0)
                
                st.download_button(
                    label="⬇️ Download Tagged Image (JPEG)",
                    data=buf,
                    file_name=f"refurbished_product_{tag_type.lower().replace(' ', '_')}.jpg",
                    mime="image/jpeg",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"❌ Error processing image: {str(e)}")
        else:
            st.info("👆 Upload or provide a URL for a product image to get started!")

else:  # Bulk Processing Mode
    st.subheader("📦 Bulk Processing")
    st.markdown("Process multiple products at once")
    
    bulk_method = st.radio(
        "Choose bulk input method:",
        ["Upload multiple images", "Enter URLs manually", "Upload Excel file with URLs", "Enter SKUs"]
    )
    
    products_to_process = []  # List of (image, filename) tuples
    
    if bulk_method == "Upload multiple images":
        uploaded_files = st.file_uploader(
            "Choose multiple image files",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True
        )
        
        if uploaded_files:
            st.info(f"✅ {len(uploaded_files)} files uploaded")
            for idx, uploaded_file in enumerate(uploaded_files):
                try:
                    img = Image.open(uploaded_file).convert("RGBA")
                    filename = uploaded_file.name.rsplit('.', 1)[0]  # Remove extension
                    products_to_process.append((img, filename))
                except Exception as e:
                    st.warning(f"⚠️ Could not load {uploaded_file.name}: {str(e)}")
    
    elif bulk_method == "Enter URLs manually":
        urls_input = st.text_area(
            "Enter image URLs (one per line):",
            height=200,
            placeholder="https://example.com/image1.jpg\nhttps://example.com/image2.jpg\nhttps://example.com/image3.jpg"
        )
        
        if urls_input.strip():
            urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
            st.info(f"📝 {len(urls)} URLs entered")
            
            for idx, url in enumerate(urls):
                try:
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    img = Image.open(BytesIO(response.content)).convert("RGBA")
                    filename = f"image_{idx+1}"
                    products_to_process.append((img, filename))
                except Exception as e:
                    st.warning(f"⚠️ Could not load {url}: {str(e)}")
    
    elif bulk_method == "Upload Excel file with URLs":
        st.markdown("""
        **Excel file format:**
        - Column A: Image URLs (required)
        - Column B: Product names/IDs (optional - will be used as filename)
        
        Example:
        | Image URL | Product Name |
        |-----------|--------------|
        | https://... | Product 1 |
        | https://... | Product 2 |
        """)
        
        excel_file = st.file_uploader(
            "Upload Excel file (.xlsx or .xls)",
            type=["xlsx", "xls"]
        )
        
        if excel_file:
            try:
                import pandas as pd
                df = pd.read_excel(excel_file)
                
                # Get the first column as URLs
                if len(df.columns) > 0:
                    urls = df.iloc[:, 0].dropna().astype(str).tolist()
                    
                    # Get product names if second column exists
                    if len(df.columns) > 1:
                        names = df.iloc[:, 1].dropna().astype(str).tolist()
                    else:
                        names = [f"product_{i+1}" for i in range(len(urls))]
                    
                    st.info(f"📊 Found {len(urls)} URLs in Excel file")
                    
                    for idx, (url, name) in enumerate(zip(urls, names)):
                        try:
                            response = requests.get(url, timeout=10)
                            response.raise_for_status()
                            img = Image.open(BytesIO(response.content)).convert("RGBA")
                            # Clean filename
                            clean_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
                            products_to_process.append((img, clean_name or f"product_{idx+1}"))
                        except Exception as e:
                            st.warning(f"⚠️ Could not load {name}: {str(e)}")
                else:
                    st.error("❌ Excel file appears to be empty")
                    
            except Exception as e:
                st.error(f"❌ Error reading Excel file: {str(e)}")
    
    else:  # Enter SKUs
        skus_input = st.text_area(
            "Enter Product SKUs (one per line):",
            height=200,
            placeholder="GE840EA6C62GANAFAMZ\nAP456EA7D89HANAFAMZ\nXY123EA4B56CANAFAMZ"
        )
        
        jumia_site_bulk = st.radio(
            "Select Jumia Site:",
            ["Jumia Kenya", "Jumia Uganda"],
            horizontal=True,
            key="bulk_jumia_site"
        )
        
        if skus_input.strip():
            skus = [sku.strip() for sku in skus_input.split('\n') if sku.strip()]
            st.info(f"📝 {len(skus)} SKUs entered")
            
            if st.button("🔍 Search All SKUs and Extract Images", use_container_width=True):
                # Determine the base URL
                if jumia_site_bulk == "Jumia Kenya":
                    base_url = "https://www.jumia.co.ke"
                else:
                    base_url = "https://www.jumia.ug"
                
                progress = st.progress(0)
                status_text = st.empty()
                
                for idx, sku in enumerate(skus):
                    status_text.text(f"Processing SKU {idx+1}/{len(skus)}: {sku}")
                    search_url = f"{base_url}/catalog/?q={sku}"
                    
                    img = search_jumia_by_sku(sku, base_url, search_url)
                    if img:
                        filename = sku
                        products_to_process.append((img, filename))
                    else:
                        st.warning(f"⚠️ Could not find image for SKU: {sku}")
                    
                    progress.progress((idx + 1) / len(skus))
                
                status_text.text(f"✅ Completed! Found {len(products_to_process)} images out of {len(skus)} SKUs")
    
    # Process button
    if products_to_process and st.button("🚀 Process All Images", use_container_width=True):
        st.info(f"Processing {len(products_to_process)} images...")
        
        # Create a progress bar
        progress_bar = st.progress(0)
        
        processed_images = []
        
        # Get tag file
        try:
            tag_filename = tag_files[tag_type]
            tag_path = get_tag_path(tag_filename)
            
            if not os.path.exists(tag_path):
                st.error(f"❌ Tag file not found: {tag_filename}")
                st.stop()
            
            tag_image = Image.open(tag_path).convert("RGBA")
            canvas_width, canvas_height = tag_image.size
            banner_height = int(canvas_height * 0.095)
            vert_tag_width = int(canvas_width * 0.18)
            available_width = canvas_width - vert_tag_width
            available_height = canvas_height - banner_height
            padding_factor = 0.74
            fit_width = int(available_width * padding_factor)
            fit_height = int(available_height * padding_factor)
            
            for idx, (product_image, filename) in enumerate(products_to_process):
                try:
                    # Process the image
                    orig_prod_width, orig_prod_height = product_image.size
                    product_aspect_ratio = orig_prod_height / orig_prod_width
                    
                    new_prod_width = fit_width
                    new_prod_height = int(new_prod_width * product_aspect_ratio)
                    
                    if new_prod_height > fit_height:
                        new_prod_height = fit_height
                        new_prod_width = int(new_prod_height / product_aspect_ratio)
                    
                    product_resized = product_image.resize((new_prod_width, new_prod_height), Image.Resampling.LANCZOS)
                    result_image = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
                    
                    prod_x = (available_width - new_prod_width) // 2
                    prod_y = (available_height - new_prod_height) // 2
                    
                    if product_resized.mode == 'RGBA':
                        result_image.paste(product_resized, (prod_x, prod_y), product_resized)
                    else:
                        result_image.paste(product_resized, (prod_x, prod_y))
                    
                    if tag_image.mode == 'RGBA':
                        result_image.paste(tag_image, (0, 0), tag_image)
                    else:
                        result_image.paste(tag_image, (0, 0))
                    
                    processed_images.append((result_image, filename))
                    
                except Exception as e:
                    st.warning(f"⚠️ Error processing {filename}: {str(e)}")
                
                # Update progress
                progress_bar.progress((idx + 1) / len(products_to_process))
            
            # Show results and download options
            if processed_images:
                st.markdown("---")
                st.success(f"✅ Successfully processed {len(processed_images)} images!")
                
                # Create a zip file with all images
                import zipfile
                zip_buffer = BytesIO()
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for img, name in processed_images:
                        img_buffer = BytesIO()
                        img.save(img_buffer, format='JPEG', quality=95)
                        zip_file.writestr(
                            f"{name}_{tag_type.lower().replace(' ', '_')}.jpg",
                            img_buffer.getvalue()
                        )
                
                zip_buffer.seek(0)
                
                st.download_button(
                    label=f"📦 Download All {len(processed_images)} Images (ZIP)",
                    data=zip_buffer,
                    file_name=f"refurbished_products_{tag_type.lower().replace(' ', '_')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                
                # Show preview of processed images
                st.markdown("### Preview")
                cols = st.columns(3)
                for idx, (img, name) in enumerate(processed_images[:9]):  # Show first 9
                    with cols[idx % 3]:
                        st.image(img, caption=name, use_container_width=True)
                        
                if len(processed_images) > 9:
                    st.info(f"Showing 9 of {len(processed_images)} processed images")
            else:
                st.error("❌ No images were successfully processed")
                
        except Exception as e:
            st.error(f"❌ Error during processing: {str(e)}")
    
    elif not products_to_process:
        st.info("👆 Please provide images to process")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
    <p>💡 Tip: The tag will automatically scale to match your product image height</p>
    </div>
    """,
    unsafe_allow_html=True
)
