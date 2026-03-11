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

    black = (arr[:, :, 0] < 20) & (arr[:, :, 1] < 20) & (arr[:, :, 2] < 20)
    arr[black, 3] = 0

    visible = arr[:, :, 3] > 0
    rows = np.any(visible, axis=1)
    cols = np.any(visible, axis=0)
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    pad = 10
    rmin = max(0, rmin - pad)
    cmin = max(0, cmin - pad)
    rmax = min(arr.shape[0] - 1, rmax + pad)
    cmax = min(arr.shape[1] - 1, cmax + pad)

    cropped = Image.fromarray(arr[rmin:rmax+1, cmin:cmax+1])
    return cropped


def erase_baked_in_truck(image: Image.Image) -> Image.Image:
    arr = np.array(image.convert("RGBA"))
    h = arr.shape[0]
    top_zone = int(h * 0.20)

    region = arr[:top_zone, :, :]
    orange = (
        (region[:, :, 0] > 180) &
        (region[:, :, 1] > 80)  & (region[:, :, 1] < 160) &
        (region[:, :, 2] < 80)
    )
    if not np.any(orange):
        return image

    ys, xs = np.where(orange)
    y1 = max(0, int(ys.min()) - 12)
    y2 = min(top_zone, int(ys.max()) + 12)
    x1 = max(0, int(xs.min()) - 12)
    x2 = min(arr.shape[1], int(xs.max()) + 12)
    arr[y1:y2, x1:x2] = [255, 255, 255, 255]
    return Image.fromarray(arr)


def split_product_and_side_tag(prod_resized: Image.Image):
    """
    Split a product image by scanning right-to-left to find the white gap 
    between the side tag and the product.
    """
    arr = np.array(prod_resized)
    h, w = arr.shape[:2]
    
    # 1. Create a mask of non-white pixels
    nw_mask = (arr[:, :, 0] < 240) | (arr[:, :, 1] < 240) | (arr[:, :, 2] < 240)
    col_counts = np.sum(nw_mask, axis=0)

    side_tag_right = None
    split_x = None

    # 2. Find the right-most edge of the side tag
    for x in range(w - 1, int(w * 0.5), -1):
        if col_counts[x] > h * 0.1:  # At least 10% of column has content
            side_tag_right = x
            break

    if side_tag_right is None:
        return prod_resized, None, w

    # 3. Move left from the tag until we hit an empty vertical gap
    for x in range(side_tag_right, int(w * 0.3), -1):
        if col_counts[x] < 2:  # Found a purely white column (the gap!)
            split_x = x
            break

    if split_x is None:
        return prod_resized, None, w

    # 4. Validate that what we isolated on the right is actually a side tag
    right = arr[:, split_x:side_tag_right+1, :3]
    tag_nw_mask = (right[:, :, 0] < 240) | (right[:, :, 1] < 240) | (right[:, :, 2] < 240)
    nw_pixels = right[tag_nw_mask]

    if len(nw_pixels) == 0:
        return prod_resized, None, w

    # Check for navy blue dominance
    navy = ((nw_pixels[:, 2] > nw_pixels[:, 0]) &
            (nw_pixels[:, 2] > nw_pixels[:, 1]) &
            (nw_pixels[:, 0] < 150))
    navy_pct = float(navy.sum()) / len(nw_pixels)

    # Check aspect ratio (must be tall and narrow)
    nw_coords = np.where(tag_nw_mask)
    content_w = int(nw_coords[1].max() - nw_coords[1].min()) + 1
    content_h = int(nw_coords[0].max() - nw_coords[0].min()) + 1
    aspect = content_h / max(content_w, 1)

    # If it's not a navy tag or not tall enough, abort split
    if navy_pct < 0.35 or aspect < 1.5:
        return prod_resized, None, w

    # 5. Successfully split!
    bottles = prod_resized.crop((0, 0, split_x, h))
    side_tag = prod_resized.crop((split_x, 0, w, h))
    
    return bottles, side_tag, split_x


