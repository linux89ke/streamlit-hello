import streamlit as st
from PIL import Image
import requests
from io import BytesIO
import numpy as np
import os
import re
from bs4 import BeautifulSoup

# Page config
st.set_page_config(
    page_title="Free Delivery Tag Generator",
    page_icon="🚚",
    layout="wide"
)

# Title and description
st.title("Free Delivery Tag Generator")
st.markdown("Upload a product image and add a **Free Delivery** tag overlay!")

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Tag Settings")

tag_position = st.sidebar.selectbox(
    "Tag Position:",
    ["Top Right", "Top Left", "Bottom Right", "Bottom Left"],
    index=0   # Top Right is default
)

st.sidebar.markdown("---")
st.sidebar.header("Processing Mode")
processing_mode = st.sidebar.radio(
    "Choose mode:",
    ["Single Image", "Bulk Processing"]
)

st.sidebar.markdown("---")
st.sidebar.header("Image Settings")

if 'last_image_hash' not in st.session_state:
    st.session_state.last_image_hash = None
if 'image_scale_value' not in st.session_state:
    st.session_state.image_scale_value = 100

image_scale = st.sidebar.slider(
    "Product Image Size:",
    min_value=50, max_value=150, value=st.session_state.image_scale_value,
    step=5, key="image_scale_slider",
    help="Adjust if product image appears too small or large. Default is 100%"
)
st.session_state.image_scale_value = image_scale
st.sidebar.caption(f"Current size: {image_scale}%")

st.sidebar.markdown("---")
st.sidebar.header("Tag Size")
tag_scale = st.sidebar.slider(
    "Free Delivery Tag Size:",
    min_value=10, max_value=40, value=22,
    step=1,
    help="Tag width as % of the 1000px canvas. Default 22%"
)
st.sidebar.caption(f"Tag width: {round(tag_scale/100*1000)}px")

# ── Free Delivery tag helper ──────────────────────────────────────────────────

FREE_DELIVERY_FILE = "Free-Delivery-2026.png"

def get_tag_path(filename):
    possible = [
        filename,
        os.path.join(os.path.dirname(__file__), filename),
        os.path.join(os.getcwd(), filename),
    ]
    for p in possible:
        if os.path.exists(p):
            return p
    return filename


@st.cache_data
def load_free_delivery_tag():
    """Load & prepare the Free Delivery PNG (strip black background, crop to content)."""
    path = get_tag_path(FREE_DELIVERY_FILE)
    if not os.path.exists(path):
        return None

    img = Image.open(path).convert("RGBA")
    arr = np.array(img)

    # Make black pixels transparent
    black = (arr[:, :, 0] < 20) & (arr[:, :, 1] < 20) & (arr[:, :, 2] < 20)
    arr[black, 3] = 0

    # Auto-crop to visible content
    visible = arr[:, :, 3] > 0
    rows = np.any(visible, axis=1)
    cols = np.any(visible, axis=0)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    # Small padding around the truck
    pad = 10
    rmin = max(0, rmin - pad)
    cmin = max(0, cmin - pad)
    rmax = min(arr.shape[0] - 1, rmax + pad)
    cmax = min(arr.shape[1] - 1, cmax + pad)

    cropped = Image.fromarray(arr[rmin:rmax+1, cmin:cmax+1])
    return cropped


def erase_baked_in_truck(image: Image.Image) -> Image.Image:
    """
    Detect and white-out any baked-in orange Free Delivery truck in the image.
    Orange is identified as R>180, G 80-160, B<80.
    Returns a copy with the truck area replaced by white.
    """
    arr = np.array(image.convert("RGBA"))
    orange = (
        (arr[:, :, 0] > 180) &
        (arr[:, :, 1] > 80)  & (arr[:, :, 1] < 160) &
        (arr[:, :, 2] < 80)
    )
    if not np.any(orange):
        return image  # nothing to erase

    ys, xs = np.where(orange)
    y1, y2 = max(0, ys.min() - 12), min(arr.shape[0], ys.max() + 12)
    x1, x2 = max(0, xs.min() - 12), min(arr.shape[1], xs.max() + 12)
    arr[y1:y2, x1:x2] = [255, 255, 255, 255]
    return Image.fromarray(arr)


