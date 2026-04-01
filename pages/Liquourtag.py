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

# ─── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Age Restriction Tag Generator",
    page_icon=None,
    layout="wide"
)

# ─── Minimal Professional Styling ───────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #f8f8f6; }
    [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e0e0e0; }
    h1 { font-size: 1.6rem !important; font-weight: 700 !important; color: #1a1a1a !important; letter-spacing: -0.02em; }
    h2, h3 { font-weight: 600 !important; color: #1a1a1a !important; }
    .stButton > button[kind="primary"] {
        background: #1a1a1a !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em;
    }
    .stButton > button[kind="primary"]:hover { background: #333 !important; }
    .stButton > button { border-radius: 4px !important; }
    .stDownloadButton > button {
        border-radius: 4px !important;
        font-weight: 600 !important;
    }
    .stRadio > label { font-weight: 500; }
    div[data-testid="stImage"] img { border: 1px solid #e0e0e0; border-radius: 4px; }
    .status-box {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        padding: 1rem 1.25rem;
        margin: 0.5rem 0;
        font-size: 0.875rem;
        color: #333;
    }
</style>
""", unsafe_allow_html=True)

# ─── Constants ───────────────────────────────────────────────────────────────────
TAG_FILE = "NSFW-18++-Tag.png"
TARGET_CANVAS_SIZE = (800, 800)
PRODUCT_MAX_SIZE = (680, 680)

# ─── Session State Init ──────────────────────────────────────────────────────────
if "products_to_process" not in st.session_state:
    st.session_state.products_to_process = []
if "processed_images" not in st.session_state:
    st.session_state.processed_images = []
if "bulk_ready" not in st.session_state:
    st.session_state.bulk_ready = False

# ─── Tag File Validation ─────────────────────────────────────────────────────────
TAG_PATH = TAG_FILE if os.path.exists(TAG_FILE) else os.path.join(os.path.dirname(__file__), TAG_FILE)
TAG_MISSING = not os.path.exists(TAG_PATH)
if TAG_MISSING:
    st.error(f"Overlay file not found: {TAG_FILE}. Please place it in the same directory as this script.")

# ─── Sidebar ─────────────────────────────────────────────────────────────────────
st.sidebar.title("Age Restriction Tag Generator")
st.sidebar.markdown("---")
st.sidebar.header("Processing Mode")
processing_mode = st.sidebar.radio("Mode", ["Single Image", "Bulk Processing"])

st.sidebar.markdown("---")
st.sidebar.header("Options")
remove_old_tags = st.sidebar.checkbox(
    "Remove Existing 18+ Tags",
    value=True,
    help="Scans the top-right corner for existing red 18+ tags and removes them before applying the new overlay."
)

# ─── Helper Functions ─────────────────────────────────────────────────────────────

def remove_existing_tag(img):
    """Detect a red 18+ tag in the top-right quadrant and white it out."""
    img_rgb = img.convert('RGB') if img.mode != 'RGB' else img.copy()
    data = np.array(img_rgb)
    h, w, _ = data.shape
    search_h, search_w = int(h * 0.35), int(w * 0.35)
    top_right = data[0:search_h, w - search_w:w]

    # Tighter heuristic to reduce false positives on red product packaging
    red_mask = (
        (top_right[:, :, 0] > 160) &
        (top_right[:, :, 1] < 80) &
        (top_right[:, :, 2] < 80) &
        (top_right[:, :, 0].astype(int) - top_right[:, :, 1].astype(int) > 100)
    )

    if np.sum(red_mask) > 30:
        coords = np.argwhere(red_mask)
        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)
        pad = 25
        y_min = max(0, y_min - pad)
        x_min = max(0, x_min - pad)
        y_max = min(search_h, y_max + pad)
        x_max = min(search_w, x_max + pad)
        real_x_min = (w - search_w) + x_min
        real_x_max = (w - search_w) + x_max
        data[y_min:y_max, real_x_min:real_x_max] = [255, 255, 255]

        if img.mode == 'RGBA':
            orig = np.array(img)
            orig[:, :, 0:3] = data
            return Image.fromarray(orig, 'RGBA')
        return Image.fromarray(data, 'RGB')
    return img


def crop_white_space(img):
    """Remove large white borders from product images."""
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


def compose_image(product_img, tag_img, apply_remove=True):
    """Compose a single product image with the tag overlay.

    The product is scaled so its height exactly fills the canvas minus
    VERTICAL_PADDING px on the top and bottom (i.e. available height =
    TARGET_CANVAS_SIZE[1] - 2 * VERTICAL_PADDING).  The width is scaled
    proportionally; if the result would be wider than the canvas minus the
    same horizontal padding, it is scaled down again to fit width-wise.
    The image is then centred horizontally and pinned to the 50 px top margin.
    """
    VERTICAL_PADDING = 50

    img = product_img.copy()
    if apply_remove:
        img = remove_existing_tag(img)
    img = crop_white_space(img)

    canvas_w, canvas_h = TARGET_CANVAS_SIZE
    available_h = canvas_h - 2 * VERTICAL_PADDING   # 700 px for 800-px canvas
    available_w = canvas_w - 2 * VERTICAL_PADDING   # 700 px for 800-px canvas

    src_w, src_h = img.size

    # Scale to fill available height exactly, preserving aspect ratio
    scale = available_h / src_h
    new_w = int(src_w * scale)
    new_h = available_h

    # If width exceeds available width, scale down to fit width instead
    if new_w > available_w:
        scale = available_w / src_w
        new_w = available_w
        new_h = int(src_h * scale)

    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    result = Image.new("RGB", TARGET_CANVAS_SIZE, (255, 255, 255))

    # Centre horizontally; top-align to VERTICAL_PADDING
    px = (canvas_w - new_w) // 2
    py = VERTICAL_PADDING

    if img.mode == 'RGBA':
        result.paste(img, (px, py), img)
    else:
        result.paste(img, (px, py))
    result.paste(tag_img, (0, 0), tag_img)
    return result


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
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-logging")
    opts.add_argument("--log-level=3")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # Use shutil.which for portable binary detection
    for binary in ["chromium", "chromium-browser", "google-chrome-stable", "google-chrome"]:
        path = shutil.which(binary)
        if path:
            opts.binary_location = path
            break
    return opts


def get_driver(headless=True):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        st.error("Selenium is not installed.")
        return None

    opts = get_chrome_options(headless)
    driver = None
    try:
        driver_path = get_driver_path()
        if driver_path:
            svc = Service(driver_path)
            svc.log_path = os.devnull
            driver = webdriver.Chrome(service=svc, options=opts)
        else:
            driver = webdriver.Chrome(options=opts)
    except Exception as e:
        st.warning(f"ChromeDriver could not be initialised: {e}. Selenium-based features are unavailable.")
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
    driver = get_driver(headless=True)
    if not driver:
        return []
    driver.get(category_url)
    time.sleep(2)
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
        sku = art.get('data-sku')
        if not sku:
            core_a = art.find('a', class_='core')
            if core_a:
                sku = core_a.get('data-id')
        img_tag = art.find('img', class_='img')
        if img_tag:
            name_attr = img_tag.get('alt', 'product').strip()
            base_name = sku if sku else re.sub(r'[^\w\s-]', '', name_attr).strip().replace(' ', '_')
            img_url = img_tag.get('data-src') or img_tag.get('src')
            if img_url and 'data:image' not in img_url:
                results.append((base_name, img_url))
    return results


def search_jumia_by_sku(sku, base_url, search_url):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    driver = get_driver(headless=True)
    if not driver:
        return None
    try:
        driver.get(search_url)
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
        except TimeoutException:
            return None
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
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = base_url + src
                        image_url = src
                        break
            if image_url:
                img_response = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
                img_response.raise_for_status()
                return Image.open(BytesIO(img_response.content)).convert("RGBA")
        return None
    except Exception:
        return None
    finally:
        driver.quit()


# ─── Main Title ──────────────────────────────────────────────────────────────────
st.title("Age Restriction Tag Generator")
st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════════
# SINGLE IMAGE MODE
# ═══════════════════════════════════════════════════════════════════════════════════
if processing_mode == "Single Image":
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Input Image")
        upload_method = st.radio(
            "Source",
            ["Upload from device", "Load from URL", "Load from SKU"],
            horizontal=True
        )

        product_image = None
        single_output_name = "age_restricted_800x800.jpg"

        if upload_method == "Upload from device":
            uploaded_file = st.file_uploader("Select image", type=["png", "jpg", "jpeg", "webp"])
            if uploaded_file:
                product_image = Image.open(uploaded_file).convert("RGBA")
                single_output_name = f"{uploaded_file.name.rsplit('.', 1)[0]}.jpg"

        elif upload_method == "Load from URL":
            image_url = st.text_input("Image URL")
            if image_url:
                try:
                    response = requests.get(image_url, timeout=10)
                    response.raise_for_status()
                    product_image = Image.open(BytesIO(response.content)).convert("RGBA")
                    single_output_name = "image_1.jpg"
                    st.success("Image loaded successfully.")
                except Exception as e:
                    st.error(f"Failed to load image: {e}")

        else:
            sku_input = st.text_input("Product SKU")
            jumia_site = st.radio("Jumia Site", ["Jumia Kenya", "Jumia Uganda"], horizontal=True)
            if sku_input and st.button("Search and Extract", use_container_width=True):
                with st.spinner("Searching Jumia..."):
                    base_url = "https://www.jumia.co.ke" if jumia_site == "Jumia Kenya" else "https://www.jumia.ug"
                    search_url = f"{base_url}/catalog/?q={sku_input}"
                    product_image = search_jumia_by_sku(sku_input, base_url, search_url)
                    if product_image:
                        single_output_name = f"{sku_input.strip()}_1.jpg"
                        st.success("Product image found.")
                    else:
                        st.error("No product image found for this SKU.")

    with col2:
        st.subheader("Result Preview")
        if product_image is not None:
            if TAG_MISSING:
                st.error("Cannot generate tag: overlay file is missing.")
            else:
                tag_image = Image.open(TAG_PATH).convert("RGBA")
                if tag_image.size != TARGET_CANVAS_SIZE:
                    tag_image = tag_image.resize(TARGET_CANVAS_SIZE, Image.Resampling.LANCZOS)

                result_image = compose_image(product_image, tag_image, apply_remove=remove_old_tags)
                st.image(result_image, use_container_width=True)

                buf = BytesIO()
                result_image.save(buf, format="JPEG", quality=95)
                st.download_button(
                    label="Download Image",
                    data=buf.getvalue(),
                    file_name=single_output_name,
                    mime="image/jpeg",
                    use_container_width=True
                )

# ═══════════════════════════════════════════════════════════════════════════════════
# BULK PROCESSING MODE
# ═══════════════════════════════════════════════════════════════════════════════════
else:
    st.subheader("Bulk Processing")
    bulk_method = st.radio(
        "Input method",
        ["Upload multiple images", "Enter URLs", "Upload Excel", "Enter SKUs", "Jumia Category URL"],
        horizontal=True
    )

    # ── Input Collection ──────────────────────────────────────────────────────────

    if bulk_method == "Upload multiple images":
        uploaded_files = st.file_uploader(
            "Select images", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True
        )
        if uploaded_files:
            st.session_state.products_to_process = []
            for f in uploaded_files:
                st.session_state.products_to_process.append(
                    (Image.open(f).convert("RGBA"), f.name.rsplit('.', 1)[0], True)
                )
            st.success(f"{len(st.session_state.products_to_process)} image(s) loaded.")

    elif bulk_method == "Enter URLs":
        urls_input = st.text_area("Image URLs (one per line)")
        if st.button("Load Images from URLs", use_container_width=True):
            if urls_input.strip():
                urls = [u.strip() for u in urls_input.splitlines() if u.strip()]
                st.session_state.products_to_process = []
                prog = st.progress(0)
                errors = 0
                for idx, url in enumerate(urls):
                    try:
                        resp = requests.get(url, timeout=10)
                        resp.raise_for_status()
                        img = Image.open(BytesIO(resp.content)).convert("RGBA")
                        st.session_state.products_to_process.append((img, f"image_{idx + 1}", False))
                    except Exception:
                        errors += 1
                    prog.progress((idx + 1) / len(urls))
                msg = f"{len(st.session_state.products_to_process)} image(s) loaded."
                if errors:
                    msg += f" {errors} URL(s) failed."
                st.success(msg)

    elif bulk_method == "Upload Excel":
        st.caption("Auto-detects columns named 'URL', 'Link', 'SKU', and 'Name'.")
        excel_file = st.file_uploader("Select Excel file", type=["xlsx", "xls"])
        if excel_file and st.button("Load from Excel", use_container_width=True):
            df = pd.read_excel(excel_file)
            url_col, sku_col, name_col = None, None, None
            for col in df.columns:
                c = str(col).lower()
                if any(k in c for k in ['url', 'link', 'image']):
                    url_col = col
                elif 'sku' in c:
                    sku_col = col
                elif any(k in c for k in ['name', 'title']):
                    name_col = col
            if not url_col and not sku_col and len(df.columns) > 0:
                url_col = df.columns[0]
            if not name_col and len(df.columns) > 1:
                name_col = df.columns[1]

            st.session_state.products_to_process = []
            prog = st.progress(0)
            status = st.empty()

            rows = list(df.iterrows())

            def fetch_row(args):
                idx, row = args
                if sku_col and pd.notna(row.get(sku_col, None)):
                    base_name = str(row[sku_col]).strip()
                elif name_col and pd.notna(row.get(name_col, None)):
                    base_name = re.sub(r'[^\w\s-]', '', str(row[name_col])).strip().replace(' ', '_')
                else:
                    base_name = f"product_{idx + 1}"

                img = None
                if url_col and pd.notna(row.get(url_col, None)):
                    try:
                        resp = requests.get(str(row[url_col]), timeout=10)
                        resp.raise_for_status()
                        img = Image.open(BytesIO(resp.content)).convert("RGBA")
                    except Exception:
                        pass
                elif sku_col and pd.notna(row.get(sku_col, None)):
                    sku = str(row[sku_col]).strip()
                    img = search_jumia_by_sku(sku, "https://www.jumia.co.ke", f"https://www.jumia.co.ke/catalog/?q={sku}")

                return base_name, img

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(fetch_row, (idx, row)): idx for idx, row in rows}
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    base_name, img = future.result()
                    if img:
                        st.session_state.products_to_process.append((img, base_name, False))
                    prog.progress((i + 1) / len(rows))
                    status.text(f"Processing row {i + 1} of {len(rows)}...")

            st.success(f"{len(st.session_state.products_to_process)} image(s) loaded from Excel.")

    elif bulk_method == "Enter SKUs":
        skus_input = st.text_area("SKUs (one per line)")
        site = st.radio("Site", ["Jumia Kenya", "Jumia Uganda"], horizontal=True)
        if skus_input.strip() and st.button("Fetch SKU Images", use_container_width=True):
            skus = [s.strip() for s in skus_input.splitlines() if s.strip()]
            base_url = "https://www.jumia.co.ke" if site == "Jumia Kenya" else "https://www.jumia.ug"
            st.session_state.products_to_process = []
            prog = st.progress(0)
            stat = st.empty()

            def fetch_sku(sku):
                return sku, search_jumia_by_sku(sku, base_url, f"{base_url}/catalog/?q={sku}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(fetch_sku, s): s for s in skus}
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    sku, img = future.result()
                    if img:
                        st.session_state.products_to_process.append((img, sku, False))
                    prog.progress((i + 1) / len(skus))
                    stat.text(f"Fetched {i + 1} of {len(skus)} SKUs...")

            st.success(f"{len(st.session_state.products_to_process)} image(s) fetched.")

    elif bulk_method == "Jumia Category URL":
        cat_url = st.text_input("Category URL (e.g. https://www.jumia.co.ke/beers/)")
        max_limit = st.slider("Maximum items to scrape", 10, 100, 30, step=10)
        if cat_url and st.button("Scrape Category", use_container_width=True):
            with st.spinner("Scraping category page..."):
                scraped_data = scrape_jumia_category(cat_url, max_limit)
            if not scraped_data:
                st.error("No images found. Verify the URL and try again.")
            else:
                st.session_state.products_to_process = []
                prog = st.progress(0)
                stat = st.empty()

                def fetch_img(args):
                    name, url = args
                    try:
                        resp = requests.get(url, timeout=10)
                        resp.raise_for_status()
                        return name, Image.open(BytesIO(resp.content)).convert("RGBA")
                    except Exception:
                        return name, None

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(fetch_img, item) for item in scraped_data]
                    for i, future in enumerate(concurrent.futures.as_completed(futures)):
                        name, img = future.result()
                        if img:
                            st.session_state.products_to_process.append((img, name, False))
                        prog.progress((i + 1) / len(scraped_data))
                        stat.text(f"Downloaded {i + 1} of {len(scraped_data)} images...")

                st.success(f"{len(st.session_state.products_to_process)} image(s) loaded.")

    # ── Generate Tags ──────────────────────────────────────────────────────────────

    st.markdown("---")
    loaded_count = len(st.session_state.products_to_process)

    if loaded_count > 0:
        st.markdown(f"**{loaded_count} image(s) ready for processing.**")

        if st.button("Generate Tags", type="primary", use_container_width=True):
            if TAG_MISSING:
                st.error("Cannot generate tags: overlay file is missing.")
            else:
                tag_image = Image.open(TAG_PATH).convert("RGBA")
                if tag_image.size != TARGET_CANVAS_SIZE:
                    tag_image = tag_image.resize(TARGET_CANVAS_SIZE, Image.Resampling.LANCZOS)

                st.session_state.processed_images = []
                prog = st.progress(0)
                status_text = st.empty()

                st.markdown("### Preview")
                preview_container = st.container()
                cols_per_row = 4

                for idx, (img, fname, is_device) in enumerate(st.session_state.products_to_process):
                    result = compose_image(img, tag_image, apply_remove=remove_old_tags)
                    final_name = fname if is_device else f"{fname}_1"
                    st.session_state.processed_images.append((result, final_name))

                    col_idx = idx % cols_per_row
                    if col_idx == 0:
                        current_cols = preview_container.columns(cols_per_row)
                    current_cols[col_idx].image(result, caption=final_name, use_container_width=True)

                    prog.progress((idx + 1) / loaded_count)
                    status_text.text(f"Processing {idx + 1} of {loaded_count}...")

                status_text.text(f"Complete. {len(st.session_state.processed_images)} image(s) generated.")

        # Show download button if we have results
        if st.session_state.processed_images:
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for img, name in st.session_state.processed_images:
                    img_buf = BytesIO()
                    img.save(img_buf, format='JPEG', quality=95)
                    zf.writestr(f"{name}.jpg", img_buf.getvalue())

            st.download_button(
                label=f"Download {len(st.session_state.processed_images)} Images (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="age_restricted_images.zip",
                mime="application/zip",
                use_container_width=True
            )
    else:
        st.info("Load images using one of the input methods above, then click Generate Tags.")
