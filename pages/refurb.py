import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
import pandas as pd
import re
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from PIL import Image
from io import BytesIO
import numpy as np

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Refurbished Product Analyzer", layout="wide")
st.title(":material/sync: Refurbished Product Data Extractor")

# --- SIDEBAR ---
with st.sidebar:
    st.header(":material/settings: Settings")
    region_choice = st.selectbox("Select Region:", ("Region 1 (KE)", "Region 2 (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    st.markdown("---")
    show_browser = st.checkbox("Show Browser (Debug Mode)", value=False)
    max_workers = st.slider("Parallel Workers:", 1, 3, 2, help="More workers = faster but may cause timeouts")
    timeout_seconds = st.slider("Page Timeout (seconds):", 10, 30, 20)
    check_images = st.checkbox("Analyze Product Images for Red Badges", value=True, 
                               help="Downloads and analyzes images to detect refurbished tags")
    st.info(f"Using {max_workers} workers with {timeout_seconds}s timeout", icon=":material/bolt:")

# --- 1. DRIVER SETUP ---
@st.cache_resource
def get_driver_path():
    """Cache driver installation."""
    try:
        return ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    except Exception:
        try:
            return ChromeDriverManager().install()
        except Exception as e:
            st.error(f"Could not install driver: {e}", icon=":material/error:")
            return None

def get_chrome_options(headless=True):
    """Configure Chrome options for stability."""
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

def get_driver(headless=True, timeout=20):
    """Create WebDriver with comprehensive error handling."""
    chrome_options = get_chrome_options(headless)
    driver = None
    
    try:
        driver_path = get_driver_path()
        if not driver_path:
            return None
            
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
            driver.set_page_load_timeout(timeout)
            driver.implicitly_wait(5)
        except Exception:
            pass
    
    return driver

# --- 2. IMAGE ANALYSIS & HASHING ---
def get_dhash(img):
    """Calculate Difference Hash (dHash) for an image to allow perceptual comparison."""
    try:
        if hasattr(Image, 'Resampling'):
            resample_mode = Image.Resampling.LANCZOS
        else:
            resample_mode = Image.LANCZOS
        img = img.convert('L').resize((9, 8), resample_mode)
        pixels = np.array(img)
        diff = pixels[:, 1:] > pixels[:, :-1]
        return diff.flatten()
    except Exception:
        return None

@st.cache_data
def get_target_promo_hash():
    """Cache the hash of the target promotional image."""
    target_url = "https://ke.jumia.is/unsafe/fit-in/680x680/filters:fill(white)/product/21/3620523/3.jpg?0053"
    try:
        response = requests.get(target_url, timeout=10)
        img = Image.open(BytesIO(response.content))
        return get_dhash(img)
    except Exception:
        return None

def has_red_badge(image_url):
    """Analyze product image to detect red refurbished badges/tags."""
    try:
        response = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(response.content))
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        img = img.resize((300, 300))
        img_array = np.array(img)
        
        red = img_array[:, :, 0].astype(float)
        green = img_array[:, :, 1].astype(float)
        blue = img_array[:, :, 2].astype(float)
        
        red_mask = (red > 180) & (green < 100) & (blue < 100)
        red_pixel_ratio = np.sum(red_mask) / (img_array.shape[0] * img_array.shape[1])
        
        if red_pixel_ratio > 0.03:
            return "YES (Red Badge Detected)"
        else:
            return "NO"
            
    except Exception as e:
        return f"ERROR ({str(e)[:20]})"

# --- 3. WARRANTY EXTRACTION ---
def extract_warranty_info(soup, product_name):
    """Extract warranty information from multiple sources."""
    warranty_data = {
        'has_warranty': 'NO',
        'warranty_duration': 'N/A',
        'warranty_source': 'None',
        'warranty_details': '',
        'warranty_address': 'N/A'
    }
    
    warranty_patterns = [
        r'(\d+)\s*(?:months?|month|mnths?|mths?)\s*(?:warranty|wrty|wrnty)',
        r'(\d+)\s*(?:year|yr|years|yrs)\s*(?:warranty|wrty|wrnty)',
        r'warranty[:\s]*(\d+)\s*(?:months?|years?)',
    ]
    
    warranty_heading = soup.find(['h3', 'h4', 'div', 'dt'], string=re.compile(r'^\s*Warranty\s*$', re.I))
    if warranty_heading:
        warranty_value = warranty_heading.find_next(['div', 'dd', 'p'])
        if warranty_value:
            warranty_text = warranty_value.get_text().strip()
            
            if warranty_text and warranty_text.lower() not in ['n/a', 'na', 'none', '']:
                duration_found = False
                for pattern in warranty_patterns:
                    match = re.search(pattern, warranty_text, re.IGNORECASE)
                    if match:
                        duration = match.group(1)
                        unit = 'months' if 'month' in match.group(0).lower() else 'years'
                        warranty_data['has_warranty'] = 'YES'
                        warranty_data['warranty_duration'] = f"{duration} {unit}"
                        warranty_data['warranty_source'] = 'Warranty Section'
                        warranty_data['warranty_details'] = warranty_text[:100]
                        duration_found = True
                        break
                
                if not duration_found:
                    simple_match = re.search(r'(\d+)\s*(month|year)', warranty_text, re.IGNORECASE)
                    if simple_match:
                        warranty_data['has_warranty'] = 'YES'
                        warranty_data['warranty_duration'] = warranty_text.strip()
                        warranty_data['warranty_source'] = 'Warranty Section'
    
    if warranty_data['has_warranty'] == 'NO':
        for pattern in warranty_patterns:
            match = re.search(pattern, product_name, re.IGNORECASE)
            if match:
                duration = match.group(1)
                unit = 'months' if 'month' in match.group(0).lower() else 'years'
                warranty_data['has_warranty'] = 'YES'
                warranty_data['warranty_duration'] = f"{duration} {unit}"
                warranty_data['warranty_source'] = 'Product Name'
                warranty_data['warranty_details'] = match.group(0)
                break
    
    warranty_addr_label = soup.find(string=re.compile(r'Warranty\s+Address', re.I))
    if warranty_addr_label:
        addr_element = warranty_addr_label.find_next(['dd', 'p', 'div'])
        if addr_element:
            addr_text = addr_element.get_text().strip()
            addr_text = re.sub(r'<[^>]+>', '', addr_text).strip()
            if addr_text and len(addr_text) > 10:
                warranty_data['warranty_address'] = addr_text
    
    if warranty_data['has_warranty'] == 'NO' and not warranty_heading:
        spec_rows = soup.find_all(['tr', 'div', 'li'], class_=re.compile(r'spec|detail|attribute|row'))
        for row in spec_rows:
            text = row.get_text()
            if 'warranty' in text.lower():
                for pattern in warranty_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        duration = match.group(1)
                        unit = 'months' if 'month' in match.group(0).lower() else 'years'
                        warranty_data['has_warranty'] = 'YES'
                        warranty_data['warranty_duration'] = f"{duration} {unit}"
                        warranty_data['warranty_source'] = 'Specifications'
                        warranty_data['warranty_details'] = text.strip()[:100]
                        break
                if warranty_data['has_warranty'] == 'YES':
                    break
    
    return warranty_data

# --- 4. REFURBISHED STATUS DETECTION ---
def detect_refurbished_status(soup, product_name):
    """Detect if product is refurbished from multiple indicators."""
    refurb_data = {
        'is_refurbished': 'NO',
        'refurb_indicators': [],
        'has_refurb_tag': 'NO'
    }
    
    refurb_keywords = ['refurbished', 'renewed', 'refurb', 'recon', 'reconditioned', 
                       'ex-uk', 'ex uk', 'pre-owned', 'certified', 'restored']

    search_scope = soup
    h1 = soup.find('h1')
    if h1:
        possible_container = h1.find_parent('div', class_=re.compile(r'col10|-pvs|-p'))
        if possible_container:
            search_scope = possible_container
        else:
            search_scope = h1.parent.parent

    refu_badge = search_scope.find('a', href=re.compile(r'/all-products/\?tag=REFU', re.I))
    if refu_badge:
        refurb_data['is_refurbished'] = 'YES'
        refurb_data['refurb_indicators'].append('REFU tag badge present')
        refurb_data['has_refurb_tag'] = 'YES'
    
    refu_img = search_scope.find('img', attrs={'alt': re.compile(r'^REFU$', re.I)})
    if refu_img:
        parent = refu_img.parent
        if parent and parent.name == 'a' and 'tag=REFU' in parent.get('href', ''):
            if 'REFU tag badge present' not in refurb_data['refurb_indicators']:
                refurb_data['is_refurbished'] = 'YES'
                refurb_data['refurb_indicators'].append('REFU badge image')
                refurb_data['has_refurb_tag'] = 'YES'
    
    breadcrumbs = soup.find_all(['a', 'span'], class_=re.compile(r'breadcrumb|brcb'))
    for crumb in breadcrumbs:
        crumb_text = crumb.get_text().lower()
        if 'renewed' in crumb_text:
            refurb_data['is_refurbished'] = 'YES'
            refurb_data['refurb_indicators'].append('Breadcrumb contains "Renewed"')
            break
    
    product_name_lower = product_name.lower()
    for keyword in refurb_keywords:
        if keyword in product_name_lower:
            refurb_data['is_refurbished'] = 'YES'
            indicator = f'Title contains "{keyword}"'
            if indicator not in refurb_data['refurb_indicators']:
                refurb_data['refurb_indicators'].append(indicator)
    
    badge_searches = [
        search_scope.find(['span', 'div', 'badge'], class_=re.compile(r'refurb|renewed', re.I)),
        search_scope.find(['span', 'div'], string=re.compile(r'REFURBISHED|RENEWED', re.I)),
        search_scope.find(['img'], attrs={'alt': re.compile(r'refurb|renewed', re.I)})
    ]
    
    for badge in badge_searches:
        if badge:
            refurb_data['is_refurbished'] = 'YES'
            if 'Refurbished badge present' not in refurb_data['refurb_indicators']:
                refurb_data['refurb_indicators'].append('Refurbished badge present')
            break
    
    condition_patterns = [
        r'condition[:\s]*(renewed|refurbished|excellent|good|like new|grade [a-c])',
        r'(renewed|refurbished)[,\s]*(no scratches|excellent|good condition|like new)',
        r'product condition[:\s]*([^\n]+)',
    ]
    
    page_text = search_scope.get_text()[:3000] if search_scope != soup else soup.get_text()[:3000]
    
    for pattern in condition_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            if refurb_data['is_refurbished'] == 'NO' and any(kw in match.group(0).lower() for kw in refurb_keywords):
                refurb_data['is_refurbished'] = 'YES'
            if 'Condition statement found' not in refurb_data['refurb_indicators']:
                refurb_data['refurb_indicators'].append('Condition statement found')
            break
    
    return refurb_data

# --- 5. ENHANCED SELLER EXTRACTION ---
def extract_seller_info(soup):
    """Extract only seller name."""
    seller_data = {
        'seller_name': 'N/A'
    }
    
    seller_section = soup.find(['h2', 'h3', 'div', 'p'], string=re.compile(r'Seller\s+Information', re.I))
    
    if not seller_section:
        seller_section = soup.find(['div', 'section'], class_=re.compile(r'seller-info|seller-box', re.I))
    
    if seller_section:
        container = seller_section.find_parent('div') or seller_section.parent
        if container:
            name_element = container.find(['p', 'div'], class_=re.compile(r'-pbs|-m'))
            
            if name_element and len(name_element.get_text().strip()) > 1:
                seller_data['seller_name'] = name_element.get_text().strip()
            else:
                candidates = container.find_all(['a', 'p', 'b'])
                for c in candidates:
                    text = c.get_text().strip()
                    if not text or any(x in text.lower() for x in ['follow', 'score', 'seller', 'information', '%', 'rating']):
                        continue
                    if re.search(r'\d+%', text): 
                        continue
                        
                    seller_data['seller_name'] = text
                    break
    
    return seller_data

# --- 5b. CATEGORY URL EXTRACTION ---
def extract_category_links(category_url, headless=True, timeout=20):
    """Visits a Jumia catalog/category URL and extracts all product links."""
    driver = get_driver(headless, timeout)
    if not driver:
        return []
    
    extracted_urls = set()
    try:
        driver.get(category_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a.core"))
        )
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        
        product_elements = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
        for elem in product_elements:
            href = elem.get_attribute("href")
            if href and "/product/" in href or ".html" in href:
                extracted_urls.add(href)
                
    except TimeoutException:
        st.error(f"Timeout while trying to load the category URL: {category_url}", icon=":material/timer:")
    except Exception as e:
        st.error(f"Error extracting links from category: {e}", icon=":material/error:")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
                
    return list(extracted_urls)

# --- 6. INPUT PROCESSING ---
def process_inputs(text_input, file_input, default_domain):
    """Process inputs efficiently."""
    raw_items = set()
    
    if text_input:
        items = re.split(r'[\n,]', text_input)
        raw_items.update(i.strip() for i in items if i.strip())
    
    if file_input:
        try:
            df = pd.read_excel(file_input, header=None) if file_input.name.endswith('.xlsx') \
                 else pd.read_csv(file_input, header=None)
            
            raw_items.update(
                str(cell).strip() 
                for cell in df.values.flatten() 
                if str(cell).strip() and str(cell).lower() != 'nan'
            )
        except Exception as e:
            st.error(f"Error reading file: {e}", icon=":material/error:")

    final_targets = []
    for item in raw_items:
        clean_val = item.replace("SKU:", "").strip()
        
        if "http" in clean_val or "www." in clean_val:
            if not clean_val.startswith("http"):
                clean_val = "https://" + clean_val
            final_targets.append({"type": "url", "value": clean_val})
        elif len(clean_val) > 3:
            search_url = f"https://www.{default_domain}/catalog/?q={clean_val}"
            final_targets.append({"type": "sku", "value": search_url, "original_sku": clean_val})
    
    return final_targets

def clean_jumia_sku(raw_sku):
    """Cleans Jumia SKUs by removing trailing variation characters."""
    if not raw_sku or raw_sku == "N/A":
        return "N/A"
    
    match = re.search(r'([A-Z0-9]+NAFAM[A-Z])', raw_sku)
    if match:
        return match.group(1)
        
    return raw_sku.strip()

# --- 7. ENHANCED SCRAPING FUNCTION ---
def extract_product_data_enhanced(soup, data, is_sku_search, target, check_images=True):
    """Extract comprehensive product data with refurbished analysis."""
    
    # 1. Product Name
    h1 = soup.find('h1')
    product_name = h1.text.strip() if h1 else "N/A"
    data['Product Name'] = product_name

    # 2. Brand
    brand_label = soup.find(string=re.compile(r"Brand:\s*", re.I))
    if brand_label and brand_label.parent:
        brand_link = brand_label.parent.find('a')
        if brand_link:
            data['Brand'] = brand_link.text.strip()
        else:
            raw_text = brand_label.parent.get_text().replace('Brand:', '').split('|')[0].strip()
            data['Brand'] = raw_text
    
    if data['Brand'] in ["N/A", ""]:
        brand_crumb = soup.find('a', href=re.compile(r'/[\w\-]+/$'))
        if brand_crumb:
            data['Brand'] = brand_crumb.get_text().strip()

    if data['Brand'] and ("window.fbq" in data['Brand'] or "undefined" in data['Brand'] or "function(" in data['Brand']):
        data['Brand'] = "Renewed"
    
    if data['Brand'] in ["N/A", ""] or data['Brand'].lower() in ["generic", "renewed", "refurbished"]:
        first_word = product_name.split()[0] if product_name != "N/A" else "N/A"
        if first_word.lower() == "renewed":
             data['Brand'] = "Renewed"
        elif len(product_name.split()) > 1:
            data['Brand'] = first_word
            
    if data['Brand'].lower() == 'refurbished':
        data['Brand'] = "Renewed"

    # 3. Seller Information
    seller_info = extract_seller_info(soup)
    data['Seller Name'] = seller_info['seller_name']

    # 4. Category
    breadcrumbs = soup.select('.osh-breadcrumb a, .brcbs a, [class*="breadcrumb"] a')
    cats = []
    for b in breadcrumbs:
        text = b.text.strip()
        if text and len(text) > 0:
            cats.append(text)
    data['Category'] = ' > '.join(cats) if cats else "N/A"

    # 5. SKU
    sku_found = "N/A"
    sku_element = soup.find(attrs={'data-sku': True})
    if sku_element:
        sku_found = sku_element['data-sku']
    else:
        text_content = soup.get_text()
        sku_match = re.search(r'SKU[:\s]*([A-Z0-9]+NAFAM[A-Z])', text_content)
        if sku_match:
            sku_found = sku_match.group(1)
        else:
            sku_match_generic = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', text_content)
            if sku_match_generic:
                sku_found = sku_match_generic.group(1)
            elif is_sku_search:
                sku_found = target.get('original_sku', 'N/A')

    data['SKU'] = clean_jumia_sku(sku_found)

    # 6. PRODUCT IMAGES EXTRACTION (Main Gallery)
    data['Image URLs'] = []
    image_url = None
    
    gallery_container = soup.find('div', id='imgs') or soup.find('div', class_=re.compile(r'\bsldr\b|\bgallery\b|-pas', re.I))
    search_scope = gallery_container if gallery_container else soup

    for img in search_scope.find_all('img'):
        src = (img.get('data-src') or img.get('src') or '').strip()
        
        if src and '/product/' in src and not src.startswith('data:'):
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = 'https://www.jumia.co.ke' + src
            
            base_match = re.search(r'(/product/[a-z0-9_/-]+\.(?:jpg|jpeg|png|webp))', src, re.IGNORECASE)
            base_path = base_match.group(1) if base_match else src
            
            if not any(base_path in existing_url for existing_url in data['Image URLs']):
                data['Image URLs'].append(src)
                if not image_url:
                    image_url = src
                    
        if not gallery_container and len(data['Image URLs']) >= 8:
            break
            
    data['Primary Image URL'] = image_url if image_url else "N/A"
    data['Total Product Images'] = len(data['Image URLs'])

    # 6B. TARGET IMAGE HASH COMPARISON (Check last image in gallery)
    data['Grading last image'] = 'NO'
    if data['Image URLs']:
        target_hash = get_target_promo_hash()
        if target_hash is not None:
            last_image_url = data['Image URLs'][-1]
            try:
                resp = requests.get(last_image_url, timeout=10)
                last_img = Image.open(BytesIO(resp.content))
                last_hash = get_dhash(last_img)
                
                if last_hash is not None:
                    hamming_dist = np.count_nonzero(target_hash != last_hash)
                    if hamming_dist <= 12:
                        data['Grading last image'] = 'YES'
            except Exception:
                pass

    # 7. Refurbished Status
    refurb_status = detect_refurbished_status(soup, product_name)
    data['Is Refurbished'] = refurb_status['is_refurbished']
    data['Has refurb tag'] = refurb_status['has_refurb_tag'] 
    data['Refurbished Indicators'] = ', '.join(refurb_status['refurb_indicators']) if refurb_status['refurb_indicators'] else 'None'

    if data['Brand'] == "Renewed":
        data['Is Refurbished'] = "YES"

    # 8. Warranty
    warranty_info = extract_warranty_info(soup, product_name)
    data['Has Warranty'] = warranty_info['has_warranty']
    data['Warranty Duration'] = warranty_info['warranty_duration']
    data['Warranty Source'] = warranty_info['warranty_source']
    data['Warranty Address'] = warranty_info['warranty_address']

    # 9. Image Badge
    if check_images and image_url and image_url != "N/A":
        data['grading tag'] = has_red_badge(image_url) 
    else:
        data['grading tag'] = 'Not Checked'

    # 10. Express & Price
    express_badge = soup.find(['svg', 'img', 'span'], attrs={'aria-label': re.compile(r'Jumia Express', re.I)})
    if express_badge:
        data['Express'] = "Yes"
    
    price_tag = soup.find('span', class_=re.compile(r'price|prc|-b'))
    if not price_tag:
        price_tag = soup.find(['div', 'span'], string=re.compile(r'KSh\s*[\d,]+'))
    
    if price_tag:
        price_text = price_tag.get_text().strip()
        price_match = re.search(r'KSh\s*([\d,]+)', price_text)
        if price_match:
            data['Price'] = 'KSh ' + price_match.group(1)
        else:
            data['Price'] = price_text

    # 11. Product Rating
    rating_elem = soup.find(['span', 'div'], class_=re.compile(r'rating|stars'))
    if rating_elem:
        rating_text = rating_elem.get_text()
        rating_match = re.search(r'([\d.]+)\s*out of\s*5', rating_text)
        if rating_match:
            data['Product Rating'] = rating_match.group(1) + '/5'
    
    # 12. Infographics
    infographic_count = 0
    seen_info_imgs = set()

    desc_containers = soup.find_all('div', class_=re.compile(r'\bmarkup\b|product-desc|-mhm', re.I))
    
    if not desc_containers:
        for tag in soup.find_all(['h2', 'h3', 'div']):
            if re.search(r'Product\s+details?|Description', tag.get_text(), re.I):
                candidate = tag.find_next_sibling('div') or tag.find_next('div')
                if candidate:
                    desc_containers.append(candidate)
                    break

    for container in desc_containers:
        for img in container.find_all('img'):
            src = (img.get('data-src') or img.get('src') or '').strip()
            if not src or src.startswith('data:') or len(src) < 15:
                continue
            seen_info_imgs.add(src)

    if not seen_info_imgs:
        for img in soup.find_all('img'):
            src = (img.get('data-src') or img.get('src') or '').strip()
            if '/cms/external/' in src or '/cms/' in src:
                if not src.endswith('.svg') and src not in seen_info_imgs:
                    seen_info_imgs.add(src)

    infographic_count = len(seen_info_imgs)
    data['Infographic Image Count'] = infographic_count
    data['Has info-graphics'] = 'YES' if infographic_count > 0 else 'NO'

    return data

def scrape_item_enhanced(target, headless=True, timeout=20, check_images=True):
    """Scrape a single item with enhanced refurbished analysis."""
    driver = None
    url = target['value']
    is_sku_search = target['type'] == 'sku'
    
    data = {
        'Input Source': target.get('original_sku', url),
        'Product Name': 'N/A',
        'Brand': 'N/A',
        'Seller Name': 'N/A',
        'Category': 'N/A',
        'SKU': 'N/A',
        'Is Refurbished': 'NO',
        'Has refurb tag': 'NO', 
        'Refurbished Indicators': 'None',
        'Has Warranty': 'NO',
        'Warranty Duration': 'N/A',
        'Warranty Source': 'None',
        'Warranty Address': 'N/A',
        'grading tag': 'Not Checked',
        'Primary Image URL': 'N/A',
        'Image URLs': [],
        'Total Product Images': 0,
        'Grading last image': 'NO',
        'Price': 'N/A',
        'Product Rating': 'N/A',
        'Express': 'No',
        'Has info-graphics': 'NO',
        'Infographic Image Count': 0
    }

    try:
        driver = get_driver(headless, timeout)
        if not driver:
            data['Product Name'] = 'SYSTEM_ERROR'
            return data

        try:
            driver.get(url)
        except TimeoutException:
            data['Product Name'] = 'TIMEOUT'
            return data
        except WebDriverException:
            data['Product Name'] = 'CONNECTION_ERROR'
            return data
        
        if is_sku_search:
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1"))
                )
                if "There are no results for" in driver.page_source:
                    data['Product Name'] = "SKU_NOT_FOUND"
                    return data
                
                product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                if product_links:
                    try:
                        driver.get(product_links[0].get_attribute("href"))
                    except TimeoutException:
                        data['Product Name'] = 'TIMEOUT'
                        return data
            except TimeoutException:
                data['Product Name'] = 'TIMEOUT'
                return data
            except Exception:
                pass

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "h1"))
            )
        except TimeoutException:
            data['Product Name'] = 'TIMEOUT'
            return data
        
        try:
            for scroll_step in [800, 1600, 2400, 3200]:
                driver.execute_script(f"window.scrollTo(0, {scroll_step});")
                time.sleep(0.5)
        except Exception:
            pass
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = extract_product_data_enhanced(soup, data, is_sku_search, target, check_images)

    except TimeoutException:
        data['Product Name'] = "TIMEOUT"
    except WebDriverException:
        data['Product Name'] = "CONNECTION_ERROR"
    except Exception as e:
        data['Product Name'] = "ERROR_FETCHING"
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    
    return data

