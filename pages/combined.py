import os
import re
import time
import zipfile
import hashlib
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Jumia Refurbished Suite",
    page_icon="🔖",
    layout="wide"
)

st.title("🔖 Jumia Refurbished Product Suite")
st.markdown("Analyze listings, apply grade tags, and convert existing tags — all in one place.")

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
MARGIN_PERCENT   = 0.12
BANNER_RATIO     = 0.095
VERT_STRIP_RATIO = 0.18
WHITE_THRESHOLD  = 240
PADDING_FACTOR   = 0.74

TAG_FILES = {
    "Renewed":     "RefurbishedStickerUpdated-Renewd.png",
    "Refurbished": "RefurbishedStickerUpdate-No-Grading.png",
    "Grade A":     "Refurbished-StickerUpdated-Grade-A.png",
    "Grade B":     "Refurbished-StickerUpdated-Grade-B.png",
    "Grade C":     "Refurbished-StickerUpdated-Grade-C.png",
}

DOMAIN_MAP = {
    "Kenya (KE)":   "jumia.co.ke",
    "Uganda (UG)":  "jumia.ug",
    "Nigeria (NG)": "jumia.com.ng",
    "Morocco (MA)": "jumia.ma",
    "Ghana (GH)":   "jumia.com.gh",
}

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("🌍 Region")
    region_choice = st.selectbox(
        "Select Country:",
        list(DOMAIN_MAP.keys()),
        help="Applies to product analysis AND SKU image lookups"
    )
    domain = DOMAIN_MAP[region_choice]
    base_url = f"https://www.{domain}"

    st.markdown("---")
    st.header("🔖 Tag Settings")
    tag_type = st.selectbox(
        "Refurbished Grade:",
        list(TAG_FILES.keys())
    )

    st.markdown("---")
    st.header("🖼️ Image Settings")
    if "image_scale_value" not in st.session_state:
        st.session_state.image_scale_value = 100
    image_scale = st.slider(
        "Product Image Size (%):",
        min_value=50, max_value=200,
        value=st.session_state.image_scale_value,
        step=5, key="image_scale_slider",
        help="Applies to single-image tagging. Default is 100%."
    )
    st.session_state.image_scale_value = image_scale
    st.caption(f"Current size: {image_scale}%")

    st.markdown("---")
    st.header("⚙️ Analyzer Settings")
    show_browser    = st.checkbox("Show Browser (Debug)", value=False)
    max_workers     = st.slider("Parallel Workers:", 1, 3, 2)
    timeout_seconds = st.slider("Page Timeout (s):", 10, 30, 20)
    check_images    = st.checkbox("Analyze Images for Red Badges", value=True)
    st.info(f"{max_workers} workers · {timeout_seconds}s timeout", icon="⚡")


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED UTILITIES — TAG FILE
# ══════════════════════════════════════════════════════════════════════════════
def get_tag_path(filename):
    for path in [filename,
                 os.path.join(os.path.dirname(__file__), filename),
                 os.path.join(os.getcwd(), filename)]:
        if os.path.exists(path):
            return path
    return filename


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED UTILITIES — BROWSER DRIVER
# ══════════════════════════════════════════════════════════════════════════════
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
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    for arg in ["--no-sandbox", "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu", "--disable-extensions",
                "--window-size=1920,1080", "--disable-notifications",
                "--disable-logging", "--log-level=3", "--silent"]:
        opts.add_argument(arg)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    for path in ["/usr/bin/chromium", "/usr/bin/chromium-browser",
                 "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]:
        if os.path.exists(path):
            opts.binary_location = path
            break
    return opts


def get_driver(headless=True, timeout=20):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        return None
    opts = get_chrome_options(headless)
    driver = None
    try:
        dp = get_driver_path()
        if dp:
            svc = Service(dp)
            svc.log_path = os.devnull
            driver = webdriver.Chrome(service=svc, options=opts)
    except Exception:
        try:
            driver = webdriver.Chrome(options=opts)
        except Exception:
            return None
    if driver:
        try:
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.set_page_load_timeout(timeout)
            driver.implicitly_wait(5)
        except Exception:
            pass
    return driver


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED UTILITIES — JUMIA SKU IMAGE FETCH
# ══════════════════════════════════════════════════════════════════════════════
def search_jumia_by_sku(sku, b_url, search_url):
    """Fetch the primary product image from a Jumia SKU search."""
    driver = None
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
    except ImportError:
        st.error("Selenium not installed.")
        return None
    try:
        driver = get_driver(headless=True)
        if not driver:
            st.error("Could not initialise browser driver.")
            return None
        driver.get(search_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
        except TimeoutException:
            st.error("Page load timeout.")
            return None
        if ("There are no results for" in driver.page_source
                or "No results found" in driver.page_source):
            st.warning(f"No products found for SKU: {sku}")
            return None
        links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
        if not links:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='.html']")
        if not links:
            st.warning(f"No products found for SKU: {sku}")
            return None
        driver.get(links[0].get_attribute("href"))
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1")))
        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        image_url = None
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            image_url = og["content"]
        if not image_url:
            for img in soup.find_all("img", limit=15):
                src = img.get("data-src") or img.get("src")
                if src and ("/product/" in src or "/unsafe/" in src or "jumia.is" in src):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = b_url + src
                    image_url = src
                    break
        if not image_url:
            st.warning("Found product page but could not extract image.")
            return None
        r = requests.get(image_url,
                         headers={"User-Agent": "Mozilla/5.0", "Referer": b_url},
                         timeout=15)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        st.error(f"Error fetching SKU image: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE PROCESSING — TAGGING
# ══════════════════════════════════════════════════════════════════════════════
def auto_crop_whitespace(image: Image.Image) -> Image.Image:
    img_rgb = image.convert("RGB")
    pixels  = list(img_rgb.getdata())
    w, h    = img_rgb.size
    non_white = [
        (i % w, i // w)
        for i, (r, g, b) in enumerate(pixels)
        if not (r > WHITE_THRESHOLD and g > WHITE_THRESHOLD and b > WHITE_THRESHOLD)
    ]
    if not non_white:
        return image
    xs   = [p[0] for p in non_white]
    ys   = [p[1] for p in non_white]
    bbox = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    return image.crop(bbox)


def fit_with_margin(product_image: Image.Image, tag_image: Image.Image,
                    scale_pct: int = 100) -> Image.Image:
    """Scale product to fill the safe zone with MARGIN_PERCENT breathing room."""
    canvas_w, canvas_h = tag_image.size
    safe_w = canvas_w - int(canvas_w * VERT_STRIP_RATIO)
    safe_h = canvas_h - int(canvas_h * BANNER_RATIO)
    scale_mult = scale_pct / 100.0
    margin_x = int(safe_w * MARGIN_PERCENT)
    margin_y = int(safe_h * MARGIN_PERCENT)
    inner_w  = int((safe_w - 2 * margin_x) * scale_mult)
    inner_h  = int((safe_h - 2 * margin_y) * scale_mult)
    prod_w, prod_h = product_image.size
    scale  = min(inner_w / prod_w, inner_h / prod_h)
    new_w  = int(prod_w * scale)
    new_h  = int(prod_h * scale)
    product_resized = product_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    result = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    x = margin_x + (int(safe_w * scale_mult) - new_w) // 2
    y = margin_y + (int(safe_h * scale_mult) - new_h) // 2
    x = max(margin_x, x)
    y = max(margin_y, y)
    if product_resized.mode == "RGBA":
        result.paste(product_resized, (x, y), product_resized)
    else:
        result.paste(product_resized, (x, y))
    if tag_image.mode == "RGBA":
        result.paste(tag_image, (0, 0), tag_image)
    else:
        result.paste(tag_image, (0, 0))
    return result


def process_single(product_image: Image.Image, tag_image: Image.Image,
                   scale_pct: int = 100) -> Image.Image:
    """Full pipeline: auto-crop whitespace → fit with margin → composite."""
    cropped = auto_crop_whitespace(product_image.convert("RGBA"))
    return fit_with_margin(cropped, tag_image, scale_pct)


def detect_tag_boundaries(image: Image.Image):
    """Auto-detect old tag strip boundaries by scanning pixels."""
    img_rgb = image.convert("RGB")
    w, h = img_rgb.size

    def is_red(r, g, b):
        return r > 150 and g < 80 and b < 80

    def is_non_white(r, g, b):
        return not (r > 230 and g > 230 and b > 230)

    strip_left = w - int(w * VERT_STRIP_RATIO)
    for x in range(w - 1, int(w * 0.70), -1):
        if any(is_red(*img_rgb.getpixel((x, y))) for y in range(h)):
            strip_left = x
        else:
            if strip_left < w - 1:
                break

    banner_top = h - int(h * BANNER_RATIO)
    for y in range(int(h * 0.75), h):
        if any(is_non_white(*img_rgb.getpixel((x, y))) for x in range(strip_left)):
            banner_top = y
            break

    return strip_left, banner_top


def strip_and_retag(tagged_image: Image.Image, new_tag_image: Image.Image) -> Image.Image:
    """Strip old tag by pixel detection, then overlay the new tag cleanly."""
    img_rgb = tagged_image.convert("RGB")
    w, h = img_rgb.size
    strip_left, banner_top = detect_tag_boundaries(img_rgb)
    clean_canvas = img_rgb.copy()
    draw = ImageDraw.Draw(clean_canvas)
    draw.rectangle([strip_left, 0, w, h], fill=(255, 255, 255))
    draw.rectangle([0, banner_top, w, h], fill=(255, 255, 255))
    if new_tag_image.mode == "RGBA":
        clean_canvas.paste(new_tag_image, (0, 0), new_tag_image)
    else:
        clean_canvas.paste(new_tag_image, (0, 0))
    return clean_canvas


def image_to_bytes(img: Image.Image, quality=95) -> bytes:
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE PROCESSING — ANALYSIS (dhash, red badge)
# ══════════════════════════════════════════════════════════════════════════════
def get_dhash(img):
    try:
        resample = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
        img = img.convert('L').resize((9, 8), resample)
        pixels = np.array(img)
        diff = pixels[:, 1:] > pixels[:, :-1]
        return diff.flatten()
    except Exception:
        return None


@st.cache_data
def get_target_promo_hash():
    target_url = "https://ke.jumia.is/unsafe/fit-in/680x680/filters:fill(white)/product/21/3620523/3.jpg?0053"
    try:
        r = requests.get(target_url, timeout=10)
        img = Image.open(BytesIO(r.content))
        return get_dhash(img)
    except Exception:
        return None


def has_red_badge(image_url):
    try:
        r = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(r.content))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img = img.resize((300, 300))
        arr = np.array(img)
        red_mask = (arr[:,:,0].astype(float) > 180) & \
                   (arr[:,:,1].astype(float) < 100) & \
                   (arr[:,:,2].astype(float) < 100)
        ratio = np.sum(red_mask) / (arr.shape[0] * arr.shape[1])
        return "YES (Red Badge Detected)" if ratio > 0.03 else "NO"
    except Exception as e:
        return f"ERROR ({str(e)[:20]})"


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — WARRANTY, REFURB DETECTION, SELLER
# ══════════════════════════════════════════════════════════════════════════════
def extract_warranty_info(soup, product_name):
    data = {
        'has_warranty': 'NO', 'warranty_duration': 'N/A',
        'warranty_source': 'None', 'warranty_details': '',
        'warranty_address': 'N/A'
    }
    patterns = [
        r'(\d+)\s*(?:months?|month|mnths?|mths?)\s*(?:warranty|wrty|wrnty)',
        r'(\d+)\s*(?:year|yr|years|yrs)\s*(?:warranty|wrty|wrnty)',
        r'warranty[:\s]*(\d+)\s*(?:months?|years?)',
    ]
    heading = soup.find(['h3','h4','div','dt'], string=re.compile(r'^\s*Warranty\s*$', re.I))
    if heading:
        val = heading.find_next(['div','dd','p'])
        if val:
            text = val.get_text().strip()
            if text and text.lower() not in ['n/a','na','none','']:
                found = False
                for p in patterns:
                    m = re.search(p, text, re.I)
                    if m:
                        unit = 'months' if 'month' in m.group(0).lower() else 'years'
                        data.update({'has_warranty':'YES',
                                     'warranty_duration':f"{m.group(1)} {unit}",
                                     'warranty_source':'Warranty Section',
                                     'warranty_details':text[:100]})
                        found = True; break
                if not found:
                    sm = re.search(r'(\d+)\s*(month|year)', text, re.I)
                    if sm:
                        data.update({'has_warranty':'YES',
                                     'warranty_duration':text.strip(),
                                     'warranty_source':'Warranty Section'})
    if data['has_warranty'] == 'NO':
        for p in patterns:
            m = re.search(p, product_name, re.I)
            if m:
                unit = 'months' if 'month' in m.group(0).lower() else 'years'
                data.update({'has_warranty':'YES',
                             'warranty_duration':f"{m.group(1)} {unit}",
                             'warranty_source':'Product Name',
                             'warranty_details':m.group(0)})
                break
    lbl = soup.find(string=re.compile(r'Warranty\s+Address', re.I))
    if lbl:
        el = lbl.find_next(['dd','p','div'])
        if el:
            addr = re.sub(r'<[^>]+>', '', el.get_text()).strip()
            if addr and len(addr) > 10:
                data['warranty_address'] = addr
    if data['has_warranty'] == 'NO' and not heading:
        for row in soup.find_all(['tr','div','li'],
                                  class_=re.compile(r'spec|detail|attribute|row')):
            text = row.get_text()
            if 'warranty' in text.lower():
                for p in patterns:
                    m = re.search(p, text, re.I)
                    if m:
                        unit = 'months' if 'month' in m.group(0).lower() else 'years'
                        data.update({'has_warranty':'YES',
                                     'warranty_duration':f"{m.group(1)} {unit}",
                                     'warranty_source':'Specifications',
                                     'warranty_details':text.strip()[:100]})
                        break
                if data['has_warranty'] == 'YES':
                    break
    return data


def detect_refurbished_status(soup, product_name):
    data = {'is_refurbished':'NO', 'refurb_indicators':[], 'has_refurb_tag':'NO'}
    kws  = ['refurbished','renewed','refurb','recon','reconditioned',
            'ex-uk','ex uk','pre-owned','certified','restored']
    scope = soup
    h1 = soup.find('h1')
    if h1:
        c = h1.find_parent('div', class_=re.compile(r'col10|-pvs|-p'))
        scope = c if c else h1.parent.parent

    if scope.find('a', href=re.compile(r'/all-products/\?tag=REFU', re.I)):
        data.update({'is_refurbished':'YES','has_refurb_tag':'YES'})
        data['refurb_indicators'].append('REFU tag badge present')

    ri = scope.find('img', attrs={'alt': re.compile(r'^REFU$', re.I)})
    if ri:
        p = ri.parent
        if p and p.name == 'a' and 'tag=REFU' in p.get('href',''):
            if 'REFU tag badge present' not in data['refurb_indicators']:
                data.update({'is_refurbished':'YES','has_refurb_tag':'YES'})
                data['refurb_indicators'].append('REFU badge image')

    for crumb in soup.find_all(['a','span'], class_=re.compile(r'breadcrumb|brcb')):
        if 'renewed' in crumb.get_text().lower():
            data['is_refurbished'] = 'YES'
            data['refurb_indicators'].append('Breadcrumb: "Renewed"')
            break

    for kw in kws:
        if kw in product_name.lower():
            data['is_refurbished'] = 'YES'
            ind = f'Title: "{kw}"'
            if ind not in data['refurb_indicators']:
                data['refurb_indicators'].append(ind)

    for badge in [
        scope.find(['span','div','badge'], class_=re.compile(r'refurb|renewed', re.I)),
        scope.find(['span','div'], string=re.compile(r'REFURBISHED|RENEWED', re.I)),
        scope.find('img', attrs={'alt': re.compile(r'refurb|renewed', re.I)})
    ]:
        if badge:
            data['is_refurbished'] = 'YES'
            if 'Refurbished badge present' not in data['refurb_indicators']:
                data['refurb_indicators'].append('Refurbished badge present')
            break

    page_text = (scope if scope != soup else soup).get_text()[:3000]
    for pat in [
        r'condition[:\s]*(renewed|refurbished|excellent|good|like new|grade [a-c])',
        r'(renewed|refurbished)[,\s]*(no scratches|excellent|good condition|like new)',
        r'product condition[:\s]*([^\n]+)',
    ]:
        m = re.search(pat, page_text, re.I)
        if m:
            if data['is_refurbished'] == 'NO' and any(k in m.group(0).lower() for k in kws):
                data['is_refurbished'] = 'YES'
            if 'Condition statement found' not in data['refurb_indicators']:
                data['refurb_indicators'].append('Condition statement found')
            break
    return data


def extract_seller_info(soup):
    data = {'seller_name': 'N/A'}
    sec = soup.find(['h2','h3','div','p'], string=re.compile(r'Seller\s+Information', re.I))
    if not sec:
        sec = soup.find(['div','section'], class_=re.compile(r'seller-info|seller-box', re.I))
    if sec:
        container = sec.find_parent('div') or sec.parent
        if container:
            el = container.find(['p','div'], class_=re.compile(r'-pbs|-m'))
            if el and len(el.get_text().strip()) > 1:
                data['seller_name'] = el.get_text().strip()
            else:
                for c in container.find_all(['a','p','b']):
                    text = c.get_text().strip()
                    if not text or any(x in text.lower() for x in
                                       ['follow','score','seller','information','%','rating']):
                        continue
                    if re.search(r'\d+%', text):
                        continue
                    data['seller_name'] = text
                    break
    return data


def clean_jumia_sku(raw_sku):
    if not raw_sku or raw_sku == "N/A":
        return "N/A"
    m = re.search(r'([A-Z0-9]+NAFAM[A-Z])', raw_sku)
    return m.group(1) if m else raw_sku.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — CATEGORY LINK EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
def extract_category_links(category_url, headless=True, timeout=20):
    driver = get_driver(headless, timeout)
    if not driver:
        return []
    extracted = set()
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
        driver.get(category_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a.core")))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        for elem in driver.find_elements(By.CSS_SELECTOR, "article.prd a.core"):
            href = elem.get_attribute("href")
            if href and ("/product/" in href or ".html" in href):
                extracted.add(href)
    except Exception as e:
        st.error(f"Error extracting category links: {e}", icon="🚨")
    finally:
        try: driver.quit()
        except: pass
    return list(extracted)


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — FULL PRODUCT SCRAPE
# ══════════════════════════════════════════════════════════════════════════════
def extract_product_data(soup, data, is_sku_search, target, do_check_images=True):
    h1 = soup.find('h1')
    product_name = h1.text.strip() if h1 else "N/A"
    data['Product Name'] = product_name

    # Brand
    brand_label = soup.find(string=re.compile(r"Brand:\s*", re.I))
    if brand_label and brand_label.parent:
        bl = brand_label.parent.find('a')
        if bl:
            data['Brand'] = bl.text.strip()
        else:
            data['Brand'] = brand_label.parent.get_text().replace('Brand:','').split('|')[0].strip()
    if data['Brand'] in ["N/A",""] or \
       any(x in data.get('Brand','') for x in ["window.fbq","undefined","function("]):
        data['Brand'] = "Renewed"
    if data['Brand'] in ["N/A",""] or data['Brand'].lower() in ["generic","renewed","refurbished"]:
        fw = product_name.split()[0] if product_name != "N/A" else "N/A"
        data['Brand'] = "Renewed" if fw.lower() == "renewed" else fw
    if data['Brand'].lower() == 'refurbished':
        data['Brand'] = "Renewed"

    # Seller
    data['Seller Name'] = extract_seller_info(soup)['seller_name']

    # Category (breadcrumbs)
    cats = [b.text.strip() for b in soup.select('.osh-breadcrumb a,.brcbs a,[class*="breadcrumb"] a')
            if b.text.strip()]
    data['Category'] = ' > '.join(cats) if cats else "N/A"

    # SKU
    sku_el = soup.find(attrs={'data-sku': True})
    if sku_el:
        sku_found = sku_el['data-sku']
    else:
        tc = soup.get_text()
        m = re.search(r'SKU[:\s]*([A-Z0-9]+NAFAM[A-Z])', tc) or \
            re.search(r'SKU[:\s]*([A-Z0-9\-]+)', tc)
        sku_found = m.group(1) if m else target.get('original_sku','N/A')
    data['SKU'] = clean_jumia_sku(sku_found)

    # Images
    data['Image URLs'] = []
    image_url = None
    gallery = soup.find('div', id='imgs') or \
               soup.find('div', class_=re.compile(r'\bsldr\b|\bgallery\b|-pas', re.I))
    scope = gallery if gallery else soup
    for img in scope.find_all('img'):
        src = (img.get('data-src') or img.get('src') or '').strip()
        if src and '/product/' in src and not src.startswith('data:'):
            if src.startswith('//'): src = 'https:' + src
            elif src.startswith('/'): src = 'https://www.jumia.co.ke' + src
            bm = re.search(r'(/product/[a-z0-9_/-]+\.(?:jpg|jpeg|png|webp))', src, re.I)
            bp = bm.group(1) if bm else src
            if not any(bp in eu for eu in data['Image URLs']):
                data['Image URLs'].append(src)
                if not image_url: image_url = src
        if not gallery and len(data['Image URLs']) >= 8: break
    data['Primary Image URL'] = image_url or "N/A"
    data['Total Product Images'] = len(data['Image URLs'])

    # Grading last image (dhash)
    data['Grading last image'] = 'NO'
    if data['Image URLs']:
        th = get_target_promo_hash()
        if th is not None:
            try:
                resp = requests.get(data['Image URLs'][-1], timeout=10)
                lh = get_dhash(Image.open(BytesIO(resp.content)))
                if lh is not None and np.count_nonzero(th != lh) <= 12:
                    data['Grading last image'] = 'YES'
            except Exception:
                pass

    # Refurbished status
    rs = detect_refurbished_status(soup, product_name)
    data['Is Refurbished']       = rs['is_refurbished']
    data['Has refurb tag']        = rs['has_refurb_tag']
    data['Refurbished Indicators'] = ', '.join(rs['refurb_indicators']) or 'None'
    if data['Brand'] == "Renewed":
        data['Is Refurbished'] = "YES"

    # Warranty
    wi = extract_warranty_info(soup, product_name)
    data['Has Warranty']     = wi['has_warranty']
    data['Warranty Duration'] = wi['warranty_duration']
    data['Warranty Source']   = wi['warranty_source']
    data['Warranty Address']  = wi['warranty_address']

    # Red badge
    if do_check_images and image_url and image_url != "N/A":
        data['grading tag'] = has_red_badge(image_url)
    else:
        data['grading tag'] = 'Not Checked'

    # Express
    if soup.find(['svg','img','span'], attrs={'aria-label': re.compile(r'Jumia Express', re.I)}):
        data['Express'] = "Yes"

    # Price
    pt = soup.find('span', class_=re.compile(r'price|prc|-b')) or \
         soup.find(['div','span'], string=re.compile(r'KSh\s*[\d,]+'))
    if pt:
        pm = re.search(r'KSh\s*([\d,]+)', pt.get_text())
        data['Price'] = 'KSh ' + pm.group(1) if pm else pt.get_text().strip()

    # Rating
    re_ = soup.find(['span','div'], class_=re.compile(r'rating|stars'))
    if re_:
        rm = re.search(r'([\d.]+)\s*out of\s*5', re_.get_text())
        if rm: data['Product Rating'] = rm.group(1) + '/5'

    # Infographics
    seen = set()
    for cont in soup.find_all('div', class_=re.compile(r'\bmarkup\b|product-desc|-mhm', re.I)):
        for img in cont.find_all('img'):
            src = (img.get('data-src') or img.get('src') or '').strip()
            if src and not src.startswith('data:') and len(src) >= 15 and '1x1' not in src:
                seen.add(src)
    if not seen:
        for img in soup.find_all('img'):
            src = (img.get('data-src') or img.get('src') or '').strip()
            if '/cms/external/' in src and not src.endswith('.svg'):
                seen.add(src)
    data['Infographic Image Count'] = len(seen)
    data['Has info-graphics'] = 'YES' if seen else 'NO'
    return data


def scrape_item(target, headless=True, timeout=20, do_check_images=True):
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = None
    url = target['value']
    is_sku = target['type'] == 'sku'
    data = {
        'Input Source': target.get('original_sku', url),
        'Product Name':'N/A','Brand':'N/A','Seller Name':'N/A','Category':'N/A',
        'SKU':'N/A','Is Refurbished':'NO','Has refurb tag':'NO',
        'Refurbished Indicators':'None','Has Warranty':'NO','Warranty Duration':'N/A',
        'Warranty Source':'None','Warranty Address':'N/A','grading tag':'Not Checked',
        'Primary Image URL':'N/A','Image URLs':[],'Total Product Images':0,
        'Grading last image':'NO','Price':'N/A','Product Rating':'N/A',
        'Express':'No','Has info-graphics':'NO','Infographic Image Count':0
    }
    try:
        driver = get_driver(headless, timeout)
        if not driver:
            data['Product Name'] = 'SYSTEM_ERROR'; return data
        try:
            driver.get(url)
        except TimeoutException:
            data['Product Name'] = 'TIMEOUT'; return data
        except WebDriverException:
            data['Product Name'] = 'CONNECTION_ERROR'; return data

        if is_sku:
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
                if "There are no results for" in driver.page_source:
                    data['Product Name'] = "SKU_NOT_FOUND"; return data
                links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                if links:
                    try: driver.get(links[0].get_attribute("href"))
                    except TimeoutException:
                        data['Product Name'] = 'TIMEOUT'; return data
            except (TimeoutException, Exception):
                pass

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "h1")))
        except TimeoutException:
            data['Product Name'] = 'TIMEOUT'; return data

        for step in [800, 1600, 2400, 3200]:
            try: driver.execute_script(f"window.scrollTo(0, {step});"); time.sleep(0.5)
            except: pass

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = extract_product_data(soup, data, is_sku, target, do_check_images)
    except TimeoutException:
        data['Product Name'] = "TIMEOUT"
    except WebDriverException:
        data['Product Name'] = "CONNECTION_ERROR"
    except Exception:
        data['Product Name'] = "ERROR_FETCHING"
    finally:
        if driver:
            try: driver.quit()
            except: pass
    return data


