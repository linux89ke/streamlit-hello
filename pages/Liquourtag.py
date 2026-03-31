import streamlit as st
from PIL import Image
import requests
from io import BytesIO
import numpy as np
import os
import re
from bs4 import BeautifulSoup
import concurrent.futures
import pandas as pd
import time

# Page config
st.set_page_config(
    page_title="Age Restriction Tag Generator",
    page_icon="🔞",
    layout="wide"
)

# Title and description
st.title("Age Restriction Tag Generator")
st.markdown("Upload a product image and add a fixed 18+ overlay!")

# Sidebar for information
st.sidebar.header("Processing Mode")
processing_mode = st.sidebar.radio(
    "Choose mode:",
    ["Single Image", "Bulk Processing"]
)

st.sidebar.markdown("---")
st.sidebar.header("Image Settings")
st.sidebar.caption("Composition uses a fixed 800x800px transparent overlay.")
st.sidebar.markdown("- **Final Canvas**: 800x800px")
st.sidebar.markdown("- **Smart Trim**: Active (Auto-crops white space)")

# Tag file definition
TAG_FILE = "NSFW-18++-Tag.png"
TARGET_CANVAS_SIZE = (800, 800)

def crop_white_space(img):
    """Smart Trim: Removes massive white borders from product images."""
    if img.mode == 'RGBA':
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img_data = np.array(bg)
    else:
        img_data = np.array(img.convert('RGB'))
        
    mask = img_data < 245
    if not mask.any():
        return img
        
    coords = np.argwhere(mask.any(axis=-1))
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    return img.crop((x0, y0, x1, y1))

@st.cache_resource
def get_driver_path():
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
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    possible_paths = ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]
    for path in possible_paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            break
    return chrome_options

def get_driver(headless=True):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        st.error("Selenium not installed.")
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

def scrape_jumia_category(category_url, max_items=20):
    """Scrapes images directly from a Jumia category grid."""
    driver = get_driver(headless=True)
    if not driver:
        return []
    
    driver.get(category_url)
    time.sleep(2)  # Allow initial load
    
    # Scroll multiple times to trigger lazy loading for up to max_items
    for _ in range(3):
        driver.execute_script("window.scrollBy(0, 1500);")
        time.sleep(1)
        
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()
    
    articles = soup.find_all('article', class_='prd')
    results = []
    
    for art in articles:
        if len(results) >= max_items:
            break
        img_tag = art.find('img', class_='img')
        if img_tag:
            name = img_tag.get('alt', 'product').strip()
            # Jumia uses data-src for lazy loaded images
            img_url = img_tag.get('data-src') or img_tag.get('src')
            if img_url and not img_url.endswith('data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'):
                clean_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
                results.append((clean_name, img_url))
                
    return results

