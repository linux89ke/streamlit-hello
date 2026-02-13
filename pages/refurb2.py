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
st.set_page_config(page_title="Refurbished Product Analyzer", page_icon="🔄", layout="wide")
st.title("🔄 Refurbished Product Data Extractor & Analyzer")
st.markdown("*Specialized scraper for refurbished/renewed product verification*")

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    region_choice = st.selectbox("Select Region:", ("Region 1 (KE)", "Region 2 (UG)"))
    domain = "jumia.co.ke" if "KE" in region_choice else "jumia.ug"
    st.markdown("---")
    show_browser = st.checkbox("Show Browser (Debug Mode)", value=False)
    max_workers = st.slider("Parallel Workers:", 1, 3, 2, help="More workers = faster but may cause timeouts")
    timeout_seconds = st.slider("Page Timeout (seconds):", 10, 30, 20)
    check_images = st.checkbox("Analyze Product Images for Red Badges", value=True, 
                               help="Downloads and analyzes images to detect refurbished tags")
    st.info(f"⚡ Using {max_workers} workers with {timeout_seconds}s timeout")

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
            st.error(f"Could not install driver: {e}")
            return None

def get_chrome_options(headless=True):
    """Configure Chrome options for stability."""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    
    # Essential stability arguments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-notifications")
    
    # Reduce resource usage
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

# --- 2. IMAGE ANALYSIS FOR RED BADGES ---
def has_red_badge(image_url):
    """
    Analyze product image to detect red refurbished badges/tags.
    Looks for prominent red areas that could indicate refurbished tags.
    """
    try:
        response = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize for faster processing
        img = img.resize((300, 300))
        img_array = np.array(img)
        
        # Extract red channel dominance
        red = img_array[:, :, 0].astype(float)
        green = img_array[:, :, 1].astype(float)
        blue = img_array[:, :, 2].astype(float)
        
        # Red badge detection: high red, low green/blue
        red_mask = (red > 180) & (green < 100) & (blue < 100)
        red_pixel_ratio = np.sum(red_mask) / (img_array.shape[0] * img_array.shape[1])
        
        # If >3% of image is bright red, likely has a badge
        if red_pixel_ratio > 0.03:
            return "YES (Red Badge Detected)"
        else:
            return "NO"
            
    except Exception as e:
        return f"ERROR ({str(e)[:20]})"

# --- 3. WARRANTY EXTRACTION ---
def extract_warranty_info(soup, product_name):
    """
    Extract warranty information from multiple sources:
    1. Dedicated Warranty section (Jumia specific)
    2. Product title/name
    3. Specifications table
    4. Product details section
    5. Warranty address field
    """
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
    
    # 1. PRIORITY: Check dedicated Warranty section (Jumia pages have this)
    # Look for div/section with heading "Warranty"
    warranty_heading = soup.find(['h3', 'h4', 'div', 'dt'], string=re.compile(r'^\s*Warranty\s*$', re.I))
    if warranty_heading:
        # Get the next sibling or parent's text
        warranty_container = warranty_heading.find_next_sibling() or warranty_heading.parent
        if warranty_container:
            warranty_text = warranty_container.get_text().strip()
            
            # Try to extract number of months/years
            for pattern in warranty_patterns:
                match = re.search(pattern, warranty_text, re.IGNORECASE)
                if match:
                    duration = match.group(1)
                    unit = 'months' if 'month' in match.group(0).lower() else 'years'
                    warranty_data['has_warranty'] = 'YES'
                    warranty_data['warranty_duration'] = f"{duration} {unit}"
                    warranty_data['warranty_source'] = 'Warranty Section'
                    warranty_data['warranty_details'] = warranty_text[:100]
                    
            # Even if no pattern match, if we found "6 Months" or similar as plain text
            if warranty_data['has_warranty'] == 'NO' and warranty_text:
                simple_match = re.search(r'(\d+)\s*(month|year)', warranty_text, re.IGNORECASE)
                if simple_match:
                    warranty_data['has_warranty'] = 'YES'
                    warranty_data['warranty_duration'] = warranty_text.strip()
                    warranty_data['warranty_source'] = 'Warranty Section'
    
    # 2. Check product name for warranty mentions
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
    
    # 3. Check specifications table - look for "Warranty Address" or warranty info
    warranty_addr_label = soup.find(string=re.compile(r'Warranty Address', re.I))
    if warranty_addr_label:
        addr_container = warranty_addr_label.find_next()
        if addr_container:
            addr_text = addr_container.get_text().strip()
            if addr_text and len(addr_text) > 10:
                warranty_data['warranty_address'] = addr_text
                if warranty_data['has_warranty'] == 'NO':
                    # If we found warranty address but no duration yet, mark as having warranty
                    warranty_data['has_warranty'] = 'YES'
                    warranty_data['warranty_source'] = 'Warranty Address Present'
    
    # 4. Check general specifications for warranty row
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
    
    # 5. Generic page text search as last resort
    if warranty_data['has_warranty'] == 'NO':
        page_text = soup.get_text()[:3000]  # First 3000 chars only
        for pattern in warranty_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                duration = match.group(1)
                unit = 'months' if 'month' in match.group(0).lower() else 'years'
                warranty_data['has_warranty'] = 'YES'
                warranty_data['warranty_duration'] = f"{duration} {unit}"
                warranty_data['warranty_source'] = 'Page Content'
                warranty_data['warranty_details'] = match.group(0)
                break
    
    return warranty_data

