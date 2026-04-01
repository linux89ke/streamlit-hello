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
st.set_page_config(page_title="Age Restriction Tag Generator", page_icon=None, layout="wide")

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #f5f5f3; }
    [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e0e0e0; }
    h1 { font-size: 1.45rem !important; font-weight: 700 !important; color: #111 !important;
         letter-spacing: -0.02em; margin-bottom: 0 !important; }
    .subhead { color: #666; font-size: 0.85rem; margin-top: 2px; margin-bottom: 1.2rem; }
    h3 { font-weight: 600 !important; color: #111 !important; font-size: 1rem !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #e0e0e0; }
    .stTabs [data-baseweb="tab"] { font-weight: 500; font-size: 0.875rem; padding: 8px 18px; color: #555; }
    .stTabs [aria-selected="true"] { color: #111 !important; border-bottom: 2px solid #111 !important; }
    .stButton > button { border-radius: 4px !important; font-weight: 600 !important; }
    .stButton > button[kind="primary"] {
        background: #111 !important; color: #fff !important;
        border: none !important; letter-spacing: 0.01em;
    }
    .stButton > button[kind="primary"]:hover { background: #333 !important; }
    .stDownloadButton > button { border-radius: 4px !important; font-weight: 600 !important; }
    div[data-testid="stImage"] img { border: 1px solid #e0e0e0; border-radius: 4px; }
    .stAlert { border-radius: 4px !important; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────────
TAG_FILE = "NSFW-18++-Tag.png"
TARGET_CANVAS_SIZE = (800, 800)
VERTICAL_PADDING = 50

# ─── Session State ────────────────────────────────────────────────────────────────
for key, default in [
    ("single_result", None),
    ("single_name", "tagged_image.jpg"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Tag File Check ───────────────────────────────────────────────────────────────
TAG_PATH = TAG_FILE if os.path.exists(TAG_FILE) else os.path.join(os.path.dirname(__file__), TAG_FILE)
TAG_MISSING = not os.path.exists(TAG_PATH)

# ─── Sidebar ──────────────────────────────────────────────────────────────────────
st.sidebar.title("Settings")
remove_old_tags = st.sidebar.checkbox(
    "Remove existing 18+ tags", value=True,
    help="Detects and removes any previous red 18+ overlay before applying the new one.")
jumia_site = st.sidebar.radio("Jumia site", ["Jumia Kenya", "Jumia Uganda"])
JUMIA_BASE = "https://www.jumia.co.ke" if jumia_site == "Jumia Kenya" else "https://www.jumia.ug"

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
    if fmt == "JPEG":
        img.save(buf, format="JPEG", quality=95)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def build_zip(pairs, fmt="JPEG"):
    """Build a ZIP from (PIL Image, filename) pairs."""
    ext = "jpg" if fmt == "JPEG" else fmt.lower()
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for img, name in pairs:
            zf.writestr(f"{name}.{ext}", img_to_bytes(img, fmt))
    return buf.getvalue()


def process_bulk(products, tag):
    """
    products: list of (PIL Image, str name, bool is_device_upload)
    Returns list of (tagged PIL Image, final_name), preserving input order.
    """
    results = []
    for img, name, is_device in products:
        result = compose_image(img, tag, apply_remove=remove_old_tags)
        final_name = name if is_device else f"{name}_1"
        results.append((result, final_name))
    return results


def show_grid_and_download(results, originals=None, zip_name="tagged_images.zip"):
    """
    Show image grid and download buttons.
    results:   list of (tagged PIL Image, name)
    originals: list of (original PIL Image, name) — if provided, show backup download
    """
    cols_per_row = 4
    for i in range(0, len(results), cols_per_row):
        row_imgs = results[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (img, name) in zip(cols, row_imgs):
            col.image(img, caption=name, use_container_width=True)

    dl_col, orig_col = st.columns(2)
    with dl_col:
        st.download_button(
            f"Download {len(results)} Tagged Image(s) (ZIP)",
            build_zip(results),
            zip_name, "application/zip",
            use_container_width=True, type="primary"
        )
    if originals:
        with orig_col:
            st.download_button(
                f"Download {len(originals)} Original(s) (ZIP)",
                build_zip(originals),
                zip_name.replace(".zip", "_originals.zip"),
                "application/zip",
                use_container_width=True
            )


# ─── Selenium Helpers ─────────────────────────────────────────────────────────────

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
        st.warning(f"ChromeDriver unavailable: {e}")
        return None
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.set_page_load_timeout(20)
        driver.implicitly_wait(5)
    except Exception:
        pass
    return driver


def search_jumia_by_sku(sku):
    """
    Search Jumia for a specific SKU and return its main product image.

    Root cause of ghost products:
      - The old fallback `a[href*='.html']` matched ANY link on the page
        (nav menus, banners, related products), causing random product images
        to be fetched for SKUs that returned no direct match.
      - The old code also took links[0] blindly without checking whether the
        search result actually corresponded to the queried SKU.

    Fix:
      - Only use `article.prd a.core` links from the search results grid.
        These are guaranteed to be product cards, not navigation.
      - The broad `.html` fallback is completely removed.
      - If the search result page yields zero product cards, we return None
        immediately rather than falling through to an unrelated page.
      - We verify the SKU appears in the product page URL or title before
        fetching the image, and skip if there is no match.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    driver = get_driver()
    if not driver:
        return None

    try:
        driver.get(f"{JUMIA_BASE}/catalog/?q={sku}")
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd"))
            )
        except TimeoutException:
            # No product grid appeared at all — genuine no-result
            return None

        # Only consider actual product card links — never nav/category links
        product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
        if not product_links:
            return None

        # Verify the first result relates to our SKU.
        # Jumia encodes the SKU in the product URL (e.g. /…-SKUXXXX.html)
        # and also exposes it as data-sku on the article element.
        sku_lower = sku.lower()
        target_url = None

        for link in product_links[:5]:   # check up to 5 results, not just first
            href = link.get_attribute("href") or ""
            # Try to find the SKU in the URL slug
            if sku_lower in href.lower():
                target_url = href
                break
            # Also check data-sku attribute on the parent article
            try:
                article = link.find_element(By.XPATH, "./ancestor::article")
                data_sku = (article.get_attribute("data-sku") or "").lower()
                if data_sku and sku_lower in data_sku:
                    target_url = href
                    break
            except Exception:
                pass

        # If none of the top results match the SKU, return None rather than
        # fetching an unrelated product image
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

        # Prefer og:image as it is always the primary product shot
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            image_url = og['content']

        # Fallback: scan img tags for Jumia CDN product images only
        if not image_url:
            for img_tag in soup.find_all('img', limit=20):
                src = img_tag.get('data-src') or img_tag.get('src', '')
                if any(k in src for k in ['/product/', '/unsafe/', 'jumia.is']):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = JUMIA_BASE + src
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


def scrape_jumia_category(category_url, max_items=30):
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
st.title("Age Restriction Tag Generator")
st.markdown(
    '<p class="subhead">Apply 18+ overlays to product images for marketplace listings.</p>',
    unsafe_allow_html=True
)

if TAG_MISSING:
    st.error(f"Overlay file not found: {TAG_FILE} — place it in the same directory as this script.")
    st.stop()

tag_img_cached = load_tag_image()

# ─── Tabs ─────────────────────────────────────────────────────────────────────────
tab_single, tab_files, tab_excel, tab_urls, tab_skus, tab_category = st.tabs([
    "Single Image", "Multiple Images", "Excel", "URLs", "SKUs", "Jumia Category"
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
                "image/jpeg", use_container_width=True
            )
        else:
            st.markdown(
                '<div style="height:220px;display:flex;align-items:center;'
                'justify-content:center;border:1px dashed #ccc;border-radius:6px;'
                'color:#aaa;font-size:0.875rem;">Preview will appear here</div>',
                unsafe_allow_html=True
            )

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 2 — MULTIPLE IMAGE FILES
# ══════════════════════════════════════════════════════════════════════════════════
with tab_files:
    files = st.file_uploader(
        "Select images", type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True, label_visibility="collapsed"
    )
    if files:
        products = [(Image.open(f).convert("RGBA"), f.name.rsplit('.', 1)[0], True) for f in files]
        originals = [(Image.open(f).convert("RGB"), f.name.rsplit('.', 1)[0]) for f in files]
        with st.spinner(f"Processing {len(products)} image(s)..."):
            results = process_bulk(products, tag_img_cached)
        st.success(f"{len(results)} image(s) ready.")
        show_grid_and_download(results, originals=originals)

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 3 — EXCEL
# ══════════════════════════════════════════════════════════════════════════════════
with tab_excel:
    st.caption("Accepts columns: URL / Link / Image, SKU, Name / Title. Images are fetched automatically.")
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
                img = search_jumia_by_sku(str(row[sku_col]).strip())
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
            products = [(img, name, False) for img, name in fetched]
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
                img = Image.open(BytesIO(r.content)).convert("RGBA")
                fetched.append((img, f"image_{i + 1}"))
            except Exception:
                errors += 1
            prog.progress((i + 1) / len(urls), text=f"Fetched {i + 1} of {len(urls)}...")

        if fetched:
            originals = [(img.convert("RGB"), name) for img, name in fetched]
            products = [(img, name, False) for img, name in fetched]
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
        "Enter SKUs, one per line", height=150,
        placeholder="SKU001\nSKU002"
    )
    if skus_text.strip() and st.button("Fetch and Tag", type="primary", use_container_width=True):
        skus = [s.strip() for s in skus_text.splitlines() if s.strip()]
        prog = st.progress(0, text="Fetching from Jumia...")
        fetched = []   # list of (img, sku_name) — only verified matches

        def fetch_one_sku(sku):
            return sku, search_jumia_by_sku(sku)

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
            products = [(img, name, False) for img, name in fetched]
            with st.spinner("Applying tags..."):
                results = process_bulk(products, tag_img_cached)
            msg = f"{len(results)} of {len(skus)} SKU(s) processed."
            if not_found:
                msg += f" {not_found} SKU(s) returned no verified match and were skipped."
            st.success(msg)
            show_grid_and_download(results, originals=originals)
        else:
            st.error("No verified images found for the provided SKUs.")

# ══════════════════════════════════════════════════════════════════════════════════
# TAB 6 — JUMIA CATEGORY
# ══════════════════════════════════════════════════════════════════════════════════
with tab_category:
    cat_url = st.text_input("Category URL", placeholder="https://www.jumia.co.ke/beers/")
    max_items = st.slider("Maximum items", 10, 100, 30, step=10)

    if cat_url.strip() and st.button("Scrape and Tag", type="primary", use_container_width=True):
        with st.spinner("Scraping category page..."):
            scraped = scrape_jumia_category(cat_url.strip(), max_items)

        if not scraped:
            st.error("No products found. Check the URL and try again.")
        else:
            prog = st.progress(0, text="Downloading images...")

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
                products = [(img, name, False) for img, name in fetched]
                with st.spinner("Applying tags..."):
                    results = process_bulk(products, tag_img_cached)
                st.success(f"{len(results)} image(s) processed.")
                show_grid_and_download(results, originals=originals)
            else:
                st.error("No images could be downloaded.")