# --- 8. PARALLEL PROCESSING ---
def scrape_items_parallel(targets, max_workers, headless=True, timeout=20, check_images=True):
    """Scrape multiple items in parallel."""
    results = []
    failed = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_target = {
            executor.submit(scrape_item_enhanced, target, headless, timeout, check_images): target 
            for target in targets
        }
        
        for future in as_completed(future_to_target):
            target = future_to_target[future]
            try:
                result = future.result()
                if result['Product Name'] in ["SYSTEM_ERROR", "TIMEOUT", "CONNECTION_ERROR"]:
                    failed.append({
                        'input': target.get('original_sku', target['value']),
                        'error': result['Product Name']
                    })
                elif result['Product Name'] != "SKU_NOT_FOUND":
                    results.append(result)
            except Exception as e:
                failed.append({
                    'input': target.get('original_sku', target['value']),
                    'error': str(e)
                })
    
    return results, failed

# --- MAIN APP ---
if 'scraped_results' not in st.session_state:
    st.session_state['scraped_results'] = []
if 'failed_items' not in st.session_state:
    st.session_state['failed_items'] = []

st.markdown("### :material/input: Input Data")
col_txt, col_upl = st.columns(2)
with col_txt:
    text_in = st.text_area("Paste SKUs/Links:", height=100, 
                           placeholder="Enter SKUs or URLs, one per line\nExample: SA948MP5EER52NAFAMZ")
