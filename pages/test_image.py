import os
import re
import zipfile

import streamlit as st
from PIL import Image
import requests
from io import BytesIO
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS — tweak these if you ever need to adjust
# ══════════════════════════════════════════════════════════════════════════════

# How far from the tag borders the product will sit (8% of the safe zone)
MARGIN_PERCENT = 0.05

# Safe zone definition (matches your tag template layout)
BANNER_RATIO     = 0.095   # bottom banner height as fraction of canvas height
VERT_STRIP_RATIO = 0.18    # right vertical strip width as fraction of canvas width

# Auto-crop whitespace threshold (pixels brighter than this are treated as background)
WHITE_THRESHOLD = 240

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Refurbished Tag Generator",
    page_icon="🔖",
    layout="wide"
)

st.title("Refurbished Product Tag Generator")
st.markdown("Upload a product image and add a refurbished grade tag to it!")

# ── Sidebar ────────────────────────────────────────────────────────────────────
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

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**How it works:**\n\n"
    "1. Whitespace is automatically trimmed from the product image\n"
    "2. Product is scaled to fill the tag's safe zone\n"
    "3. A 5% margin keeps it clear of all borders\n\n"
    "_No manual adjustments needed!_"
)

# ── Tag file mapping ───────────────────────────────────────────────────────────
tag_files = {
    "Renewed":     "RefurbishedStickerUpdated-Renewd.png",
    "Refurbished": "RefurbishedStickerUpdate-No-Grading.png",
    "Grade A":     "Refurbished-StickerUpdated-Grade-A.png",
    "Grade B":     "Refurbished-StickerUpdated-Grade-B.png",
    "Grade C":     "Refurbished-StickerUpdated-Grade-C.png",
}

def get_tag_path(filename):
    for path in [filename,
                 os.path.join(os.path.dirname(__file__), filename),
                 os.path.join(os.getcwd(), filename)]:
        if os.path.exists(path):
            return path
    return filename


# ══════════════════════════════════════════════════════════════════════════════
#  CORE IMAGE PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def auto_crop_whitespace(image: Image.Image) -> Image.Image:
    """
    Trim surrounding whitespace from a product image.
    Scans for non-white pixels and crops tightly around them.
    Works on both transparent PNGs and white-background JPEGs.
    """
    img_rgb = image.convert("RGB")
    pixels  = list(img_rgb.getdata())
    w, h    = img_rgb.size

    non_white = [
        (i % w, i // w)
        for i, (r, g, b) in enumerate(pixels)
        if not (r > WHITE_THRESHOLD and g > WHITE_THRESHOLD and b > WHITE_THRESHOLD)
    ]

    if not non_white:
        return image  # entirely white — return as-is, let margin handle it

    xs = [p[0] for p in non_white]
    ys = [p[1] for p in non_white]
    bbox = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    return image.crop(bbox)


def fit_with_margin(product_image: Image.Image,
                    tag_image: Image.Image) -> Image.Image:
    """
    1. Calculate the safe zone inside the tag template.
    2. Apply MARGIN_PERCENT inset on all sides.
    3. Scale the (already-cropped) product to fill that inner area.
    4. Centre it and composite the tag on top.
    """
    canvas_w, canvas_h = tag_image.size

    # Safe zone (excludes the tag's right strip and bottom banner)
    safe_w = canvas_w - int(canvas_w * VERT_STRIP_RATIO)
    safe_h = canvas_h - int(canvas_h * BANNER_RATIO)

    # Inner area after applying margin
    margin_x = int(safe_w * MARGIN_PERCENT)
    margin_y = int(safe_h * MARGIN_PERCENT)
    inner_w  = safe_w - 2 * margin_x
    inner_h  = safe_h - 2 * margin_y

    # Best-fit scale: respect aspect ratio, fill as much of inner area as possible
    prod_w, prod_h = product_image.size
    scale  = min(inner_w / prod_w, inner_h / prod_h)
    new_w  = int(prod_w * scale)
    new_h  = int(prod_h * scale)

    product_resized = product_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # White canvas
    result = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))

    # Centre within the inner (margined) area
    x = margin_x + (inner_w - new_w) // 2
    y = margin_y + (inner_h - new_h) // 2

    if product_resized.mode == "RGBA":
        result.paste(product_resized, (x, y), product_resized)
    else:
        result.paste(product_resized, (x, y))

    # Overlay tag template on top
    if tag_image.mode == "RGBA":
        result.paste(tag_image, (0, 0), tag_image)
    else:
        result.paste(tag_image, (0, 0))

    return result