def detect_side_tag(canvas_arr: np.ndarray, canvas_size: int):
    """
    Detect a vertical info/product tag on the right side of the canvas.
    Identifies columns that have >45% non-white pixels (tall, dense content).
    Returns (left_x, right_x, top_y) or None if not found.
    """
    CANVAS = canvas_size
    h = CANVAS
    side_tag_left = None
    for x in range(int(CANVAS * 0.60), CANVAS):
        col = canvas_arr[:, x, :3]
        nw = int(np.sum((col[:, 0] < 240) | (col[:, 1] < 240) | (col[:, 2] < 240)))
        if nw > h * 0.45:
            side_tag_left = x
            break
    if side_tag_left is None:
        return None

    side_tag_right = CANVAS - 1
    for rx in range(CANVAS - 1, side_tag_left, -1):
        col = canvas_arr[:, rx, :3]
        nw = int(np.sum((col[:, 0] < 240) | (col[:, 1] < 240) | (col[:, 2] < 240)))
        if nw > h * 0.25:
            side_tag_right = rx
            break

    mid_x = (side_tag_left + side_tag_right) // 2
    side_tag_top = 0
    for y in range(0, CANVAS // 2):
        r, g, b = int(canvas_arr[y, mid_x, 0]), int(canvas_arr[y, mid_x, 1]), int(canvas_arr[y, mid_x, 2])
        if r < 240 or g < 240 or b < 240:
            side_tag_top = y
            break

    return side_tag_left, side_tag_right, side_tag_top


def split_product_and_side_tag(prod_resized: Image.Image):
    """
    Split a product image into (bottles_crop, side_tag_crop, split_x) by finding
    the first column from 60% right that has >45% non-white pixels (tall dense tag).

    Validates the right portion is a true info banner (navy blue, tall & narrow)
    and not a cropped product bottle. Returns None for side_tag_crop if not found.
    """
    arr = np.array(prod_resized)
    h, w = arr.shape[:2]
    split_x = None
    for x in range(int(w * 0.60), w):
        col = arr[:, x, :3]
        if int(np.sum((col[:, 0] < 240) | (col[:, 1] < 240) | (col[:, 2] < 240))) > h * 0.45:
            split_x = x
            break
    if split_x is None:
        return prod_resized, None, w

    # Validate: the right portion must be a navy/dark banner, not a cropped bottle
    right = arr[:, split_x:, :3]
    nw_mask = (right[:, :, 0] < 240) | (right[:, :, 1] < 240) | (right[:, :, 2] < 240)
    nw_pixels = right[nw_mask]
    if len(nw_pixels) == 0:
        return prod_resized, None, w

    # Check navy dominance: B > R, B > G, and all channels dark
    navy = ((nw_pixels[:, 2] > nw_pixels[:, 0]) &
            (nw_pixels[:, 2] > nw_pixels[:, 1]) &
            (nw_pixels[:, 0] < 100))
    navy_pct = float(navy.sum()) / len(nw_pixels)

    # Check aspect ratio of content (side tag is very tall and narrow)
    nw_coords = np.where(nw_mask)
    content_w = int(nw_coords[1].max() - nw_coords[1].min()) + 1
    content_h = int(nw_coords[0].max() - nw_coords[0].min()) + 1
    aspect = content_h / max(content_w, 1)

    # True side tag: very navy (>55%) AND taller than wide (aspect > 2)
    if navy_pct < 0.55 or aspect < 2.0:
        return prod_resized, None, w

    bottles = prod_resized.crop((0, 0, split_x, h))
    side_tag = prod_resized.crop((split_x, 0, w, h))
    return bottles, side_tag, split_x


def content_bbox(img: Image.Image):
    """Return (left, right, top, bottom) of non-white content in image."""
    arr = np.array(img)
    nw = np.where((arr[:, :, 0] < 240) | (arr[:, :, 1] < 240) | (arr[:, :, 2] < 240))
    if len(nw[0]) == 0:
        return 0, img.width, 0, img.height
    return int(nw[1].min()), int(nw[1].max()), int(nw[0].min()), int(nw[0].max())


def composite_image(product_image: Image.Image,
                    position: str,
                    prod_scale: int,
                    tag_width_pct: int) -> Image.Image:
    """
    Place product_image on a 1000×1000 white canvas and overlay the Free Delivery tag.

    Layout logic:
    - The product is split into a LEFT part (bottles) and RIGHT part (side tag).
    - Both are placed with explicit OUTER_MARGIN on the canvas edges and
      INNER_GAP between them, eliminating the large dead gap.
    - Truck renders at FULL size (side tag width), never shrunk.
    - If truck overlaps side tag, the side tag is shifted down and scaled to fit.
    """
    CANVAS       = 1000
    SIDE_MARGIN  = 90   # left/right canvas margin
    VERT_MARGIN  = 55   # top/bottom canvas margin
    TRUCK_TOP    = 55   # truck y offset from canvas top
    PANEL_GAP    = 8    # gap between truck bottom and side tag blue panel

    # ── 1. Clean any pre-existing truck ──────────────────────────────────────
    prod = erase_baked_in_truck(product_image.convert("RGBA"))

    # ── 2. Resize product to fill canvas within margins ───────────────────────
    max_w = CANVAS - 2 * SIDE_MARGIN
    max_h = CANVAS - 2 * VERT_MARGIN
    new_size = int(CANVAS * (prod_scale / 100.0) * 0.95)
    new_size = max(100, min(new_size, min(max_w, max_h)))
    prod_resized = prod.resize((new_size, new_size), Image.Resampling.LANCZOS)

    # ── 3. Split into bottles + side tag ─────────────────────────────────────
    bottles, side_tag_crop, split_x = split_product_and_side_tag(prod_resized)
    has_side_tag = side_tag_crop is not None

    # ── 4. Load truck tag ─────────────────────────────────────────────────────
    tag = load_free_delivery_tag()
    if tag is None:
        st.warning(f"⚠️ '{FREE_DELIVERY_FILE}' not found next to the app.")
        canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
        cx = (CANVAS - new_size) // 2
        canvas.paste(prod_resized, (cx, VERT_MARGIN))
        return canvas

    py = VERT_MARGIN   # vertical offset from top

    if has_side_tag:
        # Content bounds of each part
        b_left, b_right, b_top, b_bottom = content_bbox(bottles)
        s_left, s_right, s_top, s_bottom = content_bbox(side_tag_crop)

        bottles_w  = b_right - b_left
        side_tag_w = s_right - s_left

        # Horizontal layout: SIDE_MARGIN | bottles | auto-gap | side_tag | SIDE_MARGIN
        # Auto-gap = whatever space remains between the two fixed margins
        total_fixed = SIDE_MARGIN + bottles_w + side_tag_w + SIDE_MARGIN
        auto_gap = max(10, CANVAS - total_fixed)

        bx = SIDE_MARGIN - b_left
        sx = bx + b_left + bottles_w + auto_gap - s_left

        canvas = Image.new("RGBA", (CANVAS, CANVAS), (255, 255, 255, 255))
        canvas.paste(bottles,       (bx, py), bottles)
        canvas.paste(side_tag_crop, (sx, py), side_tag_crop)

        # Absolute position of side tag content on canvas
        abs_stl = sx + s_left
        abs_str = sx + s_right
        abs_stt = py + s_top
        abs_stb = py + s_bottom

        # Truck: full width = side tag content width
        truck_w = side_tag_w
        truck_h = int(tag.height * truck_w / tag.width)
        truck_bottom = TRUCK_TOP + truck_h

        # If truck overlaps side tag: shift side tag down and scale to fit
        if truck_bottom + PANEL_GAP > abs_stt:
            side_crop2 = canvas.crop((abs_stl, abs_stt, abs_str + 1, abs_stb + 1))
            arr2 = np.array(canvas)
            arr2[abs_stt:abs_stb + 1, abs_stl:abs_str + 1] = [255, 255, 255, 255]
            canvas = Image.fromarray(arr2)
            new_top  = truck_bottom + PANEL_GAP
            avail_h  = abs_stb - new_top
            orig_h   = abs_stb - abs_stt
            sc       = avail_h / max(orig_h, 1)
            new_w    = int(side_tag_w * sc)
            side_sc  = side_crop2.resize((new_w, avail_h), Image.Resampling.LANCZOS)
            canvas.paste(side_sc, (abs_str - new_w, new_top), side_sc)

        tag_w, tag_h = truck_w, truck_h
        if position == "Top Right":
            tx = abs_str - tag_w + 5
            ty = TRUCK_TOP
        elif position == "Top Left":
            tx = SIDE_MARGIN
            ty = TRUCK_TOP
        elif position == "Bottom Right":
            tx = CANVAS - tag_w - SIDE_MARGIN
            ty = CANVAS - tag_h - VERT_MARGIN
        else:
            tx = SIDE_MARGIN
            ty = CANVAS - tag_h - VERT_MARGIN

    else:
        # No side tag — place whole product within margins, truck in corner
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (255, 255, 255, 255))
        canvas.paste(prod_resized, ((CANVAS - new_size) // 2, py), prod_resized)
        tag_w = int(CANVAS * tag_width_pct / 100)
        tag_h = int(tag.height * tag_w / tag.width)
        pos_map = {
            "Top Right":    (CANVAS - tag_w - SIDE_MARGIN, TRUCK_TOP),
            "Top Left":     (SIDE_MARGIN, TRUCK_TOP),
            "Bottom Right": (CANVAS - tag_w - SIDE_MARGIN, CANVAS - tag_h - VERT_MARGIN),
            "Bottom Left":  (SIDE_MARGIN, CANVAS - tag_h - VERT_MARGIN),
        }
        tx, ty = pos_map[position]

    tag_resized = tag.resize((tag_w, tag_h), Image.Resampling.LANCZOS)
    canvas.paste(tag_resized, (tx, ty), tag_resized)
    return canvas.convert("RGB")


# ── Selenium helpers (unchanged from original) ────────────────────────────────

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
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    for path in ["/usr/bin/chromium", "/usr/bin/chromium-browser",
                 "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]:
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
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            driver.set_page_load_timeout(20)
            driver.implicitly_wait(5)
        except Exception:
            pass
    return driver


def search_jumia_by_sku(sku, base_url, search_url):
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
            st.error("Could not initialise browser driver")
            return None
        driver.get(search_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1"))
            )
        except TimeoutException:
            st.error("Page load timeout")
            return None
        if "There are no results for" in driver.page_source or \
                "No results found" in driver.page_source:
            st.warning(f"No products found for SKU: {sku}")
            return None
        try:
            product_links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
            if not product_links:
                product_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='.html']")
            if product_links:
                product_url = product_links[0].get_attribute("href")
                driver.get(product_url)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
                import time
                time.sleep(1)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                image_url = None
                og_image = soup.find('meta', property='og:image')
                if og_image and og_image.get('content'):
                    image_url = og_image['content']
                if not image_url:
                    for img in soup.find_all('img', limit=15):
                        src = img.get('data-src') or img.get('src')
                        if src and ('/product/' in src or '/unsafe/' in src or
                                    'jumia.is' in src):
                            if src.startswith('//'):
                                src = 'https:' + src
                            elif src.startswith('/'):
                                src = base_url + src
                            image_url = src
                            break
                if image_url:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                      'AppleWebKit/537.36',
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


# ── SINGLE IMAGE MODE ─────────────────────────────────────────────────────────

if processing_mode == "Single Image":
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Upload Product Image")
        upload_method = st.radio(
            "Choose upload method:",
            ["Upload from device", "Load from Image URL", "Load from SKU"]
        )

        product_image = None

        if upload_method == "Upload from device":
            uploaded_file = st.file_uploader(
                "Choose an image file",
                type=["png", "jpg", "jpeg", "webp"]
            )
            if uploaded_file is not None:
                import hashlib
                file_hash = hashlib.md5(uploaded_file.getvalue()).hexdigest()
                if st.session_state.last_image_hash != file_hash:
                    st.session_state.last_image_hash = file_hash
                    st.session_state.image_scale_value = 100
                product_image = Image.open(uploaded_file).convert("RGBA")

        elif upload_method == "Load from Image URL":
            image_url = st.text_input("Enter image URL:")
            if image_url:
                try:
                    if st.session_state.last_image_hash != image_url:
                        st.session_state.last_image_hash = image_url
                        st.session_state.image_scale_value = 100
                    response = requests.get(image_url)
                    product_image = Image.open(BytesIO(response.content)).convert("RGBA")
                    st.success("Image loaded successfully!")
                except Exception as e:
                    st.error(f"Error loading image: {str(e)}")

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
                if jumia_site == "Jumia Kenya":
                    base_url = "https://www.jumia.co.ke"
                    search_url = f"https://www.jumia.co.ke/catalog/?q={sku_input}"
                else:
                    base_url = "https://www.jumia.ug"
                    search_url = f"https://www.jumia.ug/catalog/?q={sku_input}"
                if st.button("Search and Extract Image", use_container_width=True):
                    with st.spinner(f"Searching {jumia_site} for SKU…"):
                        sku_hash = f"{sku_input}_{jumia_site}"
                        if st.session_state.last_image_hash != sku_hash:
                            st.session_state.last_image_hash = sku_hash
                            st.session_state.image_scale_value = 100
                        product_image = search_jumia_by_sku(sku_input, base_url, search_url)
                        if product_image:
                            st.success("Image found and loaded!")
                        else:
                            st.error("Could not find product with this SKU")

    with col2:
        st.subheader("Preview")

        if product_image is not None:
            try:
                result_image = composite_image(
                    product_image,
                    position=tag_position,
                    prod_scale=image_scale,
                    tag_width_pct=tag_scale
                )

                st.image(result_image, use_container_width=True)
                st.caption("Output: 1000 × 1000 px JPEG")

                st.markdown("---")
                buf = BytesIO()
                result_image.save(buf, format="JPEG", quality=95)
                buf.seek(0)

                st.download_button(
                    label="⬇️ Download Tagged Image (JPEG)",
                    data=buf,
                    file_name=f"free_delivery_{tag_position.lower().replace(' ', '_')}.jpg",
                    mime="image/jpeg",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"Error processing image: {str(e)}")
        else:
            st.info("Upload or provide a product image to get started!")

# ── BULK PROCESSING MODE ──────────────────────────────────────────────────────

else:
    st.subheader("Bulk Processing")
    st.markdown("Process multiple products at once")

    bulk_method = st.radio(
        "Choose bulk input method:",
        ["Upload multiple images", "Enter URLs manually",
         "Upload Excel file with URLs", "Enter SKUs"]
    )

    products_to_process = []   # list of (image, filename)

    if bulk_method == "Upload multiple images":
        uploaded_files = st.file_uploader(
            "Choose multiple image files",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True
        )
        if uploaded_files:
            st.info(f"{len(uploaded_files)} files uploaded")
            for uf in uploaded_files:
                try:
                    img = Image.open(uf).convert("RGBA")
                    products_to_process.append((img, uf.name.rsplit('.', 1)[0]))
                except Exception as e:
                    st.warning(f"Could not load {uf.name}: {e}")

    elif bulk_method == "Enter URLs manually":
        urls_input = st.text_area(
            "Enter image URLs (one per line):", height=200,
            placeholder="https://example.com/image1.jpg\nhttps://example.com/image2.jpg"
        )
        if urls_input.strip():
            urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
            st.info(f"{len(urls)} URLs entered")
            for idx, url in enumerate(urls):
                try:
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    img = Image.open(BytesIO(response.content)).convert("RGBA")
                    products_to_process.append((img, f"image_{idx+1}"))
                except Exception as e:
                    st.warning(f"Could not load {url}: {e}")

    elif bulk_method == "Upload Excel file with URLs":
        st.markdown("""
        **Excel format:** Column A = Image URLs, Column B = Product names (optional)
        """)
        excel_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"])
        if excel_file:
            try:
                import pandas as pd
                df = pd.read_excel(excel_file)
                if len(df.columns) > 0:
                    urls = df.iloc[:, 0].dropna().astype(str).tolist()
                    names = (df.iloc[:, 1].dropna().astype(str).tolist()
                             if len(df.columns) > 1
                             else [f"product_{i+1}" for i in range(len(urls))])
                    st.info(f"Found {len(urls)} URLs")
                    for idx, (url, name) in enumerate(zip(urls, names)):
                        try:
                            response = requests.get(url, timeout=10)
                            response.raise_for_status()
                            img = Image.open(BytesIO(response.content)).convert("RGBA")
                            clean_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')
                            products_to_process.append(
                                (img, clean_name or f"product_{idx+1}")
                            )
                        except Exception as e:
                            st.warning(f"Could not load {name}: {e}")
                else:
                    st.error("Excel file appears to be empty")
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")

    else:  # Enter SKUs
        skus_input = st.text_area(
            "Enter Product SKUs (one per line):", height=200,
            placeholder="GE840EA6C62GANAFAMZ\nAP456EA7D89HANAFAMZ"
        )
        jumia_site_bulk = st.radio(
            "Select Jumia Site:",
            ["Jumia Kenya", "Jumia Uganda"],
            horizontal=True, key="bulk_jumia_site"
        )
        if skus_input.strip():
            skus = [s.strip() for s in skus_input.split('\n') if s.strip()]
            st.info(f"{len(skus)} SKUs entered")
            if st.button("Search All SKUs and Extract Images", use_container_width=True):
                base_url = ("https://www.jumia.co.ke"
                            if jumia_site_bulk == "Jumia Kenya"
                            else "https://www.jumia.ug")
                progress = st.progress(0)
                status_text = st.empty()
                for idx, sku in enumerate(skus):
                    status_text.text(f"Processing SKU {idx+1}/{len(skus)}: {sku}")
                    search_url = f"{base_url}/catalog/?q={sku}"
                    img = search_jumia_by_sku(sku, base_url, search_url)
                    if img:
                        products_to_process.append((img, sku))
                    else:
                        st.warning(f"Could not find image for SKU: {sku}")
                    progress.progress((idx + 1) / len(skus))
                status_text.text(
                    f"Done! Found {len(products_to_process)} of {len(skus)} images"
                )

    # ── Review & process ──────────────────────────────────────────────────────
    if products_to_process:
        st.markdown("---")
        st.subheader("Review and Adjust Images")
        st.info(f"Loaded {len(products_to_process)} images. Adjust sizes before processing.")

        if 'individual_scales' not in st.session_state:
            st.session_state.individual_scales = {}

        COLS = 3
        rows = (len(products_to_process) + COLS - 1) // COLS
        for row in range(rows):
            cols = st.columns(COLS)
            for col_idx in range(COLS):
                idx = row * COLS + col_idx
                if idx < len(products_to_process):
                    img, filename = products_to_process[idx]
                    with cols[col_idx]:
                        st.image(img, caption=filename, use_container_width=True)
                        key = f"scale_{idx}_{filename}"
                        if key not in st.session_state.individual_scales:
                            st.session_state.individual_scales[key] = 100
                        scale = st.slider(
                            "Size %", min_value=50, max_value=150,
                            value=st.session_state.individual_scales[key],
                            step=5, key=f"slider_{key}",
                            label_visibility="collapsed"
                        )
                        st.session_state.individual_scales[key] = scale
                        st.caption(f"{scale}%")

        st.markdown("---")
        if st.button("Process All Images", use_container_width=True):
            st.info(f"Processing {len(products_to_process)} images…")
            progress_bar = st.progress(0)
            processed_images = []

            for idx, (product_image, filename) in enumerate(products_to_process):
                try:
                    key = f"scale_{idx}_{filename}"
                    individual_scale = st.session_state.individual_scales.get(key, 100)
                    result = composite_image(
                        product_image,
                        position=tag_position,
                        prod_scale=individual_scale,
                        tag_width_pct=tag_scale
                    )
                    processed_images.append((result, filename))
                except Exception as e:
                    st.warning(f"Error processing {filename}: {e}")
                progress_bar.progress((idx + 1) / len(products_to_process))

            if processed_images:
                st.markdown("---")
                st.success(f"Successfully processed {len(processed_images)} images!")

                import zipfile
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for img, name in processed_images:
                        img_buf = BytesIO()
                        img.save(img_buf, format='JPEG', quality=95)
                        zf.writestr(f"{name}_1.jpg", img_buf.getvalue())
                zip_buffer.seek(0)

                st.download_button(
                    label=f"⬇️ Download All {len(processed_images)} Images (ZIP)",
                    data=zip_buffer,
                    file_name=f"free_delivery_{tag_position.lower().replace(' ', '_')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )

                st.markdown("### Preview (first 9)")
                cols = st.columns(3)
                for idx, (img, name) in enumerate(processed_images[:9]):
                    with cols[idx % 3]:
                        st.image(img, caption=name, use_container_width=True)
                if len(processed_images) > 9:
                    st.info(f"Showing 9 of {len(processed_images)} processed images")
            else:
                st.error("No images were successfully processed")
    else:
        if processing_mode == "Bulk Processing":
            st.info("Please provide images to process")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#666'>"
    "All output images are 1000 × 1000 px JPEG &nbsp;|&nbsp; "
    "Place <b>Free-Delivery-2026.png</b> in the same folder as app.py"
    "</div>",
    unsafe_allow_html=True
)