# --- 4. REFURBISHED STATUS DETECTION ---
def detect_refurbished_status(soup, product_name):
    """
    Detect if product is refurbished from multiple indicators:
    1. REFU tag badge (Jumia specific)
    2. "Renewed" in breadcrumb/brand
    3. Product title
    4. Refurbished badge/tag
    5. Product condition text
    6. Seller information
    """
    refurb_data = {
        'is_refurbished': 'NO',
        'refurb_indicators': [],
        'condition_text': 'N/A',
        'has_refu_badge': 'NO'
    }
    
    refurb_keywords = ['refurbished', 'renewed', 'refurb', 'recon', 'reconditioned', 
                       'ex-uk', 'ex uk', 'pre-owned', 'certified', 'restored']
    
    # 1. CHECK FOR REFU TAG/BADGE (Jumia specific - high priority)
    # Look for links or badges with REFU tag
    refu_badge = soup.find('a', href=re.compile(r'tag=REFU', re.I))
    if refu_badge:
        refurb_data['is_refurbished'] = 'YES'
        refurb_data['refurb_indicators'].append('REFU tag badge present')
        refurb_data['has_refu_badge'] = 'YES'
    
    # Also check for REFU in img alt text or class names
    refu_img = soup.find(['img', 'div', 'span'], attrs={'alt': re.compile(r'REFU', re.I)})
    if refu_img and 'REFU tag badge present' not in refurb_data['refurb_indicators']:
        refurb_data['is_refurbished'] = 'YES'
        refurb_data['refurb_indicators'].append('REFU badge image')
        refurb_data['has_refu_badge'] = 'YES'
    
    # 2. CHECK BREADCRUMB/BRAND for "Renewed"
    # Jumia uses "Renewed" as a brand prefix for refurbished items
    breadcrumbs = soup.find_all(['a', 'span'], class_=re.compile(r'breadcrumb|brcb'))
    for crumb in breadcrumbs:
        crumb_text = crumb.get_text().lower()
        if 'renewed' in crumb_text:
            refurb_data['is_refurbished'] = 'YES'
            refurb_data['refurb_indicators'].append('Breadcrumb contains "Renewed"')
            break
    
    # 3. Check product name
    product_name_lower = product_name.lower()
    for keyword in refurb_keywords:
        if keyword in product_name_lower:
            refurb_data['is_refurbished'] = 'YES'
            indicator = f'Title contains "{keyword}"'
            if indicator not in refurb_data['refurb_indicators']:
                refurb_data['refurb_indicators'].append(indicator)
            # Don't break - collect all keywords
    
    # 4. Check for refurbished badge/tag in various locations
    badge_searches = [
        soup.find(['span', 'div', 'badge'], class_=re.compile(r'refurb|renewed', re.I)),
        soup.find(['span', 'div'], string=re.compile(r'REFURBISHED|RENEWED', re.I)),
        soup.find(['img'], attrs={'alt': re.compile(r'refurb|renewed', re.I)})
    ]
    
    for badge in badge_searches:
        if badge:
            refurb_data['is_refurbished'] = 'YES'
            if 'Refurbished badge present' not in refurb_data['refurb_indicators']:
                refurb_data['refurb_indicators'].append('Refurbished badge present')
            break
    
    # 5. Check condition text - look more broadly
    condition_patterns = [
        r'condition[:\s]*(renewed|refurbished|excellent|good|like new|grade [a-c])',
        r'(renewed|refurbished)[,\s]*(no scratches|excellent|good condition|like new)',
        r'product condition[:\s]*([^\n]+)',
    ]
    
    # Check first 2000 chars of page
    page_text = soup.get_text()[:2000]
    for pattern in condition_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            refurb_data['condition_text'] = match.group(0).strip()
            if refurb_data['is_refurbished'] == 'NO' and any(kw in match.group(0).lower() for kw in refurb_keywords):
                refurb_data['is_refurbished'] = 'YES'
            if 'Condition statement found' not in refurb_data['refurb_indicators']:
                refurb_data['refurb_indicators'].append('Condition statement found')
            break
    
    # 6. Check product details/description for refurbishment mentions
    details_section = soup.find(['div', 'section'], class_=re.compile(r'detail|description|product-desc'))
    if details_section:
        details_text = details_section.get_text()[:500].lower()
        if any(kw in details_text for kw in refurb_keywords):
            if refurb_data['is_refurbished'] == 'NO':
                refurb_data['is_refurbished'] = 'YES'
            if 'Product description mentions refurbished' not in refurb_data['refurb_indicators']:
                refurb_data['refurb_indicators'].append('Product description mentions refurbished')
    
    return refurb_data