def process_single(product_image: Image.Image,
                   tag_image: Image.Image) -> Image.Image:
    """Full pipeline: auto-crop whitespace → fit with margin → composite."""
    cropped = auto_crop_whitespace(product_image.convert("RGBA"))
    return fit_with_margin(cropped, tag_image)


def image_to_bytes(img: Image.Image, quality=95) -> bytes:
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  JUMIA SCRAPING HELPERS
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


def get_driver(headless=True):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        st.error("Selenium not installed.")
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
        import time; time.sleep(1)
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
                        src = base_url + src
                    image_url = src
                    break
        if not image_url:
            st.warning("Found product page but could not extract image.")
            return None
        r = requests.get(image_url,
                         headers={"User-Agent": "Mozilla/5.0", "Referer": base_url},
                         timeout=15)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        st.error(f"Error: {e}")
        return None
    finally:
        if driver:
            try: driver.quit()
            except Exception: pass


# ══════════════════════════════════════════════════════════════════════════════
#  SINGLE IMAGE MODE
# ══════════════════════════════════════════════════════════════════════════════
if processing_mode == "Single Image":
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Upload Product Image")
        upload_method = st.radio(
            "Source:",
            ["Upload from device", "Load from Image URL", "Load from SKU"],
            horizontal=True,
        )

        product_image = None

        if upload_method == "Upload from device":
            f = st.file_uploader("Choose an image file",
                                  type=["png", "jpg", "jpeg", "webp"])
            if f:
                product_image = Image.open(f).convert("RGBA")

        elif upload_method == "Load from Image URL":
            url = st.text_input("Image URL:")
            if url:
                try:
                    product_image = Image.open(
                        BytesIO(requests.get(url).content)).convert("RGBA")
                    st.success("Image loaded!")
                except Exception as e:
                    st.error(f"Could not load image: {e}")

        else:  # SKU
            sku_input = st.text_input("Product SKU:",
                                       placeholder="e.g. GE840EA6C62GANAFAMZ")
            site = st.radio("Jumia site:", ["Jumia Kenya", "Jumia Uganda"],
                             horizontal=True)
            if sku_input:
                base = ("https://www.jumia.co.ke" if site == "Jumia Kenya"
                        else "https://www.jumia.ug")
                if st.button("Search & Extract Image", use_container_width=True):
                    with st.spinner("Searching…"):
                        product_image = search_jumia_by_sku(
                            sku_input, base, f"{base}/catalog/?q={sku_input}")
                        if product_image:
                            st.success("Image found!")
                        else:
                            st.error("Could not find product.")

    with col2:
        st.subheader("Preview")

        if product_image is not None:
            tag_path = get_tag_path(tag_files[tag_type])
            if not os.path.exists(tag_path):
                st.error(f"Tag file not found: **{tag_files[tag_type]}**")
                st.info("Make sure the tag PNG files are in the same folder as this app.")
                st.stop()

            tag_image = Image.open(tag_path).convert("RGBA")
            result    = process_single(product_image, tag_image)

            st.image(result, use_container_width=True,
                     caption=f"{tag_type} · auto-fitted with 5% margin")

            st.markdown("---")
            st.download_button(
                label="⬇️ Download Tagged Image (JPEG)",
                data=image_to_bytes(result),
                file_name=f"refurbished_{tag_type.lower().replace(' ', '_')}.jpg",
                mime="image/jpeg",
                use_container_width=True,
            )
        else:
            st.info("← Load an image to see the preview here.")