def scrape_parallel(targets, n_workers, headless=True, timeout=20, do_check=True):
    results, failed = [], []
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        fs = {ex.submit(scrape_item, t, headless, timeout, do_check): t for t in targets}
        for f in as_completed(fs):
            t = fs[f]
            try:
                r = f.result()
                if r['Product Name'] in ["SYSTEM_ERROR","TIMEOUT","CONNECTION_ERROR"]:
                    failed.append({'input': t.get('original_sku', t['value']),
                                   'error': r['Product Name']})
                elif r['Product Name'] != "SKU_NOT_FOUND":
                    results.append(r)
            except Exception as e:
                failed.append({'input': t.get('original_sku', t['value']), 'error': str(e)})
    return results, failed


def process_inputs(text_input, file_input, d):
    raw = set()
    if text_input:
        raw.update(i.strip() for i in re.split(r'[\n,]', text_input) if i.strip())
    if file_input:
        try:
            df = pd.read_excel(file_input, header=None) \
                 if file_input.name.endswith('.xlsx') else pd.read_csv(file_input, header=None)
            raw.update(str(c).strip() for c in df.values.flatten()
                       if str(c).strip() and str(c).lower() != 'nan')
        except Exception as e:
            st.error(f"File read error: {e}")
    targets = []
    for item in raw:
        v = item.replace("SKU:", "").strip()
        if "http" in v or "www." in v:
            if not v.startswith("http"): v = "https://" + v
            targets.append({"type": "url", "value": v})
        elif len(v) > 3:
            targets.append({"type":"sku","value":f"https://www.{d}/catalog/?q={v}",
                            "original_sku":v})
    return targets


# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE INIT
# ══════════════════════════════════════════════════════════════════════════════
for key in ['scraped_results','failed_items','last_image_hash','individual_scales']:
    if key not in st.session_state:
        st.session_state[key] = [] if key in ['scraped_results','failed_items'] else \
                                  {} if key == 'individual_scales' else None


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_analyze, tab_tag_single, tab_tag_bulk, tab_convert = st.tabs([
    "🔍 Analyze Products",
    "🖼️ Tag — Single Image",
    "📦 Tag — Bulk",
    "🔄 Convert Tag"
])


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  TAB 1 — ANALYZE PRODUCTS                                               │
# └─────────────────────────────────────────────────────────────────────────┘
with tab_analyze:
    st.subheader(f"Analyze Jumia Products  ·  {region_choice}")
    st.markdown("Enter SKUs, product URLs, or a category page to bulk-analyze listings.")

    col_txt, col_upl = st.columns(2)
    with col_txt:
        text_in = st.text_area(
            "Paste SKUs / Links:",
            height=100,
            placeholder="One SKU or URL per line\nExample: SA948MP5EER52NAFAMZ",
            key="analyze_text"
        )
    with col_upl:
        file_in = st.file_uploader("Upload Excel/CSV with SKUs:", type=['xlsx','csv'],
                                   key="analyze_file")

    cat_url_in = st.text_input(
        "🌐 Category URL (extracts all products on page):",
        placeholder=f"https://www.{domain}/smartphones/",
        key="analyze_cat"
    )

    st.markdown("---")

    if st.button("▶️ Start Analysis", type="primary", key="analyze_run"):
        targets = process_inputs(text_in, file_in, domain)

        if cat_url_in:
            with st.spinner("Extracting product links from category page…"):
                links = extract_category_links(cat_url_in, not show_browser, timeout_seconds)
                for lnk in links:
                    targets.append({"type":"url","value":lnk,"original_sku":lnk})
                if links:
                    st.success(f"Extracted {len(links)} products from category URL.", icon="✅")
                else:
                    st.warning("No product links found on that category URL.", icon="⚠️")

        if not targets:
            st.warning("No valid input found. Please enter SKUs, URLs, or a Category URL.", icon="⚠️")
        else:
            st.session_state['scraped_results'] = []
            st.session_state['failed_items']    = []

            prog    = st.progress(0)
            status  = st.empty()
            details = st.empty()
            preview = st.empty()

            status.text(f"Analyzing {len(targets)} products…")
            t0 = time.time()
            batch_size   = max_workers * 2
            all_results  = []
            all_failed   = []
            processed    = 0

            for i in range(0, len(targets), batch_size):
                batch = targets[i:i+batch_size]
                b_num = i // batch_size + 1
                b_tot = (len(targets) + batch_size - 1) // batch_size
                details.info(f"Batch {b_num}/{b_tot}  ({len(batch)} items)", icon="📦")

                br, bf = scrape_parallel(batch, max_workers, not show_browser,
                                         timeout_seconds, check_images)
                all_results.extend(br)
                all_failed.extend(bf)
                processed += len(batch)
                prog.progress(min(processed / len(targets), 1.0))
                elapsed = time.time() - t0
                rem = (len(targets) - processed) * (elapsed / processed) if processed else 0
                status.text(
                    f"Processed {processed}/{len(targets)}  "
                    f"({processed/elapsed:.1f}/s)  |  Est. remaining: {rem:.0f}s"
                )
                if br:
                    li = br[-1]
                    with preview.container():
                        c1, c2 = st.columns([1,3])
                        with c1:
                            if li.get('Primary Image URL','N/A') != 'N/A':
                                try: st.image(li['Primary Image URL'], width=150)
                                except: pass
                        with c2:
                            st.caption(f"**Last:** {li.get('Product Name','N/A')[:60]}")
                            st.caption(
                                f"Images: {li.get('Total Product Images',0)}  |  "
                                f"Refurb: {li.get('Is Refurbished','NO')}  |  "
                                f"Grading img: {li.get('Grading last image','NO')}"
                            )

            elapsed = time.time() - t0
            st.session_state['scraped_results'] = all_results
            st.session_state['failed_items']    = all_failed
            details.empty(); preview.empty()

            if all_failed:
                status.warning(
                    f"Done: {len(all_results)} ok, {len(all_failed)} failed "
                    f"({elapsed:.1f}s)", icon="⚠️")
            else:
                status.success(
                    f"Done! {len(targets)} products in {elapsed:.1f}s "
                    f"({len(targets)/elapsed:.1f}/s)", icon="✅")
            time.sleep(2)
            st.rerun()

    # ── Results display ──────────────────────────────────────────────────────
    if st.session_state['failed_items']:
        with st.expander(f"Failed Items ({len(st.session_state['failed_items'])})", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state['failed_items']), use_container_width=True)

    if st.session_state['scraped_results']:
        df = pd.DataFrame(st.session_state['scraped_results'])
        priority_cols = [
            'SKU','Product Name','Brand','Is Refurbished','Has refurb tag',
            'Has Warranty','Warranty Duration','Total Product Images',
            'Grading last image','grading tag','Has info-graphics','Infographic Image Count',
            'Seller Name','Price','Product Rating','Express','Category',
            'Refurbished Indicators','Warranty Source','Warranty Address',
            'Primary Image URL','Input Source'
        ]
        df = df[[c for c in priority_cols if c in df.columns]]

        st.subheader("📊 Summary")
        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("Total Analyzed", len(df))
        m2.metric("Refurbished",    int((df['Is Refurbished']=='YES').sum()))
        m3.metric("Grading Image",  int((df.get('Grading last image','NO')=='YES').sum()))
        m4.metric("Red Badges",     int(df.get('grading tag','').str.contains('YES',na=False).sum()))
        m5.metric("Avg Images",     f"{df.get('Total Product Images',pd.Series([0])).mean():.1f}")

        st.markdown("---")
        st.subheader("🖼️ Product Gallery")
        gcol, fcol = st.columns([3,1])
        with fcol:
            view_mode      = st.radio("View:", ["Grid","List"], horizontal=True, key="view_mode")
            show_refurb_only = st.checkbox("Refurbished only", key="refurb_filter")
        display_df = df[df['Is Refurbished']=='YES'] if show_refurb_only else df

        if view_mode == "Grid":
            for row in range((len(display_df)+3)//4):
                cols = st.columns(4)
                for ci in range(4):
                    idx = row*4+ci
                    if idx < len(display_df):
                        item = display_df.iloc[idx]
                        with cols[ci]:
                            url_ = item.get('Primary Image URL','N/A')
                            try: st.image(url_ if url_ != 'N/A' else
                                          "https://via.placeholder.com/200x200?text=No+Image",
                                          use_container_width=True)
                            except: st.image("https://via.placeholder.com/200x200?text=No+Image",
                                             use_container_width=True)
                            st.caption(f"**{item.get('Brand','N/A')}**")
                            pn = item.get('Product Name','N/A')
                            st.caption(pn[:50]+"…" if len(pn)>50 else pn)
                            badges = []
                            if item.get('Is Refurbished')=='YES': badges.append("[Refurb]")
                            if item.get('Grading last image')=='YES': badges.append("[Grade Img]")
                            n_img = item.get('Total Product Images',0)
                            if n_img: badges.append(f"[{n_img} imgs]")
                            if badges: st.caption(" · ".join(badges))
                            st.caption(f"**{item.get('Price','N/A')}**")
                            with st.expander("Details"):
                                st.caption(f"SKU: {item.get('SKU','N/A')}")
                                st.caption(f"Seller: {item.get('Seller Name','N/A')}")
        else:
            for _, item in display_df.iterrows():
                with st.container():
                    c1, c2 = st.columns([1,4])
                    with c1:
                        url_ = item.get('Primary Image URL','N/A')
                        try: st.image(url_ if url_!='N/A' else
                                      "https://via.placeholder.com/150x150?text=No+Image", width=150)
                        except: pass
                    with c2:
                        st.markdown(f"**{item.get('Product Name','N/A')}**")
                        r1 = st.columns(5)
                        r1[0].caption(f"**Brand:** {item.get('Brand','N/A')}")
                        r1[1].caption(f"**Refurb:** {item.get('Is Refurbished','NO')}")
                        r1[2].caption(f"**Grade Img:** {item.get('Grading last image','NO')}")
                        r1[3].caption(f"**Price:** {item.get('Price','N/A')}")
                        r1[4].caption(f"**Images:** {item.get('Total Product Images',0)}")
                        r2 = st.columns(3)
                        r2[0].caption(f"**Seller:** {item.get('Seller Name','N/A')}")
                        r2[1].caption(f"**SKU:** {item.get('SKU','N/A')}")
                        r2[2].caption(f"**Warranty:** {item.get('Warranty Duration','N/A')}")
                    st.divider()

        if (df['Is Refurbished']=='YES').any():
            st.markdown("---")
            st.markdown("### ♻️ Refurbished Items Detail")
            st.dataframe(df[df['Is Refurbished']=='YES'], use_container_width=True)

        st.markdown("---")
        st.markdown("### 📋 Full Results")

        def highlight_renewed(row):
            return ['background-color:#fffacd']*len(row) if row.get('Brand')=='Renewed' else ['']*len(row)

        try:
            st.dataframe(df.style.apply(highlight_renewed, axis=1), use_container_width=True)
        except:
            st.dataframe(df, use_container_width=True)

        st.download_button(
            "⬇️ Download CSV",
            df.to_csv(index=False).encode('utf-8'),
            f"analysis_{int(time.time())}.csv",
            "text/csv",
            key='dl_csv'
        )


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  TAB 2 — TAG: SINGLE IMAGE                                              │
# └─────────────────────────────────────────────────────────────────────────┘
with tab_tag_single:
    st.subheader(f"Tag — Single Image  ·  Grade: **{tag_type}**")
    st.markdown(f"Applying tag to products from **{region_choice}** · Scale: **{image_scale}%**")

    col_in, col_out = st.columns([1,1])
    with col_in:
        st.markdown("#### Image Source")
        src_method = st.radio(
            "Source:",
            ["Upload from device","Load from Image URL","Load from SKU"],
            horizontal=True, key="single_src"
        )
        product_image = None

        if src_method == "Upload from device":
            f = st.file_uploader("Choose image:", type=["png","jpg","jpeg","webp"],
                                  key="single_upload")
            if f:
                fhash = hashlib.md5(f.getvalue()).hexdigest()
                if st.session_state.last_image_hash != fhash:
                    st.session_state.last_image_hash = fhash
                    st.session_state.image_scale_value = 100
                product_image = Image.open(f).convert("RGBA")

        elif src_method == "Load from Image URL":
            url_ = st.text_input("Image URL:", key="single_url")
            if url_:
                try:
                    if st.session_state.last_image_hash != url_:
                        st.session_state.last_image_hash = url_
                        st.session_state.image_scale_value = 100
                    product_image = Image.open(BytesIO(requests.get(url_).content)).convert("RGBA")
                    st.success("Image loaded!")
                except Exception as e:
                    st.error(f"Could not load image: {e}")

        else:  # SKU
            sku_ = st.text_input("Product SKU:", placeholder="e.g. GE840EA6C62GANAFAMZ",
                                  key="single_sku")
            st.caption(f"Will search on **{base_url}**")
            if sku_:
                if st.button("🔍 Search & Extract Image", use_container_width=True, key="single_search"):
                    with st.spinner("Searching…"):
                        product_image = search_jumia_by_sku(
                            sku_, base_url, f"{base_url}/catalog/?q={sku_}")
                        if product_image:
                            st.success("Image found!")
                        else:
                            st.error("Could not find product.")

    with col_out:
        st.markdown("#### Preview")
        if product_image is not None:
            tp = get_tag_path(TAG_FILES[tag_type])
            if not os.path.exists(tp):
                st.error(f"Tag file not found: **{TAG_FILES[tag_type]}**")
                st.stop()
            tag_img = Image.open(tp).convert("RGBA")
            result  = process_single(product_image, tag_img, image_scale)
            st.image(result, use_container_width=True, caption=f"Grade: {tag_type}")
            st.markdown("---")
            st.download_button(
                label=f"⬇️ Download Tagged Image (JPEG)",
                data=image_to_bytes(result),
                file_name=f"tagged_{tag_type.lower().replace(' ','_')}.jpg",
                mime="image/jpeg",
                use_container_width=True,
                key="single_dl"
            )
        else:
            st.info("← Load an image to see the preview here.")


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  TAB 3 — TAG: BULK                                                      │
# └─────────────────────────────────────────────────────────────────────────┘
with tab_tag_bulk:
    st.subheader(f"Tag — Bulk Processing  ·  Grade: **{tag_type}**")
    st.markdown("Images are **auto-cropped and fitted** — no manual adjustment needed (but per-image scale controls are available).")

    bulk_method = st.radio(
        "Input method:",
        ["Upload multiple images","Enter URLs manually","Upload Excel file with URLs","Enter SKUs"],
        key="bulk_method"
    )
    products_to_process = []

    if bulk_method == "Upload multiple images":
        files = st.file_uploader("Choose image files:",
                                  type=["png","jpg","jpeg","webp"],
                                  accept_multiple_files=True, key="bulk_upload")
        if files:
            st.info(f"{len(files)} files uploaded")
            for f in files:
                try:
                    products_to_process.append((Image.open(f).convert("RGBA"),
                                                f.name.rsplit(".",1)[0]))
                except Exception as e:
                    st.warning(f"Could not load {f.name}: {e}")

    elif bulk_method == "Enter URLs manually":
        raw = st.text_area("Image URLs (one per line):", height=180,
                            placeholder="https://example.com/image1.jpg",
                            key="bulk_urls")
        if raw.strip():
            for i, u in enumerate(u.strip() for u in raw.splitlines() if u.strip()):
                try:
                    r = requests.get(u, timeout=10); r.raise_for_status()
                    products_to_process.append((Image.open(BytesIO(r.content)).convert("RGBA"),
                                                f"image_{i+1}"))
                except Exception as e:
                    st.warning(f"URL {i+1}: {e}")

    elif bulk_method == "Upload Excel file with URLs":
        st.markdown("**Column A:** Image URLs  ·  **Column B (optional):** Product name")
        xf = st.file_uploader("Excel file:", type=["xlsx","xls"], key="bulk_excel")
        if xf:
            try:
                df_xl = pd.read_excel(xf)
                urls  = df_xl.iloc[:,0].dropna().astype(str).tolist()
                names = (df_xl.iloc[:,1].dropna().astype(str).tolist()
                         if len(df_xl.columns) > 1
                         else [f"product_{i+1}" for i in range(len(urls))])
                st.info(f"Found {len(urls)} URLs")
                for i,(u,n) in enumerate(zip(urls,names)):
                    try:
                        r = requests.get(u, timeout=10); r.raise_for_status()
                        clean = re.sub(r"[^\w\s-]","",n).strip().replace(" ","_")
                        products_to_process.append((Image.open(BytesIO(r.content)).convert("RGBA"),
                                                    clean or f"product_{i+1}"))
                    except Exception as e:
                        st.warning(f"Could not load {n}: {e}")
            except Exception as e:
                st.error(f"Excel error: {e}")

    else:  # SKUs
        skus_raw = st.text_area("SKUs (one per line):", height=180,
                                 placeholder="GE840EA6C62GANAFAMZ", key="bulk_skus")
        st.caption(f"Will search on **{base_url}**")
        if skus_raw.strip():
            skus = [s.strip() for s in skus_raw.splitlines() if s.strip()]
            st.info(f"{len(skus)} SKUs entered")
            if st.button("🔍 Search All SKUs", use_container_width=True, key="bulk_search"):
                prog   = st.progress(0)
                status = st.empty()
                for i, sku in enumerate(skus):
                    status.text(f"Processing {i+1}/{len(skus)}: {sku}")
                    img_ = search_jumia_by_sku(sku, base_url,
                                               f"{base_url}/catalog/?q={sku}")
                    if img_:
                        products_to_process.append((img_, sku))
                    else:
                        st.warning(f"No image for SKU: {sku}")
                    prog.progress((i+1)/len(skus))
                status.text(f"Done — {len(products_to_process)}/{len(skus)} found")

    # ── Review grid with per-image scale sliders ──────────────────────────
    if products_to_process:
        st.markdown("---")
        st.subheader(f"{len(products_to_process)} images ready — adjust sizes if needed")
        cols_per_row = 4
        for row_s in range(0, len(products_to_process), cols_per_row):
            cols = st.columns(cols_per_row)
            for ci, (img_, name_) in enumerate(
                    products_to_process[row_s:row_s+cols_per_row]):
                with cols[ci]:
                    st.image(img_.convert("RGB"), caption=name_, use_container_width=True)
                    k = f"bscale_{row_s+ci}_{name_}"
                    if k not in st.session_state.individual_scales:
                        st.session_state.individual_scales[k] = 100
                    sc = st.slider("Size %", 50, 200,
                                   st.session_state.individual_scales[k],
                                   step=5, key=f"sl_{k}",
                                   label_visibility="collapsed")
                    st.session_state.individual_scales[k] = sc
                    st.caption(f"{sc}%")

        st.markdown("---")
        if st.button("⚙️ Process All Images", use_container_width=True, key="bulk_process"):
            tp = get_tag_path(TAG_FILES[tag_type])
            if not os.path.exists(tp):
                st.error(f"Tag file not found: {TAG_FILES[tag_type]}")
                st.stop()
            tag_img   = Image.open(tp).convert("RGBA")
            prog      = st.progress(0)
            processed = []
            for i, (raw_img, name_) in enumerate(products_to_process):
                try:
                    k  = f"bscale_{i}_{name_}"
                    sc = st.session_state.individual_scales.get(k, 100)
                    processed.append((process_single(raw_img, tag_img, sc), name_))
                except Exception as e:
                    st.warning(f"Error on {name_}: {e}")
                prog.progress((i+1)/len(products_to_process))

            if processed:
                st.success(f"✅ {len(processed)} images processed!")
                zb = BytesIO()
                with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
                    for img_, name_ in processed:
                        zf.writestr(f"{name_}_1.jpg", image_to_bytes(img_))
                zb.seek(0)
                st.download_button(
                    f"⬇️ Download All {len(processed)} Images (ZIP)",
                    zb,
                    f"tagged_{tag_type.lower().replace(' ','_')}.zip",
                    "application/zip",
                    use_container_width=True,
                    key="bulk_dl"
                )
                st.markdown("### Preview")
                pcols = st.columns(4)
                for i, (img_, name_) in enumerate(processed[:8]):
                    with pcols[i%4]:
                        st.image(img_, caption=name_, use_container_width=True)
                if len(processed) > 8:
                    st.caption(f"Showing 8 of {len(processed)}")
            else:
                st.error("No images were successfully processed.")
    else:
        st.info("Provide images above to get started.")


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  TAB 4 — CONVERT TAG                                                    │
# └─────────────────────────────────────────────────────────────────────────┘
with tab_convert:
    st.subheader(f"Convert Tag  →  **{tag_type}**")
    st.markdown(
        "Upload images that **already have a refurbished tag** applied. "
        "The app will auto-detect and strip the old tag, then apply the grade "
        "selected in the sidebar."
    )

    conv_mode = st.radio(
        "Input method:",
        ["Single image","Multiple images"],
        horizontal=True, key="conv_mode"
    )
    images_to_convert = []

    if conv_mode == "Single image":
        c1, c2 = st.columns([1,1])
        with c1:
            st.markdown("#### Upload tagged image")
            cf = st.file_uploader("Choose tagged image:",
                                   type=["png","jpg","jpeg","webp"],
                                   key="conv_single")
            if cf:
                images_to_convert = [(Image.open(cf).convert("RGB"),
                                      cf.name.rsplit(".",1)[0])]
        with c2:
            st.markdown("#### Result")
            if images_to_convert:
                tagged_img, fname_ = images_to_convert[0]
                tp = get_tag_path(TAG_FILES[tag_type])
                if not os.path.exists(tp):
                    st.error(f"Tag file not found: **{TAG_FILES[tag_type]}**")
                    st.stop()
                new_tag = Image.open(tp).convert("RGBA")
                result  = strip_and_retag(tagged_img, new_tag)
                bc, ac  = st.columns(2)
                bc.image(tagged_img, caption="Before (old tag)", use_container_width=True)
                ac.image(result,     caption=f"After → {tag_type}", use_container_width=True)
                st.markdown("---")
                st.download_button(
                    f"⬇️ Download as {tag_type} (JPEG)",
                    image_to_bytes(result),
                    f"{fname_}_{tag_type.lower().replace(' ','_')}.jpg",
                    "image/jpeg",
                    use_container_width=True,
                    key="conv_single_dl"
                )
            else:
                st.info("← Upload a tagged image to see the conversion.")

    else:  # Multiple images
        st.markdown("#### Upload tagged images")
        conv_files = st.file_uploader(
            "Choose tagged images:",
            type=["png","jpg","jpeg","webp"],
            accept_multiple_files=True, key="conv_bulk"
        )
        if conv_files:
            st.info(f"{len(conv_files)} files uploaded")
            for f in conv_files:
                try:
                    images_to_convert.append((Image.open(f).convert("RGB"),
                                              f.name.rsplit(".",1)[0]))
                except Exception as e:
                    st.warning(f"Could not load {f.name}: {e}")

        if images_to_convert:
            st.markdown("**Originals (with old tags):**")
            for rs in range(0, len(images_to_convert), 4):
                cols = st.columns(4)
                for ci, (img_, name_) in enumerate(images_to_convert[rs:rs+4]):
                    with cols[ci]:
                        st.image(img_, caption=name_, use_container_width=True)

            st.markdown("---")
            if st.button(f"🔄 Convert All → {tag_type}", use_container_width=True,
                          key="conv_bulk_btn"):
                tp = get_tag_path(TAG_FILES[tag_type])
                if not os.path.exists(tp):
                    st.error(f"Tag file not found: {TAG_FILES[tag_type]}")
                    st.stop()
                new_tag   = Image.open(tp).convert("RGBA")
                prog      = st.progress(0)
                converted = []
                for i, (tagged_img, name_) in enumerate(images_to_convert):
                    try:
                        converted.append((strip_and_retag(tagged_img, new_tag), name_))
                    except Exception as e:
                        st.warning(f"Error on {name_}: {e}")
                    prog.progress((i+1)/len(images_to_convert))

                if converted:
                    st.success(f"✅ {len(converted)} images converted to {tag_type}!")
                    zb = BytesIO()
                    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
                        for img_, name_ in converted:
                            zf.writestr(
                                f"{name_}_{tag_type.lower().replace(' ','_')}.jpg",
                                image_to_bytes(img_))
                    zb.seek(0)
                    st.download_button(
                        f"⬇️ Download All {len(converted)} Converted Images (ZIP)",
                        zb,
                        f"converted_{tag_type.lower().replace(' ','_')}.zip",
                        "application/zip",
                        use_container_width=True,
                        key="conv_bulk_dl"
                    )
                    st.markdown("### Preview")
                    pcols = st.columns(4)
                    for i, (img_, name_) in enumerate(converted[:8]):
                        with pcols[i%4]:
                            st.image(img_, caption=name_, use_container_width=True)
                    if len(converted) > 8:
                        st.caption(f"Showing 8 of {len(converted)}")
                else:
                    st.error("No images were successfully converted.")
        else:
            st.info("Upload tagged images above to get started.")


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#888;font-size:0.85rem'>"
    "Auto-crop trims whitespace · 12% margin keeps product clear of tag borders · "
    "Pixel-scan strips old tags cleanly"
    "</div>",
    unsafe_allow_html=True,
)