# --- 5. ENHANCED SELLER EXTRACTION ---
def extract_seller_info(soup):
    """
    Extract detailed seller information including performance metrics.
    Optimized for Jumia's seller information structure.
    """
    seller_data = {
        'seller_name': 'N/A',
        'seller_score': 'N/A',
        'seller_followers': 'N/A',
        'shipping_speed': 'N/A',
        'quality_score': 'N/A',
        'customer_rating': 'N/A'
    }
    
    # Method 1: Jumia's seller information section structure
    # Look for "Seller Information" heading
    seller_heading = soup.find(['h2', 'h3'], string=re.compile(r'Seller Information', re.I))
    if seller_heading:
        seller_section = seller_heading.find_next(['div', 'section'])
        
        if seller_section:
            # Extract seller name - usually a link
            seller_link = seller_section.find('a', href=re.compile(r'/[^/]+/$'))
            if seller_link:
                seller_data['seller_name'] = seller_link.get_text().strip()
            
            # Extract seller score
            score_text = seller_section.find(string=re.compile(r'\d+%.*Seller Score', re.I))
            if score_text:
                score_match = re.search(r'(\d+)%', score_text)
                if score_match:
                    seller_data['seller_score'] = score_match.group(1) + '%'
            
            # Extract followers
            follower_text = seller_section.find(string=re.compile(r'\d+.*Follower', re.I))
            if follower_text:
                follower_match = re.search(r'(\d+)', follower_text)
                if follower_match:
                    seller_data['seller_followers'] = follower_match.group(1)
    
    # Method 2: Seller Performance section
    performance_heading = soup.find(['h3', 'h4', 'div'], string=re.compile(r'Seller Performance', re.I))
    if performance_heading:
        perf_section = performance_heading.find_next(['div', 'ul'])
        if perf_section:
            perf_text = perf_section.get_text()
            
            # Shipping speed
            if 'shipping speed' in perf_text.lower():
                speed_match = re.search(r'Shipping speed:\s*(\w+)', perf_text, re.I)
                if speed_match:
                    seller_data['shipping_speed'] = speed_match.group(1)
            
            # Quality Score
            if 'quality score' in perf_text.lower():
                quality_match = re.search(r'Quality Score:\s*([\w\s]+)', perf_text, re.I)
                if quality_match:
                    seller_data['quality_score'] = quality_match.group(1).strip()
            
            # Customer Rating
            if 'customer rating' in perf_text.lower():
                rating_match = re.search(r'Customer Rating:\s*(\w+)', perf_text, re.I)
                if rating_match:
                    seller_data['customer_rating'] = rating_match.group(1)
    
    # Method 3: Alternative seller box structure (older Jumia layout)
    if seller_data['seller_name'] == 'N/A':
        seller_box = soup.select_one('div.-hr.-pas, div.seller-details, div[class*="seller"]')
        if seller_box:
            # Try to find seller name in a paragraph or link
            seller_elem = seller_box.find(['p', 'a'], class_=re.compile(r'name|title|-m'))
            if seller_elem:
                seller_text = seller_elem.get_text().strip()
                # Filter out non-seller text
                if seller_text and not any(x in seller_text.lower() for x in ['details', 'follow', 'sell on', 'view', 'performance']):
                    seller_data['seller_name'] = seller_text
    
    # Method 4: Extract from link structure /seller-name/
    if seller_data['seller_name'] == 'N/A':
        seller_link = soup.find('a', href=re.compile(r'/[\w\-]+/$'))
        if seller_link:
            # Check if this is in seller context
            parent_text = seller_link.parent.get_text().lower() if seller_link.parent else ''
            if 'seller' in parent_text or 'sold by' in parent_text:
                seller_data['seller_name'] = seller_link.get_text().strip()
    
    return seller_data

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
            st.error(f"Error reading file: {e}")

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

