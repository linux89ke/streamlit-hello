import os
import re
import zipfile
import hashlib

import streamlit as st
from PIL import Image, ImageOps
import requests
from io import BytesIO

# ── streamlit-cropper (install with: pip install streamlit-cropper) ───────────
try:
    from streamlit_cropper import st_cropper
    CROPPER_AVAILABLE = True
except ImportError:
    CROPPER_AVAILABLE = False

from bs4 import BeautifulSoup

# ── Page config ────────────────────────────────────────────────────────────────
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

# ── Tag file mapping ───────────────────────────────────────────────────────────
tag_files = {
    "Renewed":      "RefurbishedStickerUpdated-Renewd.png",
    "Refurbished":  "RefurbishedStickerUpdate-No-Grading.png",
    "Grade A":      "Refurbished-StickerUpdated-Grade-A.png",
    "Grade B":      "Refurbished-StickerUpdated-Grade-B.png",
    "Grade C":      "Refurbished-StickerUpdated-Grade-C.png",
}

def get_tag_path(filename):
    for path in [filename,
                 os.path.join(os.path.dirname(__file__), filename),
                 os.path.join(os.getcwd(), filename)]:
        if os.path.exists(path):
            return path
    return filename


# ── Core compositing ───────────────────────────────────────────────────────────
def auto_crop_whitespace(image: Image.Image, padding: int = 10) -> Image.Image:
    """
    Automatically trim surrounding whitespace/transparency from an image.
    Works on both transparent PNGs and white-background JPEGs.
    padding: pixels of breathing room to leave around the detected product.
    """
    img = image.convert("RGBA")
    # Create a white background to detect whitespace
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    diff = Image.new("RGBA", img.size)

    # Find non-white pixels
    img_rgb = img.convert("RGB")
    bbox = None

    pixels = list(img_rgb.getdata())
    w, h = img_rgb.size
    non_white = [(i % w, i // w) for i, p in enumerate(pixels)
                 if not (p[0] > 240 and p[1] > 240 and p[2] > 240)]

    if non_white:
        xs = [p[0] for p in non_white]
        ys = [p[1] for p in non_white]
        left   = max(0, min(xs) - padding)
        top    = max(0, min(ys) - padding)
        right  = min(w, max(xs) + padding)
        bottom = min(h, max(ys) + padding)
        bbox = (left, top, right, bottom)

    if bbox:
        return image.crop(bbox)
    return image  # fallback: return original if nothing found


def composite_onto_tag(product_image: Image.Image,
                        tag_image: Image.Image) -> Image.Image:
    """
    Fit product_image into the safe zone of tag_image (best-fit, centred).
    The product_image passed in should already be cropped to the product only.
    """
    canvas_w, canvas_h = tag_image.size

    # Safe zone: exclude the right vertical strip and the bottom banner
    banner_h    = int(canvas_h * 0.095)
    vert_strip_w = int(canvas_w * 0.18)
    safe_w = canvas_w - vert_strip_w
    safe_h = canvas_h - banner_h

    # Best-fit scale inside safe zone
    prod_w, prod_h = product_image.size
    scale = min(safe_w / prod_w, safe_h / prod_h)
    new_w = int(prod_w * scale)
    new_h = int(prod_h * scale)

    product_resized = product_image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # White canvas
    result = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))

    # Centre within safe zone
    x = (safe_w - new_w) // 2
    y = (safe_h - new_h) // 2

    if product_resized.mode == "RGBA":
        result.paste(product_resized, (x, y), product_resized)
    else:
        result.paste(product_resized, (x, y))

    # Overlay tag on top
    if tag_image.mode == "RGBA":
        result.paste(tag_image, (0, 0), tag_image)
    else:
        result.paste(tag_image, (0, 0))

    return result


def image_to_bytes(img: Image.Image, fmt="JPEG", quality=95) -> bytes:
    buf = BytesIO()
    img.save(buf, format=fmt, quality=quality)
    return buf.getvalue()