def content_bbox(img: Image.Image):
    """Return (left, right, top, bottom) of non-white content in image."""
    arr = np.array(img.convert("RGB"))
    nw = np.where((arr[:, :, 0] < 240) | (arr[:, :, 1] < 240) | (arr[:, :, 2] < 240))
    if len(nw[0]) == 0:
        return 0, img.width, 0, img.height
    return int(nw[1].min()), int(nw[1].max()), int(nw[0].min()), int(nw[0].max())


def composite_image(product_image: Image.Image,
                    position: str,
                    prod_scale: int,
                    tag_width_pct: int) -> Image.Image:
    CANVAS       = 1000
    SIDE_MARGIN  = 90
    TRUCK_TOP    = 55
    PANEL_GAP    = 20
    
    # Target content height: 700px (leaves exactly 150px margin top and bottom)
    TARGET_CONTENT_H = 700.0

    prod = erase_baked_in_truck(product_image.convert("RGBA"))

    detect_size = 950
    prod_detect = prod.resize((detect_size, detect_size), Image.Resampling.LANCZOS)
    bottles_det, side_tag_det, split_x_det = split_product_and_side_tag(prod_detect)
    has_side_tag = side_tag_det is not None

    tag = load_free_delivery_tag()
    user_factor = prod_scale / 100.0

    if has_side_tag:
        orig_h, orig_w = np.array(prod).shape[:2]
        split_ratio = split_x_det / detect_size
        orig_split = int(orig_w * split_ratio)

        bottles_orig = prod.crop((0, 0, orig_split, orig_h))
        sidetag_orig = prod.crop((orig_split, 0, orig_w, orig_h))

        # 1. CROP to pure content (removes all invisible white space)
        b_left, b_right, b_top, b_bottom = content_bbox(bottles_orig)
        s_left, s_right, s_top, s_bottom = content_bbox(sidetag_orig)

        bottles_content = bottles_orig.crop((b_left, b_top, b_right, b_bottom))
        sidetag_content = sidetag_orig.crop((s_left, s_top, s_right, s_bottom))

        # 2. SCALE up to the target 700px height based on the tallest element
        target_h = TARGET_CONTENT_H * user_factor
        max_orig_h = max(bottles_content.height, sidetag_content.height)
        scale = target_h / max(max_orig_h, 1)

        bw = max(10, int(bottles_content.width * scale))
        bh = max(10, int(bottles_content.height * scale))
        sw = max(10, int(sidetag_content.width * scale))
        sh = max(10, int(sidetag_content.height * scale))

        bottles_scaled = bottles_content.resize((bw, bh), Image.Resampling.LANCZOS)
        sidetag_scaled = sidetag_content.resize((sw, sh), Image.Resampling.LANCZOS)

        # 3. POSITION horizontally and group them tightly
        GAP = 50 # Tight gap between the bottles and the side tag
        total_w = bottles_scaled.width + GAP + sidetag_scaled.width

        # Prevent it from exceeding canvas width
        if total_w > CANVAS - 100:
            shrink = (CANVAS - 100) / total_w
            scale *= shrink
            bottles_scaled = bottles_content.resize((int(bottles_content.width * scale), int(bottles_content.height * scale)), Image.Resampling.LANCZOS)
            sidetag_scaled = sidetag_content.resize((int(sidetag_content.width * scale), int(sidetag_content.height * scale)), Image.Resampling.LANCZOS)
            total_w = bottles_scaled.width + GAP + sidetag_scaled.width

        # Center horizontally and vertically
        start_x = (CANVAS - total_w) // 2
        bx = start_x
        sx = start_x + bottles_scaled.width + GAP
        
        by = (CANVAS - bottles_scaled.height) // 2
        sy = (CANVAS - sidetag_scaled.height) // 2

        canvas = Image.new("RGBA", (CANVAS, CANVAS), (255, 255, 255, 255))
        canvas.paste(bottles_scaled, (bx, by), bottles_scaled)
        canvas.paste(sidetag_scaled, (sx, sy), sidetag_scaled)

        if tag is None:
            st.warning(f"⚠️ '{FREE_DELIVERY_FILE}' not found next to the app.")
            return canvas.convert("RGB")

        # 4. TRUCK OVERLAY LOGIC
        tag_w = int(CANVAS * tag_width_pct / 100)
        tag_h = int(tag.height * tag_w / tag.width)

        pos_map = {
            "Top Right":    (CANVAS - tag_w - SIDE_MARGIN, TRUCK_TOP),
            "Top Left":      (SIDE_MARGIN, TRUCK_TOP),
            "Bottom Right": (CANVAS - tag_w - SIDE_MARGIN, CANVAS - tag_h - TRUCK_TOP),
            "Bottom Left":  (SIDE_MARGIN, CANVAS - tag_h - TRUCK_TOP),
        }
        tx, ty = pos_map.get(position, pos_map["Top Right"])

        # Shift side tag down smoothly if truck overlaps
        overlap_x = (tx < sx + sidetag_scaled.width) and (tx + tag_w > sx)
        truck_bottom = ty + tag_h
        
        if position == "Top Right" and (truck_bottom + PANEL_GAP > sy) and overlap_x:
            new_sy = truck_bottom + PANEL_GAP
            avail_h = (by + bottles_scaled.height) - new_sy 
            
            if avail_h > 0:
                # Shrink side tag if it gets pushed past the bottom of the bottles
                if sidetag_scaled.height > avail_h:
                    shrink_st = avail_h / sidetag_scaled.height
                    new_sw = max(10, int(sidetag_scaled.width * shrink_st))
                    new_sh = max(10, int(sidetag_scaled.height * shrink_st))
                    sidetag_scaled2 = sidetag_content.resize((new_sw, new_sh), Image.Resampling.LANCZOS)
                else:
                    sidetag_scaled2 = sidetag_scaled
                
                # Align right edge dynamically
                new_sx = (sx + sidetag_scaled.width) - sidetag_scaled2.width
                
                canvas = Image.new("RGBA", (CANVAS, CANVAS), (255, 255, 255, 255))
                canvas.paste(bottles_scaled, (bx, by), bottles_scaled)
                canvas.paste(sidetag_scaled2, (new_sx, new_sy), sidetag_scaled2)

        tag_resized = tag.resize((tag_w, tag_h), Image.Resampling.LANCZOS)
        canvas.paste(tag_resized, (tx, ty), tag_resized)

    else:
        # NO SIDE TAG logic (also strips white space perfectly)
        p_left, p_right, p_top, p_bottom = content_bbox(prod)
        prod_content = prod.crop((p_left, p_top, p_right, p_bottom))

        target_h = TARGET_CONTENT_H * user_factor
        scale = target_h / max(prod_content.height, 1)

        pw = max(10, int(prod_content.width * scale))
        ph = max(10, int(prod_content.height * scale))

        if pw > CANVAS - 100:
            shrink = (CANVAS - 100) / pw
            pw = max(10, int(pw * shrink))
            ph = max(10, int(ph * shrink))

        prod_scaled = prod_content.resize((pw, ph), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (CANVAS, CANVAS), (255, 255, 255, 255))
        cx = (CANVAS - prod_scaled.width) // 2
        cy = (CANVAS - prod_scaled.height) // 2
        canvas.paste(prod_scaled, (cx, cy), prod_scaled)

        if tag is None:
            st.warning(f"⚠️ '{FREE_DELIVERY_FILE}' not found next to the app.")
            return canvas.convert("RGB")

        tag_w = int(CANVAS * tag_width_pct / 100)
        tag_h = int(tag.height * tag_w / tag.width)
        pos_map = {
            "Top Right":    (CANVAS - tag_w - SIDE_MARGIN, TRUCK_TOP),
            "Top Left":      (SIDE_MARGIN, TRUCK_TOP),
            "Bottom Right": (CANVAS - tag_w - SIDE_MARGIN, CANVAS - tag_h - TRUCK_TOP),
            "Bottom Left":  (SIDE_MARGIN, CANVAS - tag_h - TRUCK_TOP),
        }
        tx, ty = pos_map.get(position, pos_map["Top Right"])

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