# --- 7. ENHANCED SCRAPING FUNCTION ---
def extract_product_data_enhanced(soup, data, is_sku_search, target, check_images=True):
    """Extract comprehensive product data with refurbished analysis."""
    
    # Product Name
    h1 = soup.find('h1')
    product_name = h1.text.strip() if h1 else "N/A"
    data['Product Name'] = product_name

    # Brand - improved extraction
    brand_label = soup.find(string=re.compile(r"Brand:\s*", re.I))
    if brand_label and brand_label.parent:
        brand_link = brand_label.parent.find('a')
        data['Brand'] = brand_link.text.strip() if brand_link else \
                       brand_label.parent.get_text().replace('Brand:', '').split('|')[0].strip()
    
    # Extract brand from breadcrumbs if not found
    if data['Brand'] in ["N/A", ""]:
        brand_crumb = soup.find('a', href=re.compile(r'/[\w\-]+/$'))
        if brand_crumb:
            data['Brand'] = brand_crumb.get_text().strip()
    
    # If brand still generic or Renewed, try to extract from product name
    if data['Brand'] in ["N/A", ""] or data['Brand'].lower() in ["generic", "renewed"]:
        # Extract first word from product name (usually the brand)
        first_word = product_name.split()[0] if product_name != "N/A" else "N/A"
        # Check if first word is "Renewed" - if so, get second word
        if first_word.lower() == "renewed" and len(product_name.split()) > 1:
            data['Brand'] = product_name.split()[1]
        else:
            data['Brand'] = first_word

    # Seller Information (Enhanced)
    seller_info = extract_seller_info(soup)
    data['Seller Name'] = seller_info['seller_name']
    data['Seller Score'] = seller_info['seller_score']
    data['Seller Followers'] = seller_info['seller_followers']
    data['Shipping Speed'] = seller_info['shipping_speed']
    data['Quality Score'] = seller_info['quality_score']
    data['Customer Rating'] = seller_info['customer_rating']

    # Category - improved extraction with full path
    breadcrumbs = soup.select('.osh-breadcrumb a, .brcbs a, [class*="breadcrumb"] a')
    cats = [b.text.strip() for b in breadcrumbs if b.text.strip() and b.text.strip().lower() != 'home']
    # Create full category path
    if len(cats) > 0:
        data['Category'] = ' > '.join(cats)
    else:
        data['Category'] = "N/A"

    # SKU
    sku_match = re.search(r'SKU[:\s]*([A-Z0-9\-]+)', soup.get_text())
    if sku_match:
        data['SKU'] = sku_match.group(1)
    elif is_sku_search:
        data['SKU'] = target.get('original_sku', 'N/A')

    # Images - get primary and all images
    image_url = None
    for img in soup.find_all('img', limit=15):
        src = img.get('data-src') or img.get('src')
        if src and ('/product/' in src or '/unsafe/' in src):
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = 'https://www.jumia.co.ke' + src
            
            if src not in data['Image URLs']:
                data['Image URLs'].append(src)
                if not image_url:
                    image_url = src
    
    data['Primary Image URL'] = image_url if image_url else "N/A"

    # Refurbished Status Detection
    refurb_status = detect_refurbished_status(soup, product_name)
    data['Is Refurbished'] = refurb_status['is_refurbished']
    data['Has REFU Badge'] = refurb_status['has_refu_badge']
    data['Refurbished Indicators'] = ', '.join(refurb_status['refurb_indicators']) if refurb_status['refurb_indicators'] else 'None'
    data['Condition Text'] = refurb_status['condition_text']

    # Warranty Information
    warranty_info = extract_warranty_info(soup, product_name)
    data['Has Warranty'] = warranty_info['has_warranty']
    data['Warranty Duration'] = warranty_info['warranty_duration']
    data['Warranty Source'] = warranty_info['warranty_source']
    data['Warranty Address'] = warranty_info['warranty_address']

    # Image Badge Detection (if enabled)
    if check_images and image_url and image_url != "N/A":
        data['Red Badge in Image'] = has_red_badge(image_url)
    else:
        data['Red Badge in Image'] = 'Not Checked'

    # Express
    express_badge = soup.find(['svg', 'img', 'span'], attrs={'aria-label': re.compile(r'Jumia Express', re.I)})
    if express_badge:
        data['Express'] = "Yes"
    
    # Price - improved extraction
    price_tag = soup.find('span', class_=re.compile(r'price|prc|-b'))
    if not price_tag:
        # Alternative price location
        price_tag = soup.find(['div', 'span'], string=re.compile(r'KSh\s*[\d,]+'))
    
    if price_tag:
        price_text = price_tag.get_text().strip()
        # Clean up price text
        price_match = re.search(r'KSh\s*([\d,]+)', price_text)
        if price_match:
            data['Price'] = 'KSh ' + price_match.group(1)
        else:
            data['Price'] = price_text
    
    # Customer Reviews/Ratings
    rating_elem = soup.find(['span', 'div'], class_=re.compile(r'rating|stars'))
    if rating_elem:
        rating_text = rating_elem.get_text()
        rating_match = re.search(r'([\d.]+)\s*out of\s*5', rating_text)
        if rating_match:
            data['Product Rating'] = rating_match.group(1) + '/5'
    
    # Number of reviews
    review_count = soup.find(string=re.compile(r'\(\d+\s*verified ratings?\)', re.I))
    if review_count:
        count_match = re.search(r'(\d+)', review_count)
        if count_match:
            data['Review Count'] = count_match.group(1)
    
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
        'Seller Score': 'N/A',
        'Seller Followers': 'N/A',
        'Shipping Speed': 'N/A',
        'Quality Score': 'N/A',
        'Customer Rating': 'N/A',
        'Category': 'N/A',
        'SKU': 'N/A',
        'Is Refurbished': 'NO',
        'Has REFU Badge': 'NO',
        'Refurbished Indicators': 'None',
        'Condition Text': 'N/A',
        'Has Warranty': 'NO',
        'Warranty Duration': 'N/A',
        'Warranty Source': 'None',
        'Warranty Address': 'N/A',
        'Red Badge in Image': 'Not Checked',
        'Primary Image URL': 'N/A',
        'Image URLs': [],
        'Price': 'N/A',
        'Product Rating': 'N/A',
        'Review Count': 'N/A',
        'Express': 'No'
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
        
        # Handle SKU search
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
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
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