def search_jumia_by_sku(sku, base_url, search_url):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    
    driver = get_driver(headless=True)
    if not driver: return None
    
    try:
        driver.get(search_url)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
        except TimeoutException: return None
        
        product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
        if not product_links:
            product_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='.html']")
        
        if product_links:
            product_url = product_links[0].get_attribute("href")
            driver.get(product_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
            time.sleep(1) 
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            image_url = None
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                image_url = og_image['content']
            
            if not image_url:
                for img in soup.find_all('img', limit=15):
                    src = img.get('data-src') or img.get('src')
                    if src and ('/product/' in src or '/unsafe/' in src or 'jumia.is' in src):
                        if src.startswith('//'): src = 'https:' + src
                        elif src.startswith('/'): src = base_url + src
                        image_url = src
                        break
            
            if image_url:
                headers = {'User-Agent': 'Mozilla/5.0'}
                img_response = requests.get(image_url, headers=headers, timeout=15)
                img_response.raise_for_status()
                return Image.open(BytesIO(img_response.content)).convert("RGBA")
        return None
    except Exception:
        return None
    finally:
        driver.quit()

# ----------------- SINGLE IMAGE MODE -----------------
if processing_mode == "Single Image":
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Upload Product Image")
        upload_method = st.radio("Choose upload method:", ["Upload from device", "Load from Image URL", "Load from SKU"])
        product_image = None
        
        if upload_method == "Upload from device":
            uploaded_file = st.file_uploader("Choose an image file", type=["png", "jpg", "jpeg", "webp"])
            if uploaded_file: product_image = Image.open(uploaded_file).convert("RGBA")
        elif upload_method == "Load from Image URL":
            image_url = st.text_input("Enter image URL:")
            if image_url:
                try:
                    product_image = Image.open(BytesIO(requests.get(image_url).content)).convert("RGBA")
                    st.success("Loaded successfully!")
                except: st.error("Error loading image.")
        else:
            sku_input = st.text_input("Enter Product SKU:")
            jumia_site = st.radio("Select Jumia Site:", ["Jumia Kenya", "Jumia Uganda"], horizontal=True)
            if sku_input and st.button("Search and Extract", use_container_width=True):
                with st.spinner("Searching..."):
                    base_url = "https://www.jumia.co.ke" if jumia_site == "Jumia Kenya" else "https://www.jumia.ug"
                    search_url = f"{base_url}/catalog/?q={sku_input}"
                    product_image = search_jumia_by_sku(sku_input, base_url, search_url)
                    if product_image: st.success("Found!")
                    else: st.error("Not found.")

    with col2:
        st.subheader("Preview (Fixed Composition: 800x800px)")
        if product_image is not None:
            tag_path = TAG_FILE if os.path.exists(TAG_FILE) else os.path.join(os.path.dirname(__file__), TAG_FILE)
            if not os.path.exists(tag_path):
                st.error(f"Overlay file not found: {TAG_FILE}")
                st.stop()
            
            tag_image = Image.open(tag_path).convert("RGBA")
            if tag_image.size != TARGET_CANVAS_SIZE:
                tag_image = tag_image.resize(TARGET_CANVAS_SIZE, Image.Resampling.LANCZOS)
            
            result_image = Image.new("RGB", TARGET_CANVAS_SIZE, (255, 255, 255))
            product_image = crop_white_space(product_image)
            product_image.thumbnail((750, 750), Image.Resampling.LANCZOS)
            
            paste_x = (TARGET_CANVAS_SIZE[0] - product_image.width) // 2
            paste_y = (TARGET_CANVAS_SIZE[1] - product_image.height) // 2
            
            if product_image.mode == 'RGBA': result_image.paste(product_image, (paste_x, paste_y), product_image)
            else: result_image.paste(product_image, (paste_x, paste_y))
            
            result_image.paste(tag_image, (0, 0), tag_image)
            st.image(result_image, use_container_width=True)
            
            buf = BytesIO()
            result_image.save(buf, format="JPEG", quality=95)
            st.download_button("Download Image", buf.getvalue(), "age_restricted_800x800.jpg", "image/jpeg", use_container_width=True)

# ----------------- BULK PROCESSING MODE -----------------
else:
    st.subheader("Bulk Processing (to Fixed 800x800px)")
    bulk_method = st.radio(
        "Choose bulk input method:",
        ["Upload multiple images", "Enter URLs manually", "Upload Smart Excel", "Enter SKUs", "Jumia Category URL (Auto-Scrape)"]
    )
    
    products_to_process = []
    
    if bulk_method == "Upload multiple images":
        uploaded_files = st.file_uploader("Choose multiple files", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
        if uploaded_files:
            for f in uploaded_files:
                products_to_process.append((Image.open(f).convert("RGBA"), f.name.rsplit('.', 1)[0]))
                
    elif bulk_method == "Enter URLs manually":
        urls_input = st.text_area("Enter image URLs (one per line):")
        if urls_input.strip():
            urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
            for idx, url in enumerate(urls):
                try:
                    img = Image.open(BytesIO(requests.get(url, timeout=10).content)).convert("RGBA")
                    products_to_process.append((img, f"image_{idx+1}"))
                except: pass

    elif bulk_method == "Upload Smart Excel":
        st.caption("Auto-detects columns named 'URL', 'Link', 'SKU', and 'Name'.")
        excel_file = st.file_uploader("Upload Excel", type=["xlsx", "xls"])
        if excel_file:
            df = pd.read_excel(excel_file)
            
            url_col, sku_col, name_col = None, None, None
            for col in df.columns:
                c_low = str(col).lower()
                if 'url' in c_low or 'link' in c_low or 'image' in c_low: url_col = col
                elif 'sku' in c_low: sku_col = col
                elif 'name' in c_low or 'title' in c_low: name_col = col
            
            # Fallbacks
            if not url_col and not sku_col and len(df.columns) > 0: url_col = df.columns[0]
            if not name_col and len(df.columns) > 1: name_col = df.columns[1]
            
            progress = st.progress(0)
            status = st.empty()
            
            for idx, row in df.iterrows():
                name = str(row[name_col]) if name_col else f"product_{idx+1}"
                clean_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
                
                img = None
                if url_col and pd.notna(row[url_col]):
                    try: img = Image.open(BytesIO(requests.get(str(row[url_col]), timeout=10).content)).convert("RGBA")
                    except: pass
                elif sku_col and pd.notna(row[sku_col]):
                    sku = str(row[sku_col])
                    img = search_jumia_by_sku(sku, "https://www.jumia.co.ke", f"https://www.jumia.co.ke/catalog/?q={sku}")
                
                if img: products_to_process.append((img, clean_name))
                progress.progress((idx + 1) / len(df))
                status.text(f"Processed row {idx+1}/{len(df)}")
                
    elif bulk_method == "Enter SKUs":
        skus_input = st.text_area("Enter SKUs:")
        site = st.radio("Site:", ["Jumia Kenya", "Jumia Uganda"], horizontal=True)
        if skus_input.strip() and st.button("Extract SKUs"):
            skus = [s.strip() for s in skus_input.split('\n') if s.strip()]
            base_url = "https://www.jumia.co.ke" if site == "Jumia Kenya" else "https://www.jumia.ug"
            
            prog = st.progress(0)
            stat = st.empty()
            
            def fetch(sku):
                return sku, search_jumia_by_sku(sku, base_url, f"{base_url}/catalog/?q={sku}")
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as x:
                futs = {x.submit(fetch, s): s for s in skus}
                for i, f in enumerate(concurrent.futures.as_completed(futs)):
                    sku, img = f.result()
                    if img: products_to_process.append((img, sku))
                    prog.progress((i+1)/len(skus))
                    stat.text(f"Scraped {i+1}/{len(skus)} SKUs")

    elif bulk_method == "Jumia Category URL (Auto-Scrape)":
        cat_url = st.text_input("Paste Jumia Category URL (e.g., https://www.jumia.co.ke/beers/)")
        max_limit = st.slider("Max items to scrape", 10, 100, 30, step=10)
        
        if cat_url and st.button("Scrape Category"):
            with st.spinner("Extracting category grid..."):
                scraped_data = scrape_jumia_category(cat_url, max_limit)
                
            if not scraped_data:
                st.error("No images found. Check URL.")
            else:
                prog = st.progress(0)
                stat = st.empty()
                def fetch_img(name, url):
                    try: return name, Image.open(BytesIO(requests.get(url, timeout=10).content)).convert("RGBA")
                    except: return name, None
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as x:
                    futs = [x.submit(fetch_img, n, u) for n, u in scraped_data]
                    for i, f in enumerate(concurrent.futures.as_completed(futs)):
                        n, img = f.result()
                        if img: products_to_process.append((img, n))
                        prog.progress((i+1)/len(scraped_data))
                        stat.text(f"Downloaded {i+1}/{len(scraped_data)} category images")

    # ----- PROCESSING AND LIVE PREVIEW -----
    if products_to_process:
        st.markdown("---")
        st.subheader("Process & Preview")
        
        # Batch Rename Pattern
        rename_pattern = st.text_input("Renaming Pattern (Use {original} for original name/SKU):", value="{original}_18plus")
        
        if st.button("Generate Composites", type="primary", use_container_width=True):
            tag_path = TAG_FILE if os.path.exists(TAG_FILE) else os.path.join(os.path.dirname(__file__), TAG_FILE)
            if not os.path.exists(tag_path):
                st.error(f"Overlay file not found: {TAG_FILE}")
                st.stop()
                
            tag_image = Image.open(tag_path).convert("RGBA")
            if tag_image.size != TARGET_CANVAS_SIZE:
                tag_image = tag_image.resize(TARGET_CANVAS_SIZE, Image.Resampling.LANCZOS)

            processed_images = []
            
            # Setup Live Preview Grid
            st.markdown("### Live Preview")
            preview_container = st.container()
            cols_per_row = 4
            
            prog = st.progress(0)
            
            for idx, (img, fname) in enumerate(products_to_process):
                # Process
                res = Image.new("RGB", TARGET_CANVAS_SIZE, (255, 255, 255))
                img = crop_white_space(img)
                img.thumbnail((750, 750), Image.Resampling.LANCZOS)
                
                px = (TARGET_CANVAS_SIZE[0] - img.width) // 2
                py = (TARGET_CANVAS_SIZE[1] - img.height) // 2
                
                if img.mode == 'RGBA': res.paste(img, (px, py), img)
                else: res.paste(img, (px, py))
                
                res.paste(tag_image, (0, 0), tag_image)
                
                final_name = rename_pattern.replace("{original}", fname)
                processed_images.append((res, final_name))
                
                # Live Preview
                if idx % cols_per_row == 0:
                    current_cols = preview_container.columns(cols_per_row)
                current_cols[idx % cols_per_row].image(res, caption=final_name, use_container_width=True)
                
                prog.progress((idx + 1) / len(products_to_process))
                
            # Zip and Download
            import zipfile
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for img, name in processed_images:
                    img_buf = BytesIO()
                    img.save(img_buf, format='JPEG', quality=95)
                    zf.writestr(f"{name}.jpg", img_buf.getvalue())
            
            st.success("Complete!")
            st.download_button(
                label=f"Download {len(processed_images)} Images (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="bulk_age_restricted_images.zip",
                mime="application/zip",
                use_container_width=True
            )