# ── Jumia scraping helpers (unchanged) ────────────────────────────────────────
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
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
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
            st.warning("Found product but could not extract image.")
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

    if not CROPPER_AVAILABLE:
        st.warning(
            "📦 **streamlit-cropper** is not installed. "
            "Run `pip install streamlit-cropper` then restart the app "
            "to enable interactive cropping. "
            "Auto-crop (whitespace trimming) is being used as fallback."
        )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1 · Load Image")
        upload_method = st.radio(
            "Source:",
            ["Upload from device", "Load from Image URL", "Load from SKU"],
            horizontal=True,
        )

        raw_image = None   # original PIL image, before any crop

        if upload_method == "Upload from device":
            f = st.file_uploader("Choose an image file",
                                  type=["png", "jpg", "jpeg", "webp"])
            if f:
                raw_image = Image.open(f).convert("RGBA")

        elif upload_method == "Load from Image URL":
            url = st.text_input("Image URL:")
            if url:
                try:
                    raw_image = Image.open(
                        BytesIO(requests.get(url).content)).convert("RGBA")
                    st.success("Loaded!")
                except Exception as e:
                    st.error(f"Could not load image: {e}")

        else:  # SKU
            sku_input = st.text_input("Product SKU:",
                                       placeholder="e.g. GE840EA6C62GANAFAMZ")
            site = st.radio("Jumia site:", ["Jumia Kenya", "Jumia Uganda"],
                             horizontal=True)
            if sku_input:
                base = "https://www.jumia.co.ke" if site == "Jumia Kenya" \
                       else "https://www.jumia.ug"
                search = f"{base}/catalog/?q={sku_input}"
                if st.button("Search & Extract Image", use_container_width=True):
                    with st.spinner("Searching…"):
                        raw_image = search_jumia_by_sku(sku_input, base, search)
                        if raw_image:
                            st.success("Image found!")
                        else:
                            st.error("Could not find product.")

        # ── Cropping step ──────────────────────────────────────────────────────
        cropped_image = None

        if raw_image is not None:
            st.markdown("---")
            st.subheader("2 · Crop to Product")

            if CROPPER_AVAILABLE:
                st.markdown(
                    "Drag the handles to frame the product tightly. "
                    "Remove any excess whitespace for the best result."
                )
                # st_cropper returns the cropped PIL image live
                cropped_image = st_cropper(
                    raw_image.convert("RGB"),   # cropper needs RGB
                    realtime_update=True,
                    box_color="#FF4B4B",
                    aspect_ratio=None,          # free-form crop
                )
                st.caption("✂️ Adjust the red box, then check the preview →")

            else:
                # Fallback: auto-trim whitespace
                st.info("🤖 Auto-cropping whitespace…")
                cropped_image = auto_crop_whitespace(raw_image)
                st.image(cropped_image.convert("RGB"),
                         caption="Auto-cropped preview", use_container_width=True)

    with col2:
        st.subheader("3 · Preview & Download")

        if cropped_image is not None:
            tag_filename = tag_files[tag_type]
            tag_path = get_tag_path(tag_filename)

            if not os.path.exists(tag_path):
                st.error(f"Tag file not found: **{tag_filename}**")
                st.info("Make sure the tag PNG files are in the same folder as this app.")
                st.stop()

            tag_image = Image.open(tag_path).convert("RGBA")

            # Convert cropped to RGBA for compositing
            if cropped_image.mode != "RGBA":
                cropped_image = cropped_image.convert("RGBA")

            result = composite_onto_tag(cropped_image, tag_image)

            st.image(result, use_container_width=True,
                     caption=f"Tagged · {tag_type}")

            st.markdown("---")
            buf = BytesIO()
            result.save(buf, format="JPEG", quality=95)
            buf.seek(0)
            st.download_button(
                label="⬇️ Download Tagged Image (JPEG)",
                data=buf,
                file_name=f"refurbished_{tag_type.lower().replace(' ','_')}.jpg",
                mime="image/jpeg",
                use_container_width=True,
            )
        else:
            st.info("← Load an image and crop it to see the preview here.")


# ══════════════════════════════════════════════════════════════════════════════
#  BULK PROCESSING MODE
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.subheader("Bulk Processing")
    st.markdown(
        "Images are **auto-cropped** (whitespace trimming) then composited. "
        "For pixel-perfect results on individual images, use Single Image mode."
    )

    bulk_method = st.radio(
        "Input method:",
        ["Upload multiple images", "Enter URLs manually",
         "Upload Excel file with URLs", "Enter SKUs"],
    )

    products_to_process = []  # list of (PIL Image, filename_str)

    # ── Input collection ───────────────────────────────────────────────────────
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
                df = pd.read_excel(xf)
                urls  = df.iloc[:, 0].dropna().astype(str).tolist()
                names = (df.iloc[:, 1].dropna().astype(str).tolist()
                         if len(df.columns) > 1
                         else [f"product_{i+1}" for i in range(len(urls))])
                st.info(f"Found {len(urls)} URLs")
                for i, (url, name) in enumerate(zip(urls, names)):
                    try:
                        r = requests.get(url, timeout=10); r.raise_for_status()
                        img = Image.open(BytesIO(r.content)).convert("RGBA")
                        clean = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
                        products_to_process.append((img, clean or f"product_{i+1}"))
                    except Exception as e:
                        st.warning(f"Could not load {name}: {e}")
            except Exception as e:
                st.error(f"Excel error: {e}")

    else:  # SKUs
        skus_raw = st.text_area("SKUs (one per line):", height=180,
                                 placeholder="GE840EA6C62GANAFAMZ")
        site_bulk = st.radio("Jumia site:", ["Jumia Kenya", "Jumia Uganda"],
                              horizontal=True, key="bulk_site")
        if skus_raw.strip():
            skus = [s.strip() for s in skus_raw.splitlines() if s.strip()]
            st.info(f"{len(skus)} SKUs entered")
            if st.button("Search All SKUs", use_container_width=True):
                base = ("https://www.jumia.co.ke" if site_bulk == "Jumia Kenya"
                        else "https://www.jumia.ug")
                prog = st.progress(0)
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
        st.subheader(f"Loaded {len(products_to_process)} images")
        st.caption("Auto-crop will trim whitespace before compositing.")

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

            tag_image = Image.open(tag_path).convert("RGBA")
            prog = st.progress(0)
            processed = []

            for i, (raw_img, name) in enumerate(products_to_process):
                try:
                    cropped = auto_crop_whitespace(raw_img)
                    result  = composite_onto_tag(cropped, tag_image)
                    processed.append((result, name))
                except Exception as e:
                    st.warning(f"Error on {name}: {e}")
                prog.progress((i + 1) / len(products_to_process))

            if processed:
                st.success(f"✅ {len(processed)} images processed!")

                # ZIP download
                zip_buf = BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for img, name in processed:
                        zf.writestr(f"{name}_1.jpg", image_to_bytes(img))
                zip_buf.seek(0)

                st.download_button(
                    label=f"⬇️ Download All {len(processed)} Images (ZIP)",
                    data=zip_buf,
                    file_name=f"refurbished_{tag_type.lower().replace(' ','_')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

                # Preview first 8
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
    "Single Image: drag the crop box for perfect framing · "
    "Bulk: auto-crop trims whitespace automatically"
    "</div>",
    unsafe_allow_html=True,
)