with col_upl:
    file_in = st.file_uploader("Upload Excel/CSV with SKUs:", type=['xlsx', 'csv'])

category_url_in = st.text_input(":material/language: Search URL (Extracts all products on the page):", 
                                placeholder="https://www.jumia.co.ke/smartphones/")

st.markdown("---")

if st.button("Start Refurbished Product Analysis", type="primary", icon=":material/play_arrow:"):
    targets = process_inputs(text_in, file_in, domain)
    
    if category_url_in:
        with st.spinner("Extracting product links from category page..."):
            cat_links = extract_category_links(
                category_url_in, 
                headless=not show_browser, 
                timeout=timeout_seconds
            )
            for link in cat_links:
                targets.append({"type": "url", "value": link, "original_sku": link})
            
            if cat_links:
                st.success(f"Extracted {len(cat_links)} products from the category URL.", icon=":material/check_circle:")
            else:
                st.warning("Could not find any product links on the provided category URL.", icon=":material/warning:")
    
    if not targets:
        st.warning("No valid data found. Please enter SKUs, URLs, or a Category URL.", icon=":material/warning:")
    else:
        st.session_state['scraped_results'] = []
        st.session_state['failed_items'] = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        progress_details = st.empty()
        current_item_display = st.empty()
        
        status_text.text(f"Analyzing {len(targets)} products for refurbished attributes...")
        start_time = time.time()
        
        batch_size = max_workers * 2
        all_results = []
        all_failed = []
        processed_count = 0
        
        for i in range(0, len(targets), batch_size):
            batch = targets[i:i + batch_size]
            
            batch_num = (i // batch_size) + 1
            total_batches = (len(targets) + batch_size - 1) // batch_size
            progress_details.info(
                f"Processing batch {batch_num}/{total_batches} "
                f"({len(batch)} items)", icon=":material/inventory_2:"
            )
            
            batch_results, batch_failed = scrape_items_parallel(
                batch, max_workers, not show_browser, timeout_seconds, check_images
            )
            
            all_results.extend(batch_results)
            all_failed.extend(batch_failed)
            processed_count += len(batch)
            
            progress = min(processed_count / len(targets), 1.0)
            progress_bar.progress(progress)
            
            elapsed = time.time() - start_time
            avg_time = elapsed / processed_count if processed_count > 0 else 0
            remaining = (len(targets) - processed_count) * avg_time
            
            status_text.text(
                f"Processed {processed_count}/{len(targets)} items "
                f"({processed_count/elapsed:.1f} items/sec) | "
                f"Est. remaining: {remaining:.0f}s"
            )
            
            if batch_results:
                last_item = batch_results[-1]
                with current_item_display.container():
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        if last_item.get('Primary Image URL') and last_item['Primary Image URL'] != 'N/A':
                            try:
                                st.image(last_item['Primary Image URL'], width=150)
                            except:
                                st.caption("Image unavailable")
                    with col2:
                        st.caption(f"**Last processed:** {last_item.get('Product Name', 'N/A')[:60]}...")
                        st.caption(f"Images: {last_item.get('Total Product Images', 0)} | Refurb: {last_item.get('Is Refurbished', 'NO')} | Grading Img: {last_item.get('Grading last image', 'NO')}")
        
        elapsed = time.time() - start_time
        st.session_state['scraped_results'] = all_results
        st.session_state['failed_items'] = all_failed
        
        success_count = len(all_results)
        failed_count = len(all_failed)
        
        progress_details.empty()
        current_item_display.empty()
        
        if failed_count > 0:
            status_text.warning(
                f"Completed with issues: {success_count} successful, {failed_count} failed "
                f"({elapsed:.1f}s | {len(targets)/elapsed:.1f} items/sec)", icon=":material/warning:"
            )
        else:
            status_text.success(
                f"Done! Analyzed {len(targets)} products in {elapsed:.1f}s "
                f"({len(targets)/elapsed:.1f} items/sec)", icon=":material/check_circle:"
            )
        
        time.sleep(2)
        st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state['scraped_results'] or st.session_state['failed_items']:
    st.markdown("---")
    
    if st.session_state['failed_items']:
        with st.expander(f"Failed Items ({len(st.session_state['failed_items'])})", expanded=False):
            failed_df = pd.DataFrame(st.session_state['failed_items'])
            st.dataframe(failed_df, use_container_width=True)
    
    if st.session_state['scraped_results']:
        df = pd.DataFrame(st.session_state['scraped_results'])
        
        # New Column Ordering
        priority_cols = [
            'SKU', 'Product Name', 'Brand', 'Is Refurbished', 'Has refurb tag',
            'Has Warranty', 'Warranty Duration', 'Total Product Images', 'Grading last image', 'grading tag',
            'Has info-graphics', 'Infographic Image Count',
            'Seller Name', 
            'Price', 'Product Rating', 'Express', 
            'Category', 'Refurbished Indicators', 
            'Warranty Source', 'Warranty Address', 
            'Primary Image URL', 'Input Source'
        ]
        cols = [c for c in priority_cols if c in df.columns]
        df = df[cols]
        
        st.subheader(":material/bar_chart: Analysis Summary")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Analyzed", len(df))
        with col2:
            refurb_count = (df['Is Refurbished'] == 'YES').sum()
            st.metric("Refurbished Items", refurb_count)
        with col3:
            if 'Grading last image' in df.columns:
                grading_img_count = (df['Grading last image'] == 'YES').sum()
                st.metric("Has Grading Image", grading_img_count)
        with col4:
            if 'grading tag' in df.columns:
                badge_count = df['grading tag'].str.contains('YES', na=False).sum()
                st.metric("Grading Tags", badge_count)
        with col5:
            if 'Total Product Images' in df.columns:
                avg_images = df['Total Product Images'].mean()
                st.metric("Avg Product Images", f"{avg_images:.1f}")
        
        st.markdown("---")
        st.subheader(":material/gallery_thumbnail: Product Gallery")
        
        col_gallery, col_filter = st.columns([3, 1])
        with col_filter:
            view_mode = st.radio("View:", ["Grid", "List"], horizontal=True)
            show_refurb_only = st.checkbox("Refurbished only", value=False)
        
        display_df = df[df['Is Refurbished'] == 'YES'] if show_refurb_only else df
        
        if view_mode == "Grid":
            cols_per_row = 4
            rows = (len(display_df) + cols_per_row - 1) // cols_per_row
            
            for row in range(rows):
                cols = st.columns(cols_per_row)
                for col_idx in range(cols_per_row):
                    idx = row * cols_per_row + col_idx
                    if idx < len(display_df):
                        item = display_df.iloc[idx]
                        with cols[col_idx]:
                            if item.get('Primary Image URL') and item['Primary Image URL'] != 'N/A':
                                try:
                                    st.image(item['Primary Image URL'], use_container_width=True)
                                except:
                                    st.image("https://via.placeholder.com/200x200?text=No+Image", 
                                             use_container_width=True)
                            else:
                                st.image("https://via.placeholder.com/200x200?text=No+Image", 
                                         use_container_width=True)
                            
                            st.caption(f"**{item.get('Brand', 'N/A')}**")
                            product_name = item.get('Product Name', 'N/A')
                            st.caption(product_name[:50] + "..." if len(product_name) > 50 else product_name)
                            
                            badge_text = []
                            if item.get('Is Refurbished') == 'YES': badge_text.append("[Refurbished]")
                            if item.get('Grading last image') == 'YES': badge_text.append("[Grading Img]")
                            if item.get('Total Product Images', 0) > 0: badge_text.append(f"[{item['Total Product Images']} Images]")
                            
                            if badge_text:
                                st.caption(" • ".join(badge_text))
                            
                            st.caption(f"**Price:** {item.get('Price', 'N/A')}")
                            with st.expander("Details"):
                                st.caption(f"**SKU:** {item.get('SKU', 'N/A')}")
                                st.caption(f"**Seller:** {item.get('Seller Name', 'N/A')}")
        else:
            for idx, item in display_df.iterrows():
                with st.container():
                    col1, col2 = st.columns([1, 4])
                    
                    with col1:
                        if item.get('Primary Image URL') and item['Primary Image URL'] != 'N/A':
                            try:
                                st.image(item['Primary Image URL'], width=150)
                            except:
                                st.image("https://via.placeholder.com/150x150?text=No+Image", width=150)
                        else:
                            st.image("https://via.placeholder.com/150x150?text=No+Image", width=150)
                    
                    with col2:
                        st.markdown(f"**{item.get('Product Name', 'N/A')}**")
                        
                        info_cols = st.columns(5)
                        with info_cols[0]: st.caption(f"**Brand:** {item.get('Brand', 'N/A')}")
                        with info_cols[1]: 
                            refurb_status = "YES" if item.get('Is Refurbished') == 'YES' else "NO"
                            st.caption(f"**Refurbished:** {refurb_status}")
                        with info_cols[2]: st.caption(f"**Grading Last Image:** {item.get('Grading last image', 'NO')}")
                        with info_cols[3]: st.caption(f"**Price:** {item.get('Price', 'N/A')}")
                        with info_cols[4]: st.caption(f"**Images:** {item.get('Total Product Images', 0)}")
                        
                        detail_cols = st.columns(3)
                        with detail_cols[0]: st.caption(f"**Seller:** {item.get('Seller Name', 'N/A')}")
                        with detail_cols[1]: st.caption(f"**SKU:** {item.get('SKU', 'N/A')}")
                        with detail_cols[2]: st.caption(f"**Warranty:** {item.get('Warranty Duration', 'N/A')}")
                    st.divider()
        
        if (df['Is Refurbished'] == 'YES').any():
            st.markdown("---")
            st.markdown("### :material/autorenew: Refurbished Products Details")
            refurb_df = df[df['Is Refurbished'] == 'YES']
            st.dataframe(refurb_df, use_container_width=True)
        
        st.markdown("---")
        st.markdown("### :material/table: Complete Analysis Results")
        
        def highlight_renewed(row):
            if row['Brand'] == 'Renewed':
                return ['background-color: #fffacd'] * len(row)
            return [''] * len(row)

        try:
            st.dataframe(df.style.apply(highlight_renewed, axis=1), use_container_width=True)
        except Exception:
            st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download Complete Analysis (CSV)",
            csv,
            f"refurbished_analysis_{int(time.time())}.csv",
            "text/csv",
            key='download-csv',
            icon=":material/download:"
        )