col_txt, col_upl = st.columns(2)
with col_txt:
    text_in = st.text_area("Paste SKUs/Links:", height=150, 
                           placeholder="Enter SKUs or URLs, one per line\nExample: SA948MP5EER52NAFAMZ")
with col_upl:
    file_in = st.file_uploader("Upload Excel/CSV with SKUs:", type=['xlsx', 'csv'])

st.markdown("---")

if st.button("🚀 Start Refurbished Product Analysis", type="primary"):
    targets = process_inputs(text_in, file_in, domain)
    
    if not targets:
        st.warning("⚠️ No valid data found. Please enter SKUs or URLs.")
    else:
        st.session_state['scraped_results'] = []
        st.session_state['failed_items'] = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text(f"🔄 Analyzing {len(targets)} products for refurbished attributes...")
        start_time = time.time()
        
        batch_size = max_workers * 2
        all_results = []
        all_failed = []
        
        for i in range(0, len(targets), batch_size):
            batch = targets[i:i + batch_size]
            batch_results, batch_failed = scrape_items_parallel(
                batch, max_workers, not show_browser, timeout_seconds, check_images
            )
            
            all_results.extend(batch_results)
            all_failed.extend(batch_failed)
            
            progress = min((i + len(batch)) / len(targets), 1.0)
            progress_bar.progress(progress)
            status_text.text(
                f"🔄 Processed {min(i + len(batch), len(targets))}/{len(targets)} items..."
            )
        
        elapsed = time.time() - start_time
        st.session_state['scraped_results'] = all_results
        st.session_state['failed_items'] = all_failed
        
        success_count = len(all_results)
        failed_count = len(all_failed)
        
        if failed_count > 0:
            status_text.warning(
                f"⚠️ Completed with issues: {success_count} successful, {failed_count} failed "
                f"({elapsed:.1f}s)"
            )
        else:
            status_text.success(
                f"✅ Done! Analyzed {len(targets)} products in {elapsed:.1f}s "
                f"({len(targets)/elapsed:.1f} items/sec)"
            )
        
        time.sleep(1)
        st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state['scraped_results'] or st.session_state['failed_items']:
    st.markdown("---")
    
    # Show failed items if any
    if st.session_state['failed_items']:
        with st.expander(f"⚠️ Failed Items ({len(st.session_state['failed_items'])})", expanded=False):
            failed_df = pd.DataFrame(st.session_state['failed_items'])
            st.dataframe(failed_df, use_container_width=True)
    
    # Show successful results
    if st.session_state['scraped_results']:
        df = pd.DataFrame(st.session_state['scraped_results'])
        
        # Reorder columns for better visibility
        priority_cols = [
            'SKU', 'Product Name', 'Brand', 'Is Refurbished', 'Has REFU Badge',
            'Has Warranty', 'Warranty Duration', 'Red Badge in Image',
            'Seller Name', 'Seller Score', 'Shipping Speed', 'Quality Score', 'Customer Rating',
            'Price', 'Product Rating', 'Review Count', 'Express',
            'Category', 'Refurbished Indicators', 'Condition Text',
            'Warranty Source', 'Warranty Address', 'Seller Followers',
            'Primary Image URL', 'Input Source'
        ]
        cols = [c for c in priority_cols if c in df.columns]
        df = df[cols]
        
        # Key Metrics
        st.subheader("📊 Analysis Summary")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("✅ Products Analyzed", len(df))
        with col2:
            refurb_count = (df['Is Refurbished'] == 'YES').sum()
            st.metric("🔄 Refurbished Items", refurb_count)
        with col3:
            warranty_count = (df['Has Warranty'] == 'YES').sum()
            st.metric("🛡️ With Warranty", warranty_count)
        with col4:
            if 'Red Badge in Image' in df.columns:
                badge_count = df['Red Badge in Image'].str.contains('YES', na=False).sum()
                st.metric("🏷️ Red Badges Detected", badge_count)
        with col5:
            express_count = (df['Express'] == 'Yes').sum()
            st.metric("⚡ Express Items", express_count)
        
        # Refurbished Status Breakdown
        if (df['Is Refurbished'] == 'YES').any():
            st.markdown("### 🔄 Refurbished Products Details")
            refurb_df = df[df['Is Refurbished'] == 'YES']
            st.dataframe(refurb_df, use_container_width=True)
        
        # Full Results
        st.markdown("### 📋 Complete Analysis Results")
        st.dataframe(df, use_container_width=True)
        
        # Download button
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download Complete Analysis (CSV)",
            csv,
            f"refurbished_analysis_{int(time.time())}.csv",
            "text/csv",
            key='download-csv'
        )
        
        # Additional insights
        with st.expander("💡 Analysis Insights", expanded=False):
            st.markdown(f"""
            **Refurbished Detection:**
            - {refurb_count} products identified as refurbished/renewed
            - Detection based on: product title, badges, condition statements
            
            **Warranty Coverage:**
            - {warranty_count} products have warranty information
            - Warranty sources: product names, specifications, page content
            
            **Image Analysis:**
            - {'Enabled' if check_images else 'Disabled'} red badge detection in product images
            - Scans for prominent red areas indicating refurbished tags
            
            **Seller Information:**
            - Extracted seller names and performance scores where available
            - Useful for verifying authorized refurbished sellers
            """)
