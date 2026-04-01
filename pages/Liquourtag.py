import streamlit as st
from PIL import Image
import requests
from io import BytesIO
import numpy as np
import os
import re
import zipfile
import shutil
import concurrent.futures
import pandas as pd
import time
from bs4 import BeautifulSoup

# ─── Page Config ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="18+ Tag Generator", page_icon=None, layout="wide")

# Jumia brand palette
# Primary orange: #F68B1E  |  Dark: #1A1A1A  |  Light bg: #FFF8F2  |  Border: #F0D5B8
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    * { font-family: 'DM Sans', sans-serif; }

    [data-testid="stAppViewContainer"] {
        background: #FFF8F2;
    }
    [data-testid="stSidebar"] {
        background: #1A1A1A !important;
        border-right: none;
    }
    [data-testid="stSidebar"] * { color: #fff !important; }
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stCheckbox label { color: #ccc !important; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #aaa !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #F68B1E !important; }

    /* Sidebar radio + checkbox accent */
    [data-testid="stSidebar"] [data-baseweb="radio"] [data-testid="stMarkdownContainer"] p { color: #fff !important; }
    [data-testid="stSidebar"] input[type="radio"]:checked + div { border-color: #F68B1E !important; }
    [data-testid="stSidebar"] [data-baseweb="checkbox"] svg { fill: #F68B1E !important; }

    /* Header */
    h1 {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #1A1A1A !important;
        letter-spacing: -0.02em;
        margin-bottom: 0 !important;
    }
    .subhead {
        color: #888;
        font-size: 0.85rem;
        margin-top: 3px;
        margin-bottom: 1.4rem;
    }
    .orange-bar {
        height: 3px;
        background: linear-gradient(90deg, #F68B1E, #ffb347);
        border-radius: 2px;
        margin-bottom: 1.2rem;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 2px solid #F0D5B8;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 500;
        font-size: 0.875rem;
        padding: 10px 20px;
        color: #888;
        border-radius: 0;
        background: transparent;
    }
    .stTabs [aria-selected="true"] {
        color: #F68B1E !important;
        border-bottom: 2px solid #F68B1E !important;
        font-weight: 700 !important;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"]:hover { color: #F68B1E !important; }

    /* Primary buttons — orange */
    .stButton > button[kind="primary"] {
        background: #F68B1E !important;
        color: #fff !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 700 !important;
        letter-spacing: 0.01em;
        padding: 0.55rem 1.2rem;
        transition: background 0.15s;
    }
    .stButton > button[kind="primary"]:hover { background: #d97710 !important; }

    /* Secondary buttons */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 600 !important;
        border: 1.5px solid #F68B1E !important;
        color: #F68B1E !important;
        background: transparent !important;
    }
    .stButton > button:hover { background: #FFF0E0 !important; }

    /* Download buttons */
    .stDownloadButton > button {
        border-radius: 6px !important;
        font-weight: 700 !important;
        background: #F68B1E !important;
        color: #fff !important;
        border: none !important;
    }
    .stDownloadButton > button:hover { background: #d97710 !important; }

    /* Secondary download (originals) */
    .orig-dl .stDownloadButton > button {
        background: transparent !important;
        color: #F68B1E !important;
        border: 1.5px solid #F68B1E !important;
    }
    .orig-dl .stDownloadButton > button:hover { background: #FFF0E0 !important; }

    /* Progress bar */
    [data-testid="stProgressBar"] > div > div { background: #F68B1E !important; }

    /* Images */
    div[data-testid="stImage"] img {
        border: 1.5px solid #F0D5B8;
        border-radius: 6px;
    }

    /* Alerts */
    .stAlert { border-radius: 6px !important; }
    [data-testid="stAlert"][data-baseweb="notification"] {
        border-left: 4px solid #F68B1E !important;
    }

    /* File uploader */
    [data-testid="stFileUploader"] section {
        border: 2px dashed #F0D5B8 !important;
        border-radius: 8px !important;
        background: #FFFAF5 !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: #F68B1E !important;
        background: #FFF5EA !important;
    }

    /* Text inputs */
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
        border: 1.5px solid #F0D5B8 !important;
        border-radius: 6px !important;
        background: #FFFAF5 !important;
    }
    [data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus {
        border-color: #F68B1E !important;
        box-shadow: 0 0 0 2px rgba(246,139,30,0.15) !important;
    }

    /* Caption text */
    .stCaption { color: #888 !important; font-size: 0.78rem !important; }

    /* Spinner */
    [data-testid="stSpinner"] { color: #F68B1E !important; }

    div[data-testid="stMarkdownContainer"] h3 {
        font-weight: 700 !important;
        color: #1A1A1A !important;
        font-size: 0.95rem !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    /* Empty preview placeholder */
    .preview-empty {
        height: 240px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px dashed #F0D5B8;
        border-radius: 8px;
        color: #bbb;
        font-size: 0.875rem;
        background: #FFFAF5;
    }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────────
TAG_FILE = "NSFW-18++-Tag.png"
TARGET_CANVAS_SIZE = (800, 800)
VERTICAL_PADDING = 50

# ─── Session State ────────────────────────────────────────────────────────────────
for key, default in [("single_result", None), ("single_name", "tagged_image.jpg")]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Tag File Check ───────────────────────────────────────────────────────────────
TAG_PATH = TAG_FILE if os.path.exists(TAG_FILE) else os.path.join(os.path.dirname(__file__), TAG_FILE)
TAG_MISSING = not os.path.exists(TAG_PATH)

# ─── Sidebar ──────────────────────────────────────────────────────────────────────
st.sidebar.markdown("## Settings")
st.sidebar.markdown("---")
remove_old_tags = st.sidebar.checkbox(
    "Remove existing 18+ tags", value=True,
    help="Scans the top-right corner for a previous red tag and removes it before applying the new one."
)
st.sidebar.markdown("---")
st.sidebar.markdown("**Marketplace region**")
marketplace = st.sidebar.radio(
    "Region", ["Kenya", "Uganda"], label_visibility="collapsed"
)
MARKET_BASE = "https://www.jumia.co.ke" if marketplace == "Kenya" else "https://www.jumia.ug"

st.sidebar.markdown("---")
st.sidebar.markdown(
    '<p style="font-size:0.75rem;color:#666;margin-top:8px;">18+ Tag Generator v3.0</p>',
    unsafe_allow_html=True
)

# ─── Core Image Functions ─────────────────────────────────────────────────────────

def remove_existing_tag(img):
    img_rgb = img.convert('RGB') if img.mode != 'RGB' else img.copy()
    data = np.array(img_rgb)
    h, w, _ = data.shape
    sh, sw = int(h * 0.35), int(w * 0.35)
    tr = data[0:sh, w - sw:w]
    red_mask = (
        (tr[:, :, 0] > 160) & (tr[:, :, 1] < 80) & (tr[:, :, 2] < 80) &
        (tr[:, :, 0].astype(int) - tr[:, :, 1].astype(int) > 100)
    )
    if np.sum(red_mask) > 30:
        coords = np.argwhere(red_mask)
        y0, x0 = coords.min(axis=0)
        y1, x1 = coords.max(axis=0)
        pad = 25
        y0, x0 = max(0, y0 - pad), max(0, x0 - pad)
        y1, x1 = min(sh, y1 + pad), min(sw, x1 + pad)
        data[y0:y1, (w - sw) + x0:(w - sw) + x1] = [255, 255, 255]
        if img.mode == 'RGBA':
            orig = np.array(img)
            orig[:, :, 0:3] = data
            return Image.fromarray(orig, 'RGBA')
        return Image.fromarray(data, 'RGB')
    return img


def crop_white_space(img):
    if img.mode == 'RGBA':
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        arr = np.array(bg)
    else:
        arr = np.array(img.convert('RGB'))
    mask = arr < 245
    if not mask.any():
        return img
    coords = np.argwhere(mask.any(axis=-1))
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    return img.crop((x0, y0, x1, y1))


@st.cache_resource
def load_tag_image():
    if TAG_MISSING:
        return None
    tag = Image.open(TAG_PATH).convert("RGBA")
    if tag.size != TARGET_CANVAS_SIZE:
        tag = tag.resize(TARGET_CANVAS_SIZE, Image.Resampling.LANCZOS)
    return tag


def compose_image(product_img, tag_img, apply_remove=True):
    img = product_img.copy()
    if apply_remove:
        img = remove_existing_tag(img)
    img = crop_white_space(img)
    cw, ch = TARGET_CANVAS_SIZE
    avail_h = ch - 2 * VERTICAL_PADDING
    avail_w = cw - 2 * VERTICAL_PADDING
    sw, sh = img.size
    scale = avail_h / sh
    nw, nh = int(sw * scale), avail_h
    if nw > avail_w:
        scale = avail_w / sw
        nw, nh = avail_w, int(sh * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    result = Image.new("RGB", TARGET_CANVAS_SIZE, (255, 255, 255))
    px = (cw - nw) // 2
    py = VERTICAL_PADDING
    if img.mode == 'RGBA':
        result.paste(img, (px, py), img)
    else:
        result.paste(img, (px, py))
    result.paste(tag_img, (0, 0), tag_img)
    return result


def img_to_bytes(img, fmt="JPEG"):
    buf = BytesIO()
    img.save(buf, format=fmt, quality=95) if fmt == "JPEG" else img.save(buf, format=fmt)
    return buf.getvalue()


def build_zip(pairs, fmt="JPEG"):
    ext = "jpg" if fmt == "JPEG" else fmt.lower()
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for img, name in pairs:
            zf.writestr(f"{name}.{ext}", img_to_bytes(img, fmt))
    return buf.getvalue()


def process_bulk(products, tag):
    results = []
    for img, name, is_device in products:
        result = compose_image(img, tag, apply_remove=remove_old_tags)
        final_name = name if is_device else f"{name}_1"
        results.append((result, final_name))
    return results


def show_grid_and_download(results, originals=None, zip_name="tagged_images.zip"):
    cols_per_row = 4
    for i in range(0, len(results), cols_per_row):
        row_imgs = results[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (img, name) in zip(cols, row_imgs):
            col.image(img, caption=name, use_container_width=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    dl_col, orig_col = st.columns(2)
    with dl_col:
        st.download_button(
            f"Download {len(results)} Tagged Image(s)",
            build_zip(results),
            zip_name, "application/zip",
            use_container_width=True, type="primary"
        )
    if originals:
        with orig_col:
            st.markdown('<div class="orig-dl">', unsafe_allow_html=True)
            st.download_button(
                f"Download {len(originals)} Original(s)",
                build_zip(originals),
                zip_name.replace(".zip", "_originals.zip"),
                "application/zip",
                use_container_width=True
            )
            st.markdown('</div>', unsafe_allow_html=True)


# ─── Selenium / Scraping Helpers ──────────────────────────────────────────────────

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


def get_chrome_options():
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-logging")
    opts.add_argument("--log-level=3")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    for binary in ["chromium", "chromium-browser", "google-chrome-stable", "google-chrome"]:
        path = shutil.which(binary)
        if path:
            opts.binary_location = path
            break
    return opts


def get_driver():
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        return None
    opts = get_chrome_options()
    try:
        dp = get_driver_path()
        svc = Service(dp, log_path=os.devnull) if dp else None
        driver = webdriver.Chrome(service=svc, options=opts) if svc else webdriver.Chrome(options=opts)
    except Exception as e:
        st.warning(f"Browser driver unavailable: {e}")
        return None
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.set_page_load_timeout(20)
        driver.implicitly_wait(5)
    except Exception:
        pass
    return driver


def search_by_sku(sku):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    driver = get_driver()
    if not driver:
        return None
    try:
        driver.get(f"{MARKET_BASE}/catalog/?q={sku}")
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd"))
            )
        except TimeoutException:
            return None

        product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
        if not product_links:
            return None

        sku_lower = sku.lower()
        target_url = None

        for link in product_links[:5]:
            href = link.get_attribute("href") or ""
            if sku_lower in href.lower():
                target_url = href
                break
            try:
                article = link.find_element(By.XPATH, "./ancestor::article")
                data_sku = (article.get_attribute("data-sku") or "").lower()
                if data_sku and sku_lower in data_sku:
                    target_url = href
                    break
            except Exception:
                pass

        if not target_url:
            return None

        driver.get(target_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "h1"))
            )
        except TimeoutException:
            return None
        time.sleep(1)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        image_url = None
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            image_url = og['content']
        if not image_url:
            for img_tag in soup.find_all('img', limit=20):
                src = img_tag.get('data-src') or img_tag.get('src', '')
                if any(k in src for k in ['/product/', '/unsafe/', 'jumia.is']):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = MARKET_BASE + src
                    image_url = src
                    break
        if not image_url:
            return None

        r = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None
    finally:
        driver.quit()


def scrape_category(category_url, max_items=30):
    driver = get_driver()
    if not driver:
        return []
    driver.get(category_url)
    time.sleep(2)
    for _ in range(3):
        driver.execute_script("window.scrollBy(0, 1500);")
        time.sleep(1)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()
    results = []
    for art in soup.find_all('article', class_='prd'):
        if len(results) >= max_items:
            break
        sku = art.get('data-sku')
        if not sku:
            core = art.find('a', class_='core')
            if core:
                sku = core.get('data-id')
        img_tag = art.find('img', class_='img')
        if img_tag:
            alt = img_tag.get('alt', 'product').strip()
            name = sku if sku else re.sub(r'[^\w\s-]', '', alt).strip().replace(' ', '_')
            src = img_tag.get('data-src') or img_tag.get('src', '')
            if src and 'data:image' not in src:
                results.append((name, src))
    return results


# ─── Header ───────────────────────────────────────────────────────────────────────
st.title("18+ Tag Generator")
st.markdown('<div class="orange-bar"></div>', unsafe_allow_html=True)
st.markdown(
    '<p class="subhead">Apply age-restriction overlays to product images — 800 x 800 px, ready to upload.</p>',
    unsafe_allow_html=True
)

if TAG_MISSING:
    st.error(f"Overlay file not found: {TAG_FILE} — place it in the same directory as this script.")
    st.stop()

tag_img_cached = load_tag_image()

# ─── Tabs ─────────────────────────────────────────────────────────────────────────
tab_single, tab_files, tab_excel, tab_urls, tab_skus, tab_category = st.tabs([
    "Single Image", "Multiple Images", "Excel", "URLs", "SKUs", "Category Scrape"
])

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 1 — SINGLE IMAGE
# ══════════════════════════════════════════════════════════════════════════════════
with tab_single:
    col_in, col_out = st.columns(2, gap="large")
    with col_in:
        st.markdown("### Source")
        uploaded = st.file_uploader(
            "Select image", type=["png", "jpg", "jpeg", "webp"],
            label_visibility="collapsed"
        )
        url_input = st.text_input("Or paste an image URL", placeholder="https://...")

    product_img = None
    out_name = "tagged_image.jpg"

    if uploaded:
        product_img = Image.open(uploaded).convert("RGBA")
        out_name = f"{uploaded.name.rsplit('.', 1)[0]}.jpg"
    elif url_input.strip():
        try:
            r = requests.get(url_input.strip(), timeout=10)
            r.raise_for_status()
            product_img = Image.open(BytesIO(r.content)).convert("RGBA")
            out_name = "image_1.jpg"
        except Exception as e:
            col_in.error(f"Could not load image: {e}")

    with col_out:
        st.markdown("### Result")
        if product_img is not None:
            result = compose_image(product_img, tag_img_cached, apply_remove=remove_old_tags)
            st.image(result, use_container_width=True)
            st.download_button(
                "Download", img_to_bytes(result), out_name,
                "image/jpeg", use_container_width=True, type="primary"
            )
        else:
            st.markdown('<div class="preview-empty">Preview will appear here</div>',
                        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 2 — MULTIPLE IMAGE FILES
# ══════════════════════════════════════════════════════════════════════════════════
with tab_files:
    files = st.file_uploader(
        "Select images", type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True, label_visibility="collapsed"
    )
    if files:
        products  = [(Image.open(f).convert("RGBA"), f.name.rsplit('.', 1)[0], True) for f in files]
        originals = [(Image.open(f).convert("RGB"),  f.name.rsplit('.', 1)[0])       for f in files]
        with st.spinner(f"Processing {len(products)} image(s)..."):
            results = process_bulk(products, tag_img_cached)
        st.success(f"{len(results)} image(s) ready.")
        show_grid_and_download(results, originals=originals)

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 3 — EXCEL
# ══════════════════════════════════════════════════════════════════════════════════
with tab_excel:
    st.caption("Accepts columns named URL / Link / Image, SKU, and Name / Title. Images are fetched automatically.")
    xl = st.file_uploader("Select Excel file", type=["xlsx", "xls"], label_visibility="collapsed")

    if xl:
        df = pd.read_excel(xl)
        url_col = sku_col = name_col = None
        for col in df.columns:
            c = str(col).lower()
            if any(k in c for k in ['url', 'link', 'image']):
                url_col = col
            elif 'sku' in c:
                sku_col = col
            elif any(k in c for k in ['name', 'title']):
                name_col = col
        if not url_col and not sku_col:
            url_col = df.columns[0]
        if not name_col and len(df.columns) > 1:
            name_col = df.columns[1]

        rows = list(df.iterrows())
        prog = st.progress(0, text="Fetching images...")

        def fetch_excel_row(args):
            idx, row = args
            if sku_col and pd.notna(row.get(sku_col)):
                base = str(row[sku_col]).strip()
            elif name_col and pd.notna(row.get(name_col)):
                base = re.sub(r'[^\w\s-]', '', str(row[name_col])).strip().replace(' ', '_')
            else:
                base = f"product_{idx + 1}"
            img = None
            if url_col and pd.notna(row.get(url_col)):
                try:
                    r = requests.get(str(row[url_col]), timeout=10)
                    r.raise_for_status()
                    img = Image.open(BytesIO(r.content)).convert("RGBA")
                except Exception:
                    pass
            elif sku_col and pd.notna(row.get(sku_col)):
                img = search_by_sku(str(row[sku_col]).strip())
            return base, img

        fetched = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(fetch_excel_row, r): r for r in rows}
            for i, f in enumerate(concurrent.futures.as_completed(futs)):
                base, img = f.result()
                if img:
                    fetched.append((img, base))
                prog.progress((i + 1) / len(rows), text=f"Fetched {i + 1} of {len(rows)}...")

        if fetched:
            originals = [(img.convert("RGB"), name) for img, name in fetched]
            products  = [(img, name, False)          for img, name in fetched]
            with st.spinner("Applying tags..."):
                results = process_bulk(products, tag_img_cached)
            st.success(f"{len(results)} image(s) processed.")
            show_grid_and_download(results, originals=originals)
        else:
            st.warning("No images could be fetched from the uploaded file.")

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 4 — URLs
# ══════════════════════════════════════════════════════════════════════════════════
with tab_urls:
    urls_text = st.text_area(
        "Paste image URLs, one per line", height=150,
        placeholder="https://example.com/image1.jpg\nhttps://example.com/image2.jpg"
    )
    if urls_text.strip():
        urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
        prog = st.progress(0, text="Fetching images...")
        fetched, errors = [], 0
        for i, url in enumerate(urls):
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                fetched.append((Image.open(BytesIO(r.content)).convert("RGBA"), f"image_{i + 1}"))
            except Exception:
                errors += 1
            prog.progress((i + 1) / len(urls), text=f"Fetched {i + 1} of {len(urls)}...")

        if fetched:
            originals = [(img.convert("RGB"), name) for img, name in fetched]
            products  = [(img, name, False)          for img, name in fetched]
            with st.spinner("Applying tags..."):
                results = process_bulk(products, tag_img_cached)
            msg = f"{len(results)} image(s) processed."
            if errors:
                msg += f" ({errors} URL(s) failed.)"
            st.success(msg)
            show_grid_and_download(results, originals=originals)

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 5 — SKUs
# ══════════════════════════════════════════════════════════════════════════════════
with tab_skus:
    skus_text = st.text_area(
        "Enter product SKUs, one per line", height=150,
        placeholder="SKU001\nSKU002"
    )
    if skus_text.strip() and st.button("Fetch and Tag", type="primary", use_container_width=True):
        skus = [s.strip() for s in skus_text.splitlines() if s.strip()]
        prog = st.progress(0, text="Fetching product images...")
        fetched = []

        def fetch_one_sku(sku):
            return sku, search_by_sku(sku)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(fetch_one_sku, s): s for s in skus}
            for i, f in enumerate(concurrent.futures.as_completed(futs)):
                sku, img = f.result()
                if img:
                    fetched.append((img, sku))
                prog.progress((i + 1) / len(skus), text=f"Fetched {i + 1} of {len(skus)}...")

        not_found = len(skus) - len(fetched)
        if fetched:
            originals = [(img.convert("RGB"), name) for img, name in fetched]
            products  = [(img, name, False)          for img, name in fetched]
            with st.spinner("Applying tags..."):
                results = process_bulk(products, tag_img_cached)
            msg = f"{len(results)} of {len(skus)} SKU(s) processed."
            if not_found:
                msg += f" {not_found} SKU(s) had no verified match and were skipped."
            st.success(msg)
            show_grid_and_download(results, originals=originals)
        else:
            st.error("No verified images found for the provided SKUs.")

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 6 — CATEGORY SCRAPE
# ══════════════════════════════════════════════════════════════════════════════════
with tab_category:
    cat_url = st.text_input(
        "Category URL",
        placeholder=f"{MARKET_BASE}/beers/"
    )
    max_items = st.slider("Maximum items to scrape", 10, 100, 30, step=10)

    if cat_url.strip() and st.button("Scrape and Tag", type="primary", use_container_width=True):
        with st.spinner("Scraping category page..."):
            scraped = scrape_category(cat_url.strip(), max_items)

        if not scraped:
            st.error("No products found. Check the URL and try again.")
        else:
            prog = st.progress(0, text="Downloading product images...")

            def fetch_cat_img(args):
                name, url = args
                try:
                    r = requests.get(url, timeout=10)
                    r.raise_for_status()
                    return name, Image.open(BytesIO(r.content)).convert("RGBA")
                except Exception:
                    return name, None

            fetched = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(fetch_cat_img, item) for item in scraped]
                for i, f in enumerate(concurrent.futures.as_completed(futs)):
                    name, img = f.result()
                    if img:
                        fetched.append((img, name))
                    prog.progress((i + 1) / len(scraped),
                                  text=f"Downloaded {i + 1} of {len(scraped)}...")

            if fetched:
                originals = [(img.convert("RGB"), name) for img, name in fetched]
                products  = [(img, name, False)          for img, name in fetched]
                with st.spinner("Applying tags..."):
                    results = process_bulk(products, tag_img_cached)
                st.success(f"{len(results)} image(s) processed.")
                show_grid_and_download(results, originals=originals)
            else:
                st.error("No images could be downloaded.")