# ══════════════════════════════════════════════════════════════════════════════
#  BULK PROCESSING MODE
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.subheader("Bulk Processing")
    st.markdown(
        "Images are **automatically cropped and fitted** — "
        "no adjustments needed."
    )

    bulk_method = st.radio(
        "Input method:",
        ["Upload multiple images", "Enter URLs manually",
         "Upload Excel file with URLs", "Enter SKUs"],
    )

    products_to_process = []  # list of (PIL Image, filename str)

    if bulk_method == "Upload multiple images":
        files = st.file_uploader("Choose image files",
                                  type=["png", "jpg", "jpeg", "webp"],
                                  accept_multiple_files=True)
        if files:
            st.info(f"{len(files)} files uploaded")
            for f in files:
                try:
                    img = Image.open(f).convert("RGBA")
                    products_to_process.append((img, f.name.rsplit(".", 1)[0]))
                except Exception as e:
                    st.warning(f"Could not load {f.name}: {e}")

    elif bulk_method == "Enter URLs manually":
        raw = st.text_area("Image URLs (one per line):", height=180,
                            placeholder="https://example.com/image1.jpg")
        if raw.strip():
            for i, url in enumerate([u.strip() for u in raw.splitlines() if u.strip()]):
                try:
                    r = requests.get(url, timeout=10); r.raise_for_status()
                    img = Image.open(BytesIO(r.content)).convert("RGBA")
                    products_to_process.append((img, f"image_{i+1}"))
                except Exception as e:
                    st.warning(f"Could not load URL {i+1}: {e}")

    elif bulk_method == "Upload Excel file with URLs":
        st.markdown("**Column A:** Image URLs · **Column B (optional):** Product name")
        xf = st.file_uploader("Excel file", type=["xlsx", "xls"])
        if xf:
            try:
                import pandas as pd
                df    = pd.read_excel(xf)
                urls  = df.iloc[:, 0].dropna().astype(str).tolist()
                names = (df.iloc[:, 1].dropna().astype(str).tolist()
                         if len(df.columns) > 1
                         else [f"product_{i+1}" for i in range(len(urls))])
                st.info(f"Found {len(urls)} URLs")
                for i, (url, name) in enumerate(zip(urls, names)):
                    try:
                        r = requests.get(url, timeout=10); r.raise_for_status()
                        img   = Image.open(BytesIO(r.content)).convert("RGBA")
                        clean = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
                        products_to_process.append((img, clean or f"product_{i+1}"))
                    except Exception as e:
                        st.warning(f"Could not load {name}: {e}")
            except Exception as e:
                st.error(f"Excel error: {e}")

    else:  # SKUs
        skus_raw  = st.text_area("SKUs (one per line):", height=180,
                                  placeholder="GE840EA6C62GANAFAMZ")
        site_bulk = st.radio("Jumia site:", ["Jumia Kenya", "Jumia Uganda"],
                              horizontal=True, key="bulk_site")
        if skus_raw.strip():
            skus = [s.strip() for s in skus_raw.splitlines() if s.strip()]
            st.info(f"{len(skus)} SKUs entered")
            if st.button("Search All SKUs", use_container_width=True):
                base = ("https://www.jumia.co.ke" if site_bulk == "Jumia Kenya"
                        else "https://www.jumia.ug")
                prog   = st.progress(0)
                status = st.empty()
                for i, sku in enumerate(skus):
                    status.text(f"Processing {i+1}/{len(skus)}: {sku}")
                    img = search_jumia_by_sku(sku, base, f"{base}/catalog/?q={sku}")
                    if img:
                        products_to_process.append((img, sku))
                    else:
                        st.warning(f"No image for SKU: {sku}")
                    prog.progress((i + 1) / len(skus))
                status.text(f"Done — {len(products_to_process)}/{len(skus)} found")

    # ── Preview grid ───────────────────────────────────────────────────────────
    if products_to_process:
        st.markdown("---")
        st.subheader(f"{len(products_to_process)} images ready")

        cols_per_row = 4
        for row_start in range(0, len(products_to_process), cols_per_row):
            cols = st.columns(cols_per_row)
            for col_idx, (img, name) in enumerate(
                    products_to_process[row_start: row_start + cols_per_row]):
                with cols[col_idx]:
                    st.image(img.convert("RGB"), caption=name,
                             use_container_width=True)

        st.markdown("---")

        if st.button("⚙️ Process All Images", use_container_width=True):
            tag_path = get_tag_path(tag_files[tag_type])
            if not os.path.exists(tag_path):
                st.error(f"Tag file not found: {tag_files[tag_type]}")
                st.stop()

            tag_image  = Image.open(tag_path).convert("RGBA")
            prog       = st.progress(0)
            processed  = []

            for i, (raw_img, name) in enumerate(products_to_process):
                try:
                    result = process_single(raw_img, tag_image)
                    processed.append((result, name))
                except Exception as e:
                    st.warning(f"Error on {name}: {e}")
                prog.progress((i + 1) / len(products_to_process))

            if processed:
                st.success(f"✅ {len(processed)} images processed!")

                zip_buf = BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for img, name in processed:
                        zf.writestr(f"{name}_1.jpg", image_to_bytes(img))
                zip_buf.seek(0)

                st.download_button(
                    label=f"⬇️ Download All {len(processed)} Images (ZIP)",
                    data=zip_buf,
                    file_name=f"refurbished_{tag_type.lower().replace(' ', '_')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

                st.markdown("### Preview")
                prev_cols = st.columns(4)
                for i, (img, name) in enumerate(processed[:8]):
                    with prev_cols[i % 4]:
                        st.image(img, caption=name, use_container_width=True)
                if len(processed) > 8:
                    st.caption(f"Showing 8 of {len(processed)}")
            else:
                st.error("No images were successfully processed.")
    else:
        st.info("Provide images above to get started.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#888'>"
    "Auto-crop trims whitespace · 5% margin keeps product clear of tag borders"
    "</div>",
    unsafe_allow_html=True,
)
