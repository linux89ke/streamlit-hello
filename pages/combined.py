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
    page_icon=":material/label:",
    layout="wide"
)

# ══════════════════════════════════════════════════════════════════════════════
#  JUMIA BRAND THEME  (injected once, right after set_page_config)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── Jumia palette ──────────────────────────────────────────────────────────
   Primary orange : #F68B1E
   Dark orange    : #D4730A
   Light orange bg: #FFF4E6
   Dark text      : #1A1A1A
   Mid grey       : #6B6B6B
   Border grey    : #E0E0E0
   White          : #FFFFFF
──────────────────────────────────────────────────────────────────────────── */

/* Google Font — Nunito (clean, friendly, close to Jumia's wordmark feel) */
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Nunito', sans-serif;
    color: #1A1A1A;
}

/* ── Page background ──────────────────────────────────────────────────────── */
.stApp {
    background-color: #FAFAFA;
}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1A1A1A 0%, #2D2D2D 100%);
    border-right: 3px solid #F68B1E;
}
[data-testid="stSidebar"] * {
    color: #F5F5F5 !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stCheckbox label,
[data-testid="stSidebar"] .stRadio label {
    color: #CCCCCC !important;
    font-size: 0.85rem;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #F68B1E !important;
    font-weight: 800;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #F68B1E44;
    padding-bottom: 4px;
    margin-bottom: 8px;
}
/* Sidebar selectbox container + border */
[data-testid="stSidebar"] [data-baseweb="select"] > div:first-child {
    background-color: #3A3A3A !important;
    border-color: #F68B1E !important;
    border-radius: 6px !important;
}
/* Selected value text — must be light on the dark sidebar background */
[data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stSelectboxValue"],
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div {
    color: #FFFFFF !important;
}
/* Dropdown list (rendered in a portal outside sidebar) */
[data-baseweb="popover"] [data-baseweb="menu"] {
    background-color: #2D2D2D !important;
}
[data-baseweb="popover"] [role="option"] {
    background-color: #2D2D2D !important;
    color: #F5F5F5 !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"] {
    background-color: #F68B1E !important;
    color: #FFFFFF !important;
}
/* Sidebar markdown paragraphs */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #AAAAAA !important;
    font-size: 0.8rem;
}

/* Sidebar info box */
[data-testid="stSidebar"] .stAlert {
    background-color: #F68B1E22 !important;
    border-left: 4px solid #F68B1E !important;
    color: #F68B1E !important;
}

/* ── Top header bar ───────────────────────────────────────────────────────── */
.jumia-header {
    background: linear-gradient(135deg, #F68B1E 0%, #D4730A 100%);
    border-radius: 12px;
    padding: 20px 28px 16px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 4px 16px #F68B1E44;
}
.jumia-header h1 {
    margin: 0;
    color: #FFFFFF;
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.1;
}
.jumia-header p {
    margin: 4px 0 0;
    color: #FFE0B2;
    font-size: 0.9rem;
}
.jumia-logo-dot {
    width: 48px;
    height: 48px;
    background: #FFFFFF;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.6rem;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}

/* ── Tab bar ──────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    gap: 4px;
    border-bottom: 2px solid #F68B1E;
}
[data-testid="stTabs"] button[role="tab"] {
    background: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    color: #6B6B6B;
    font-weight: 600;
    font-size: 0.88rem;
    padding: 8px 18px;
    transition: all 0.2s ease;
}
[data-testid="stTabs"] button[role="tab"]:hover {
    background: #FFF4E6;
    color: #F68B1E;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: #F68B1E;
    color: #FFFFFF !important;
    border-color: #F68B1E;
    font-weight: 700;
}

/* ── Primary buttons ──────────────────────────────────────────────────────── */
[data-testid="stButton"] button[kind="primary"],
[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #F68B1E 0%, #D4730A 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 0.9rem !important;
    padding: 10px 20px !important;
    box-shadow: 0 3px 10px #F68B1E55 !important;
    transition: all 0.2s ease !important;
}
[data-testid="stButton"] button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
    box-shadow: 0 5px 18px #F68B1E88 !important;
    transform: translateY(-1px);
}

/* Secondary / normal buttons */
[data-testid="stButton"] button:not([kind="primary"]),
[data-testid="stBaseButton-secondary"] {
    background: #FFFFFF !important;
    color: #F68B1E !important;
    border: 1.5px solid #F68B1E !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
[data-testid="stButton"] button:not([kind="primary"]):hover {
    background: #FFF4E6 !important;
}

/* Download button */
[data-testid="stDownloadButton"] button {
    background: linear-gradient(135deg, #F68B1E 0%, #D4730A 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    box-shadow: 0 3px 10px #F68B1E44 !important;
}

/* ── Metrics ──────────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #F0E0CC;
    border-left: 4px solid #F68B1E;
    border-radius: 10px;
    padding: 14px 16px !important;
    box-shadow: 0 2px 8px rgba(246,139,30,0.1);
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #F68B1E;
    font-weight: 800;
    font-size: 1.6rem;
}
[data-testid="stMetric"] [data-testid="stMetricLabel"] {
    color: #6B6B6B;
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* ── Cards / containers ───────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #F0E0CC !important;
    border-radius: 10px !important;
    overflow: hidden;
}
[data-testid="stExpander"] summary {
    background: #FFF4E6 !important;
    color: #1A1A1A !important;
    font-weight: 600;
}

/* ── Form inputs ──────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    border: 1.5px solid #E0E0E0 !important;
    border-radius: 8px !important;
    font-family: 'Nunito', sans-serif !important;
    transition: border-color 0.2s;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #F68B1E !important;
    box-shadow: 0 0 0 3px #F68B1E22 !important;
}

/* ── Slider ───────────────────────────────────────────────────────────────── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
    background: #F68B1E !important;
    border-color: #F68B1E !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] div[data-testid="stSlider"] {
    background: #F68B1E !important;
}

/* ── Info / success / warning / error alerts ──────────────────────────────── */
[data-testid="stAlert"][data-baseweb="notification"] {
    border-radius: 8px;
}
.stSuccess { border-left: 4px solid #F68B1E !important; }
.stInfo    { border-left: 4px solid #F68B1E !important; }

/* ── Dataframe header row ─────────────────────────────────────────────────── */
[data-testid="stDataFrame"] th {
    background-color: #F68B1E !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
}

/* ── File uploader ────────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    border: 2px dashed #F68B1E !important;
    border-radius: 10px !important;
    background: #FFF4E688 !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: transparent !important;
}

/* ── Radio buttons ────────────────────────────────────────────────────────── */
[data-testid="stRadio"] label[data-baseweb="radio"] div:first-child {
    border-color: #F68B1E !important;
}
[data-testid="stRadio"] [aria-checked="true"] div:first-child {
    background: #F68B1E !important;
    border-color: #F68B1E !important;
}

/* ── Checkbox ─────────────────────────────────────────────────────────────── */
[data-testid="stCheckbox"] input:checked + div {
    background: #F68B1E !important;
    border-color: #F68B1E !important;
}

/* ── Selectbox focus border ───────────────────────────────────────────────── */
[data-baseweb="select"]:focus-within {
    border-color: #F68B1E !important;
    box-shadow: 0 0 0 3px #F68B1E22 !important;
}

/* ── Horizontal divider ───────────────────────────────────────────────────── */
hr {
    border-color: #F0E0CC !important;
}

/* ── Caption / small text ─────────────────────────────────────────────────── */
[data-testid="stCaptionContainer"] {
    color: #6B6B6B;
    font-size: 0.8rem;
}

/* ── Subheader accent ─────────────────────────────────────────────────────── */
h2, h3 {
    color: #1A1A1A;
    font-weight: 700;
}
h2::after {
    content: '';
    display: block;
    width: 48px;
    height: 3px;
    background: #F68B1E;
    border-radius: 2px;
    margin-top: 4px;
}

/* ── Image borders ────────────────────────────────────────────────────────── */
[data-testid="stImage"] img {
    border-radius: 8px;
    border: 1px solid #F0E0CC;
}

/* ── Progress bar ─────────────────────────────────────────────────────────── */
[data-testid="stProgress"] div[role="progressbar"] > div {
    background: linear-gradient(90deg, #F68B1E, #D4730A) !important;
}

/* ── Spinner ──────────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] svg {
    color: #F68B1E !important;
}
</style>

<div class="jumia-header">
  <div class="jumia-logo-dot">🏷</div>
  <div>
    <h1>Jumia Refurbished Suite</h1>
    <p>Analyze listings &nbsp;·&nbsp; Apply grade tags &nbsp;·&nbsp; Convert existing tags</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
MARGIN_PERCENT   = 0.12
BANNER_RATIO     = 0.095
VERT_STRIP_RATIO = 0.18
WHITE_THRESHOLD  = 240

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

# ── Reverse map: domain string → country key ──────────────────────────────────
_DOMAIN_TO_COUNTRY: dict[str, str] = {v: k for k, v in DOMAIN_MAP.items()}

def detect_country_from_url(url: str) -> str | None:
    """
    Parse a URL and return the DOMAIN_MAP key if the domain matches a known
    Jumia country, otherwise return None.
    e.g. 'https://www.jumia.com.ng/...' → 'Nigeria (NG)'
    """
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
        for domain, country_key in _DOMAIN_TO_COUNTRY.items():
            if host == domain or host.endswith("." + domain):
                return country_key
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════
_defaults = {
    # Analyzer
    "scraped_results": [],
    "failed_items":    [],
    # Single-image tagging
    "single_img_bytes":  None,
    "single_img_label":  "",
    "single_img_source": None,
    "single_scale":      100,
    # Convert-tag tab
    "cv_img_bytes":  None,
    "cv_img_label":  "",
    "cv_img_source": None,
    # Bulk tagging — persisted SKU results
    "bulk_sku_results":  [],
    # Convert bulk — persisted SKU results
    "cv_bulk_sku_results": [],
    # Shared
    "individual_scales":   {},
    # Geo — auto-detected country key (e.g. "Kenya (KE)")
    "geo_country": None,
    # Country-mismatch dialog state
    "mismatch_detected":       False,   # True when a mismatch was just found
    "mismatch_url_country":    None,    # country key detected from URL/SKU
    "mismatch_active_country": None,    # country that was active when mismatch found
    "mismatch_context":        None,    # "single_tag" | "cv_single" | "bulk_sku" etc.
    "mismatch_resolved":       False,   # True once user clicked Switch or Ignore
    # Pending image load after mismatch resolution
    "pending_img_bytes":  None,
    "pending_img_label":  "",
    "pending_img_source": None,
    "pending_img_target": None,   # "single" | "cv_single"
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
#  GEO-DETECTION  — resolve user's country once per session
# ══════════════════════════════════════════════════════════════════════════════
# Maps ip-api.com country codes → DOMAIN_MAP keys
_COUNTRY_CODE_MAP = {
    "KE": "Kenya (KE)",
    "UG": "Uganda (UG)",
    "NG": "Nigeria (NG)",
    "MA": "Morocco (MA)",
    "GH": "Ghana (GH)",
}

def _detect_country() -> str | None:
    """Return a DOMAIN_MAP key for the user's IP location, or None."""
    try:
        r = requests.get("https://ipapi.co/json/", timeout=4)
        code = r.json().get("country_code","")
        return _COUNTRY_CODE_MAP.get(code)
    except Exception:
        return None

if st.session_state["geo_country"] is None:
    st.session_state["geo_country"] = _detect_country()

_geo_default = st.session_state["geo_country"]
_country_list = list(DOMAIN_MAP.keys())
_default_idx  = (
    _country_list.index(_geo_default)
    if _geo_default and _geo_default in _country_list
    else 0
)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS — image bytes ↔ PIL
# ══════════════════════════════════════════════════════════════════════════════
def pil_to_bytes(img: Image.Image, fmt="PNG") -> bytes:
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def bytes_to_pil(b: bytes) -> Image.Image:
    return Image.open(BytesIO(b))


def image_to_jpeg_bytes(img: Image.Image, quality: int = 95) -> bytes:
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("Region")

    # Geo-detected indicator (shown above the selector)
    if _geo_default:
        st.markdown(
            f"""<div style="background:#F68B1E22;border:1px solid #F68B1E55;
            border-radius:6px;padding:6px 10px;margin-bottom:8px;font-size:0.78rem;
            color:#F68B1E!important;">
            📍 Auto-detected: <strong style="color:#F68B1E">{_geo_default}</strong>
            </div>""",
            unsafe_allow_html=True,
        )

    region_choice = st.selectbox(
        "Select Country:",
        _country_list,
        index=_default_idx,
        key="region_select",
        help="Used for product analysis and all SKU image lookups"
    )
    domain   = DOMAIN_MAP[region_choice]
    base_url = f"https://www.{domain}"

    # Active country status pill
    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#F68B1E,#D4730A);
        border-radius:20px;padding:5px 12px;text-align:center;margin:4px 0 8px;
        font-size:0.8rem;font-weight:700;color:#fff!important;letter-spacing:0.03em;">
        Active: {region_choice}
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.header("Tag Settings")
    tag_type = st.selectbox("Refurbished Grade:", list(TAG_FILES.keys()),
                             key="tag_select")

    # Active grade pill
    st.markdown(
        f"""<div style="background:#2D2D2D;border:1px solid #F68B1E;
        border-radius:20px;padding:5px 12px;text-align:center;margin:4px 0 8px;
        font-size:0.8rem;font-weight:700;color:#F68B1E!important;">
        Grade: {tag_type}
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.header("Analyzer Settings")
    show_browser    = st.checkbox("Show Browser (Debug Mode)", value=False)
    max_workers     = st.slider("Parallel Workers:", 1, 3, 2)
    timeout_seconds = st.slider("Page Timeout (s):", 10, 30, 20)
    check_images    = st.checkbox("Analyze Images for Red Badges", value=True)
    st.info(
        f"{max_workers} workers · {timeout_seconds}s timeout",
        icon=":material/bolt:"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  TAG FILE RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════
def get_tag_path(filename: str) -> str:
    for path in [
        filename,
        os.path.join(os.path.dirname(__file__), filename),
        os.path.join(os.getcwd(), filename),
    ]:
        if os.path.exists(path):
            return path
    return filename


def load_tag_image(grade: str) -> Image.Image | None:
    path = get_tag_path(TAG_FILES[grade])
    if not os.path.exists(path):
        st.error(
            f"Tag file not found: **{TAG_FILES[grade]}** \n"
            "Ensure all tag PNG files are in the same directory as this app.",
            icon=":material/error:"
        )
        return None
    return Image.open(path).convert("RGBA")


# ══════════════════════════════════════════════════════════════════════════════
#  BROWSER DRIVER
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


def get_chrome_options(headless: bool = True):
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    for arg in [
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu", "--disable-extensions",
        "--window-size=1920,1080", "--disable-notifications",
        "--disable-logging", "--log-level=3", "--silent",
    ]:
        opts.add_argument(arg)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    for p in ["/usr/bin/chromium", "/usr/bin/chromium-browser",
               "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]:
        if os.path.exists(p):
            opts.binary_location = p
            break
    return opts


def get_driver(headless: bool = True, timeout: int = 20):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        return None
    opts   = get_chrome_options(headless)
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
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            driver.set_page_load_timeout(timeout)
            driver.implicitly_wait(5)
        except Exception:
            pass
    return driver


# ══════════════════════════════════════════════════════════════════════════════
#  JUMIA SKU → PRIMARY IMAGE  (with multi-country fallback)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_image_from_url_and_soup(driver, b_url: str) -> Image.Image | None:
    """Given a driver already on a product page, extract & return the primary image."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1")))
    except TimeoutException:
        return None
    time.sleep(1)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    og   = soup.find("meta", property="og:image")
    if og and og.get("content"):
        image_url = og["content"]
    else:
        image_url = None
        for img in soup.find_all("img", limit=20):
            src = img.get("data-src") or img.get("src") or ""
            if any(x in src for x in ["/product/", "/unsafe/", "jumia.is"]):
                if src.startswith("//"): src = "https:" + src
                elif src.startswith("/"): src = b_url + src
                image_url = src
                break
    if not image_url:
        return None
    r = requests.get(image_url,
                     headers={"User-Agent": "Mozilla/5.0", "Referer": b_url},
                     timeout=15)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGBA")


def fetch_image_from_sku(
    sku: str,
    primary_b_url: str,
    try_all_countries: bool = True,
) -> tuple[Image.Image | None, str | None]:
    """
    Search Jumia for a SKU.

    Strategy
    --------
    1. Try ``primary_b_url`` (the currently active country) first.
    2. If not found AND ``try_all_countries`` is True, iterate through all other
       Jumia domains in order.
    3. Return ``(image, found_country_key)`` — found_country_key is None if the
       search failed entirely, or the DOMAIN_MAP key for the country where the
       product was actually located.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    def _try_single_country(b_url: str) -> Image.Image | None:
        search_url = f"{b_url}/catalog/?q={sku}"
        driver = get_driver(headless=True)
        if not driver:
            return None
        try:
            driver.get(search_url)
            try:
                WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
            except TimeoutException:
                return None
            if ("There are no results" in driver.page_source or
                    "No results found" in driver.page_source):
                return None
            links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
            if not links:
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='.html']")
            if not links:
                return None
            driver.get(links[0].get_attribute("href"))
            return _fetch_image_from_url_and_soup(driver, b_url)
        except Exception:
            return None
        finally:
            try: driver.quit()
            except: pass

    # 1 — try active country
    img = _try_single_country(primary_b_url)
    if img is not None:
        # Resolve which country key corresponds to this domain
        domain_ = primary_b_url.replace("https://www.", "")
        found_key = _DOMAIN_TO_COUNTRY.get(domain_)
        return img, found_key

    if not try_all_countries:
        return None, None

    # 2 — try remaining countries in order
    primary_domain = primary_b_url.replace("https://www.", "")
    for domain_, country_key in DOMAIN_MAP.items():
        if DOMAIN_MAP[domain_] == primary_domain:
            continue
        alt_b_url = f"https://www.{DOMAIN_MAP[domain_]}"
        img = _try_single_country(alt_b_url)
        if img is not None:
            return img, domain_

    return None, None


# ══════════════════════════════════════════════════════════════════════════════
#  COUNTRY-MISMATCH DIALOG
# ══════════════════════════════════════════════════════════════════════════════
@st.dialog("Country Mismatch Detected")
def show_country_mismatch_dialog(
    active_country: str,
    found_country: str,
    context: str,
):
    """
    Modal popup shown when a URL or SKU belongs to a different Jumia country
    than the one currently active.
    """
    st.markdown(
        f"""
<div style="text-align:center;padding:8px 0 16px;">
  <div style="font-size:2.5rem;margin-bottom:8px;">🌍</div>
  <div style="font-size:1.05rem;font-weight:700;color:#1A1A1A;margin-bottom:6px;">
    Product is from a different country
  </div>
  <div style="font-size:0.9rem;color:#6B6B6B;line-height:1.5;">
    The product you entered belongs to
    <strong style="color:#F68B1E">{found_country}</strong>,
    but your active region is
    <strong style="color:#1A1A1A">{active_country}</strong>.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            f"Switch to {found_country}",
            type="primary",
            use_container_width=True,
            icon=":material/swap_horiz:",
            key=f"mismatch_switch_{context}",
        ):
            # Change the sidebar selectbox index
            st.session_state["region_select"] = found_country
            # Commit any pending image
            _commit_pending_image(context)
            st.session_state["mismatch_detected"] = False
            st.session_state["mismatch_resolved"] = True
            st.rerun()

    with col_b:
        if st.button(
            f"Keep {active_country}",
            use_container_width=True,
            icon=":material/check:",
            key=f"mismatch_keep_{context}",
        ):
            # Commit image as-is (user acknowledged the mismatch)
            _commit_pending_image(context)
            st.session_state["mismatch_detected"] = False
            st.session_state["mismatch_resolved"] = True
            st.rerun()

    st.caption(
        "The image has been loaded — this choice only affects which country "
        "will be used for future searches and analysis."
    )


def _commit_pending_image(context: str):
    """Copy pending image bytes into the right session-state slot."""
    b = st.session_state.get("pending_img_bytes")
    if b is None:
        return
    target = st.session_state.get("pending_img_target", context)
    if target == "single":
        st.session_state["single_img_bytes"]  = b
        st.session_state["single_img_label"]  = st.session_state.get("pending_img_label","")
        st.session_state["single_img_source"] = st.session_state.get("pending_img_source","sku")
        st.session_state["single_scale"]      = 100
    elif target == "cv_single":
        st.session_state["cv_img_bytes"]  = b
        st.session_state["cv_img_label"]  = st.session_state.get("pending_img_label","")
        st.session_state["cv_img_source"] = st.session_state.get("pending_img_source","sku")
    # clear pending
    st.session_state["pending_img_bytes"]  = None
    st.session_state["pending_img_label"]  = ""
    st.session_state["pending_img_source"] = None
    st.session_state["pending_img_target"] = None


def trigger_mismatch_or_commit(
    img: Image.Image,
    label: str,
    source: str,
    found_country: str | None,
    active_country: str,
    target_slot: str,           # "single" | "cv_single"
):
    """
    If found_country differs from active_country, stash the image as 'pending'
    and trigger the mismatch dialog.  Otherwise commit immediately.
    """
    img_bytes = pil_to_bytes(img.convert("RGB") if source != "upload" else img)
    if found_country and found_country != active_country:
        st.session_state["pending_img_bytes"]       = img_bytes
        st.session_state["pending_img_label"]       = label
        st.session_state["pending_img_source"]      = source
        st.session_state["pending_img_target"]      = target_slot
        st.session_state["mismatch_detected"]       = True
        st.session_state["mismatch_url_country"]    = found_country
        st.session_state["mismatch_active_country"] = active_country
        st.session_state["mismatch_context"]        = target_slot
        st.session_state["mismatch_resolved"]       = False
    else:
        # No mismatch — commit directly
        st.session_state["pending_img_bytes"]  = img_bytes
        st.session_state["pending_img_label"]  = label
        st.session_state["pending_img_source"] = source
        st.session_state["pending_img_target"] = target_slot
        _commit_pending_image(target_slot)


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE PROCESSING — TAGGING
# ══════════════════════════════════════════════════════════════════════════════
def auto_crop_whitespace(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    w, h = rgb.size
    non_white = [
        (i % w, i // w)
        for i, (r, g, b) in enumerate(rgb.getdata())
        if not (r > WHITE_THRESHOLD and g > WHITE_THRESHOLD and b > WHITE_THRESHOLD)
    ]
    if not non_white:
        return img
    xs, ys = [p[0] for p in non_white], [p[1] for p in non_white]
    return img.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))


def fit_product_onto_tag(product: Image.Image,
                          tag: Image.Image,
                          scale_pct: int = 100) -> Image.Image:
    """
    Fit product image onto tag canvas.
    scale_pct = 100 → fills the safe zone with MARGIN_PERCENT breathing room (default).
    scale_pct > 100 → larger product; scale_pct < 100 → smaller product.
    """
    cw, ch = tag.size
    safe_w  = cw - int(cw * VERT_STRIP_RATIO)
    safe_h  = ch - int(ch * BANNER_RATIO)
    mx      = int(safe_w * MARGIN_PERCENT)
    my      = int(safe_h * MARGIN_PERCENT)
    inner_w = safe_w - 2 * mx
    inner_h = safe_h - 2 * my

    # Apply user scale on top of the auto-fit scale
    mult    = scale_pct / 100.0
    target_w = int(inner_w * mult)
    target_h = int(inner_h * mult)

    pw, ph = product.size
    scale  = min(target_w / pw, target_h / ph)
    nw, nh = int(pw * scale), int(ph * scale)

    resized = product.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas  = Image.new("RGB", (cw, ch), (255, 255, 255))

    # Centre inside the safe zone
    x = mx + (inner_w - nw) // 2
    y = my + (inner_h - nh) // 2
    x, y = max(0, x), max(0, y)

    if resized.mode == "RGBA":
        canvas.paste(resized, (x, y), resized)
    else:
        canvas.paste(resized, (x, y))

    if tag.mode == "RGBA":
        canvas.paste(tag, (0, 0), tag)
    else:
        canvas.paste(tag, (0, 0))

    return canvas


def apply_tag(product: Image.Image, tag: Image.Image,
              scale_pct: int = 100) -> Image.Image:
    """Full pipeline: crop whitespace → fit onto tag canvas."""
    cropped = auto_crop_whitespace(product.convert("RGBA"))
    return fit_product_onto_tag(cropped, tag, scale_pct)


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE PROCESSING — TAG CONVERSION
# ══════════════════════════════════════════════════════════════════════════════
def detect_tag_boundaries(img: Image.Image):
    rgb = img.convert("RGB")
    w, h = rgb.size

    def is_red(r, g, b):   
        return r > 150 and g < 80 and b < 80
    def is_non_white(r, g, b): 
        # Tighter threshold to prevent anti-aliasing edges from looking "white"
        return not (r > 235 and g > 235 and b > 235)

    # 1. Detect Right Strip (scan right-to-left)
    strip_left = w - int(w * VERT_STRIP_RATIO)
    found_strip_gap = False
    consecutive_white_cols = 0
    streak_start_x = w - 1

    for x in range(w - 1, int(w * 0.65), -1):
        red_count = sum(1 for y in range(h) if is_red(*rgb.getpixel((x, y))))
        if red_count > h * 0.02: # At least 2% red
            consecutive_white_cols = 0
        else:
            if consecutive_white_cols == 0:
                streak_start_x = x
            consecutive_white_cols += 1
            if consecutive_white_cols >= int(w * 0.015):
                # Found a solid white gap. 
                # Set strip_left slightly to the left of the gap's start to ensure complete wipe
                strip_left = streak_start_x - 2
                found_strip_gap = True
                break
                
    if not found_strip_gap:
        strip_left = w - int(w * VERT_STRIP_RATIO)

    # 2. Detect Bottom Banner (scan bottom-to-top)
    banner_top = h - int(h * BANNER_RATIO)
    found_banner_gap = False
    consecutive_white_rows = 0
    streak_start_y = h - 1

    for y in range(h - 1, int(h * 0.60), -1):
        # Count non-white pixels in this row (ignoring the right strip)
        non_white_count = sum(1 for x in range(strip_left) if is_non_white(*rgb.getpixel((x, y))))
        
        # Use max(5, 1% of width) as threshold to tolerate minor JPEG artifacts
        # This prevents the tapered tip of the round yellow badge from being treated as "white"
        threshold = max(5, int(strip_left * 0.01))
        
        if non_white_count <= threshold:
            if consecutive_white_rows == 0:
                streak_start_y = y
            consecutive_white_rows += 1
            
            # We need a solid block of white rows (e.g. 1.5% of image height, ~15px) 
            # to guarantee we have totally cleared the badge and hit the actual empty gap
            if consecutive_white_rows >= int(h * 0.015):
                # Set banner_top slightly above the gap's start (lower Y) to ensure complete wipe
                banner_top = streak_start_y - 2
                found_banner_gap = True
                break
        else:
            consecutive_white_rows = 0
            
    if not found_banner_gap:
        banner_top = h - int(h * BANNER_RATIO)

    return strip_left, banner_top


def strip_and_retag(tagged: Image.Image, new_tag: Image.Image) -> Image.Image:
    rgb = tagged.convert("RGB")
    w, h = rgb.size
    
    # 1. Detect boundaries intelligently without hitting the product
    strip_left, banner_top = detect_tag_boundaries(rgb)
    
    # FIX: Clamp boundaries safely to prevent PIL ValueErrors
    strip_left = max(0, min(strip_left, w))
    banner_top = max(0, min(banner_top, h))
    
    canvas = rgb.copy()
    draw   = ImageDraw.Draw(canvas)
    
    # 2. White out ONLY the old tag areas
    if strip_left < w:
        draw.rectangle([strip_left, 0, w, h], fill=(255, 255, 255))
    if banner_top < h:
        draw.rectangle([0, banner_top, w, h], fill=(255, 255, 255))
    
    # 3. Resize the new tag to fit the canvas exactly before pasting
    resized_tag = new_tag.resize((w, h), Image.Resampling.LANCZOS)
    
    if resized_tag.mode == "RGBA":
        canvas.paste(resized_tag, (0, 0), resized_tag)
    else:
        canvas.paste(resized_tag, (0, 0))
        
    return canvas


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE ANALYSIS HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def get_dhash(img: Image.Image):
    try:
        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        img = img.convert("L").resize((9, 8), resample)
        px  = np.array(img)
        return (px[:, 1:] > px[:, :-1]).flatten()
    except Exception:
        return None


@st.cache_data
def get_target_promo_hash():
    url = ("https://ke.jumia.is/unsafe/fit-in/680x680/filters:fill(white)"
           "/product/21/3620523/3.jpg?0053")
    try:
        r = requests.get(url, timeout=10)
        return get_dhash(Image.open(BytesIO(r.content)))
    except Exception:
        return None


def has_red_badge(image_url: str) -> str:
    try:
        r   = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(r.content)).convert("RGB").resize((300, 300))
        arr = np.array(img).astype(float)
        mask = (arr[:,:,0] > 180) & (arr[:,:,1] < 100) & (arr[:,:,2] < 100)
        return "YES (Red Badge)" if mask.sum() / mask.size > 0.03 else "NO"
    except Exception as e:
        return f"ERROR ({str(e)[:20]})"


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — WARRANTY / REFURB / SELLER / SKU
# ══════════════════════════════════════════════════════════════════════════════
def extract_warranty_info(soup, product_name: str) -> dict:
    data = {"has_warranty":"NO","warranty_duration":"N/A",
            "warranty_source":"None","warranty_details":"","warranty_address":"N/A"}
    patterns = [
        r"(\d+)\s*(?:months?|month|mnths?|mths?)\s*(?:warranty|wrty|wrnty)",
        r"(\d+)\s*(?:year|yr|years|yrs)\s*(?:warranty|wrty|wrnty)",
        r"warranty[:\s]*(\d+)\s*(?:months?|years?)",
    ]

    heading = soup.find(["h3","h4","div","dt"],
                         string=re.compile(r"^\s*Warranty\s*$", re.I))
    if heading:
        val = heading.find_next(["div","dd","p"])
        if val:
            text = val.get_text().strip()
            if text and text.lower() not in ["n/a","na","none",""]:
                found = False
                for p in patterns:
                    m = re.search(p, text, re.I)
                    if m:
                        unit = "months" if "month" in m.group(0).lower() else "years"
                        data.update({"has_warranty":"YES",
                                     "warranty_duration":f"{m.group(1)} {unit}",
                                     "warranty_source":"Warranty Section",
                                     "warranty_details":text[:100]})
                        found = True; break
                if not found:
                    sm = re.search(r"(\d+)\s*(month|year)", text, re.I)
                    if sm:
                        data.update({"has_warranty":"YES","warranty_duration":text.strip(),
                                     "warranty_source":"Warranty Section"})

    if data["has_warranty"] == "NO":
        for p in patterns:
            m = re.search(p, product_name, re.I)
            if m:
                unit = "months" if "month" in m.group(0).lower() else "years"
                data.update({"has_warranty":"YES",
                             "warranty_duration":f"{m.group(1)} {unit}",
                             "warranty_source":"Product Name",
                             "warranty_details":m.group(0)})
                break

    lbl = soup.find(string=re.compile(r"Warranty\s+Address", re.I))
    if lbl:
        el = lbl.find_next(["dd","p","div"])
        if el:
            addr = re.sub(r"<[^>]+>", "", el.get_text()).strip()
            if addr and len(addr) > 10:
                data["warranty_address"] = addr

    if data["has_warranty"] == "NO" and not heading:
        for row in soup.find_all(["tr","div","li"],
                                  class_=re.compile(r"spec|detail|attribute|row")):
            text = row.get_text()
            if "warranty" in text.lower():
                for p in patterns:
                    m = re.search(p, text, re.I)
                    if m:
                        unit = "months" if "month" in m.group(0).lower() else "years"
                        data.update({"has_warranty":"YES",
                                     "warranty_duration":f"{m.group(1)} {unit}",
                                     "warranty_source":"Specifications",
                                     "warranty_details":text.strip()[:100]})
                        break
                if data["has_warranty"] == "YES":
                    break
    return data


def detect_refurbished_status(soup, product_name: str) -> dict:
    data = {"is_refurbished":"NO","refurb_indicators":[],"has_refurb_tag":"NO"}
    kws  = ["refurbished","renewed","refurb","recon","reconditioned",
            "ex-uk","ex uk","pre-owned","certified","restored"]

    scope = soup
    h1    = soup.find("h1")
    if h1:
        c = h1.find_parent("div", class_=re.compile(r"col10|-pvs|-p"))
        scope = c if c else h1.parent.parent

    if scope.find("a", href=re.compile(r"/all-products/\?tag=REFU", re.I)):
        data.update({"is_refurbished":"YES","has_refurb_tag":"YES"})
        data["refurb_indicators"].append("REFU tag badge")

    ri = scope.find("img", attrs={"alt": re.compile(r"^REFU$", re.I)})
    if ri:
        p = ri.parent
        if p and p.name == "a" and "tag=REFU" in p.get("href",""):
            if "REFU tag badge" not in data["refurb_indicators"]:
                data.update({"is_refurbished":"YES","has_refurb_tag":"YES"})
                data["refurb_indicators"].append("REFU badge image")

    for crumb in soup.find_all(["a","span"], class_=re.compile(r"breadcrumb|brcb")):
        if "renewed" in crumb.get_text().lower():
            data["is_refurbished"] = "YES"
            data["refurb_indicators"].append('Breadcrumb: "Renewed"')
            break

    for kw in kws:
        if kw in product_name.lower():
            data["is_refurbished"] = "YES"
            ind = f'Title: "{kw}"'
            if ind not in data["refurb_indicators"]:
                data["refurb_indicators"].append(ind)

    for badge in [
        scope.find(["span","div"], class_=re.compile(r"refurb|renewed", re.I)),
        scope.find(["span","div"], string=re.compile(r"REFURBISHED|RENEWED", re.I)),
        scope.find("img", attrs={"alt": re.compile(r"refurb|renewed", re.I)}),
    ]:
        if badge:
            data["is_refurbished"] = "YES"
            if "Refurbished badge" not in data["refurb_indicators"]:
                data["refurb_indicators"].append("Refurbished badge")
            break

    page_text = (scope if scope != soup else soup).get_text()[:3000]
    for pat in [
        r"condition[:\s]*(renewed|refurbished|excellent|good|like new|grade [a-c])",
        r"(renewed|refurbished)[,\s]*(no scratches|excellent|good condition|like new)",
        r"product condition[:\s]*([^\n]+)",
    ]:
        m = re.search(pat, page_text, re.I)
        if m:
            if data["is_refurbished"] == "NO" and \
               any(k in m.group(0).lower() for k in kws):
                data["is_refurbished"] = "YES"
            if "Condition statement" not in data["refurb_indicators"]:
                data["refurb_indicators"].append("Condition statement")
            break
    return data


def extract_seller_info(soup) -> dict:
    data = {"seller_name":"N/A"}
    sec  = soup.find(["h2","h3","div","p"],
                      string=re.compile(r"Seller\s+Information", re.I))
    if not sec:
        sec = soup.find(["div","section"],
                         class_=re.compile(r"seller-info|seller-box", re.I))
    if sec:
        container = sec.find_parent("div") or sec.parent
        if container:
            el = container.find(["p","div"], class_=re.compile(r"-pbs|-m"))
            if el and len(el.get_text().strip()) > 1:
                data["seller_name"] = el.get_text().strip()
            else:
                for c in container.find_all(["a","p","b"]):
                    text = c.get_text().strip()
                    if not text or any(x in text.lower() for x in
                                       ["follow","score","seller","information","%","rating"]):
                        continue
                    if re.search(r"\d+%", text):
                        continue
                    data["seller_name"] = text
                    break
    return data


def clean_jumia_sku(raw: str) -> str:
    if not raw or raw == "N/A":
        return "N/A"
    m = re.search(r"([A-Z0-9]+NAFAM[A-Z])", raw)
    return m.group(1) if m else raw.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — CATEGORY EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
def extract_category_links(category_url: str,
                            headless: bool = True,
                            timeout: int = 20) -> list[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    driver = get_driver(headless, timeout)
    if not driver:
        return []
    extracted = set()
    try:
        driver.get(category_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a.core")))
        driver.execute_script("window.scrollTo(0,document.body.scrollHeight/2);")
        time.sleep(2)
        for elem in driver.find_elements(By.CSS_SELECTOR, "article.prd a.core"):
            href = elem.get_attribute("href")
            if href and ("/product/" in href or ".html" in href):
                extracted.add(href)
    except TimeoutException:
        st.error(f"Timeout loading category URL.", icon=":material/timer:")
    except Exception as e:
        st.error(f"Error extracting category links: {e}", icon=":material/error:")
    finally:
        try: driver.quit()
        except: pass
    return list(extracted)


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — FULL PRODUCT SCRAPE
# ══════════════════════════════════════════════════════════════════════════════
def extract_product_data(soup, data: dict, is_sku: bool, target: dict,
                          do_check: bool = True) -> dict:
    h1           = soup.find("h1")
    product_name = h1.text.strip() if h1 else "N/A"
    data["Product Name"] = product_name

    # Brand
    bl = soup.find(string=re.compile(r"Brand:\s*", re.I))
    if bl and bl.parent:
        ba = bl.parent.find("a")
        data["Brand"] = ba.text.strip() if ba else \
                        bl.parent.get_text().replace("Brand:","").split("|")[0].strip()
    brand = data.get("Brand","")
    if any(x in brand for x in ["window.fbq","undefined","function("]):
        data["Brand"] = "Renewed"
    if not brand or brand in ["N/A"] or brand.lower() in ["generic","renewed","refurbished"]:
        fw = product_name.split()[0] if product_name != "N/A" else "N/A"
        data["Brand"] = "Renewed" if fw.lower() in ["renewed","refurbished"] else fw
    if data["Brand"].lower() == "refurbished":
        data["Brand"] = "Renewed"

    data["Seller Name"] = extract_seller_info(soup)["seller_name"]

    cats = [b.text.strip() for b in soup.select(
        ".osh-breadcrumb a,.brcbs a,[class*='breadcrumb'] a") if b.text.strip()]
    data["Category"] = " > ".join(cats) if cats else "N/A"

    sku_el = soup.find(attrs={"data-sku": True})
    if sku_el:
        sku_raw = sku_el["data-sku"]
    else:
        tc  = soup.get_text()
        m   = re.search(r"SKU[:\s]*([A-Z0-9]+NAFAM[A-Z])", tc) or \
              re.search(r"SKU[:\s]*([A-Z0-9\-]+)", tc)
        sku_raw = m.group(1) if m else target.get("original_sku","N/A")
    data["SKU"] = clean_jumia_sku(sku_raw)

    # Images
    data["Image URLs"] = []
    image_url = None
    gallery = soup.find("div", id="imgs") or \
               soup.find("div", class_=re.compile(r"\bsldr\b|\bgallery\b|-pas", re.I))
    scope = gallery if gallery else soup
    for img in scope.find_all("img"):
        src = (img.get("data-src") or img.get("src") or "").strip()
        if src and "/product/" in src and not src.startswith("data:"):
            if src.startswith("//"): src = "https:" + src
            elif src.startswith("/"): src = "https://www.jumia.co.ke" + src
            bm = re.search(r"(/product/[a-z0-9_/-]+\.(?:jpg|jpeg|png|webp))", src, re.I)
            bp = bm.group(1) if bm else src
            if not any(bp in eu for eu in data["Image URLs"]):
                data["Image URLs"].append(src)
                if not image_url: image_url = src
        if not gallery and len(data["Image URLs"]) >= 8:
            break
    data["Primary Image URL"]   = image_url or "N/A"
    data["Total Product Images"] = len(data["Image URLs"])

    # Grading last image (dhash)
    data["Grading last image"] = "NO"
    if data["Image URLs"]:
        th = get_target_promo_hash()
        if th is not None:
            try:
                resp = requests.get(data["Image URLs"][-1], timeout=10)
                lh   = get_dhash(Image.open(BytesIO(resp.content)))
                if lh is not None and np.count_nonzero(th != lh) <= 12:
                    data["Grading last image"] = "YES"
            except Exception:
                pass

    rs = detect_refurbished_status(soup, product_name)
    data["Is Refurbished"]        = rs["is_refurbished"]
    data["Has refurb tag"]         = rs["has_refurb_tag"]
    data["Refurbished Indicators"] = ", ".join(rs["refurb_indicators"]) or "None"
    if data["Brand"] == "Renewed":
        data["Is Refurbished"] = "YES"

    wi = extract_warranty_info(soup, product_name)
    data["Has Warranty"]     = wi["has_warranty"]
    data["Warranty Duration"] = wi["warranty_duration"]
    data["Warranty Source"]   = wi["warranty_source"]
    data["Warranty Address"]  = wi["warranty_address"]

    data["grading tag"] = has_red_badge(image_url) \
                          if (do_check and image_url and image_url != "N/A") \
                          else "Not Checked"

    if soup.find(["svg","img","span"],
                  attrs={"aria-label": re.compile(r"Jumia Express", re.I)}):
        data["Express"] = "Yes"

    pt = soup.find("span", class_=re.compile(r"price|prc|-b")) or \
         soup.find(["div","span"], string=re.compile(r"KSh\s*[\d,]+"))
    if pt:
        pm = re.search(r"KSh\s*([\d,]+)", pt.get_text())
        data["Price"] = ("KSh " + pm.group(1)) if pm else pt.get_text().strip()

    re_ = soup.find(["span","div"], class_=re.compile(r"rating|stars"))
    if re_:
        rm = re.search(r"([\d.]+)\s*out of\s*5", re_.get_text())
        if rm: data["Product Rating"] = rm.group(1) + "/5"

    seen = set()
    for cont in soup.find_all("div", class_=re.compile(r"\bmarkup\b|product-desc|-mhm", re.I)):
        for img in cont.find_all("img"):
            src = (img.get("data-src") or img.get("src") or "").strip()
            if src and not src.startswith("data:") and len(src) >= 15 and "1x1" not in src:
                seen.add(src)
    if not seen:
        for img in soup.find_all("img"):
            src = (img.get("data-src") or img.get("src") or "").strip()
            if "/cms/external/" in src and not src.endswith(".svg"):
                seen.add(src)
    data["Infographic Image Count"] = len(seen)
    data["Has info-graphics"]        = "YES" if seen else "NO"
    return data


def scrape_item(target: dict, headless: bool = True,
                timeout: int = 20, do_check: bool = True) -> dict:
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    url    = target["value"]
    is_sku = target["type"] == "sku"
    data   = {
        "Input Source": target.get("original_sku", url),
        "Product Name":"N/A","Brand":"N/A","Seller Name":"N/A","Category":"N/A",
        "SKU":"N/A","Is Refurbished":"NO","Has refurb tag":"NO",
        "Refurbished Indicators":"None","Has Warranty":"NO","Warranty Duration":"N/A",
        "Warranty Source":"None","Warranty Address":"N/A","grading tag":"Not Checked",
        "Primary Image URL":"N/A","Image URLs":[],"Total Product Images":0,
        "Grading last image":"NO","Price":"N/A","Product Rating":"N/A",
        "Express":"No","Has info-graphics":"NO","Infographic Image Count":0,
    }
    driver = None
    try:
        driver = get_driver(headless, timeout)
        if not driver:
            data["Product Name"] = "SYSTEM_ERROR"; return data

        try: driver.get(url)
        except TimeoutException:
            data["Product Name"] = "TIMEOUT"; return data
        except WebDriverException:
            data["Product Name"] = "CONNECTION_ERROR"; return data

        if is_sku:
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
                if "There are no results for" in driver.page_source:
                    data["Product Name"] = "SKU_NOT_FOUND"; return data
                links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                if links:
                    try: driver.get(links[0].get_attribute("href"))
                    except TimeoutException:
                        data["Product Name"] = "TIMEOUT"; return data
            except (TimeoutException, Exception):
                pass

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "h1")))
        except TimeoutException:
            data["Product Name"] = "TIMEOUT"; return data

        for step in [800, 1600, 2400, 3200]:
            try: driver.execute_script(f"window.scrollTo(0,{step});"); time.sleep(0.5)
            except: pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        data = extract_product_data(soup, data, is_sku, target, do_check)

    except TimeoutException:  data["Product Name"] = "TIMEOUT"
    except WebDriverException: data["Product Name"] = "CONNECTION_ERROR"
    except Exception:          data["Product Name"] = "ERROR_FETCHING"
    finally:
        if driver:
            try: driver.quit()
            except: pass
    return data


def scrape_parallel(targets, n_workers, headless=True, timeout=20, do_check=True):
    results, failed = [], []
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        fs = {ex.submit(scrape_item, t, headless, timeout, do_check): t
              for t in targets}
        for f in as_completed(fs):
            t = fs[f]
            try:
                r = f.result()
                if r["Product Name"] in ["SYSTEM_ERROR","TIMEOUT","CONNECTION_ERROR"]:
                    failed.append({"input": t.get("original_sku",t["value"]),
                                   "error": r["Product Name"]})
                elif r["Product Name"] != "SKU_NOT_FOUND":
                    results.append(r)
            except Exception as e:
                failed.append({"input": t.get("original_sku",t["value"]),
                               "error": str(e)})
    return results, failed


def process_inputs(text_in, file_in, d: str) -> list[dict]:
    raw = set()
    if text_in:
        raw.update(i.strip() for i in re.split(r"[\n,]", text_in) if i.strip())
    if file_in:
        try:
            df = pd.read_excel(file_in, header=None) \
                 if file_in.name.endswith(".xlsx") else pd.read_csv(file_in, header=None)
            raw.update(str(c).strip() for c in df.values.flatten()
                        if str(c).strip() and str(c).lower() != "nan")
        except Exception as e:
            st.error(f"File read error: {e}", icon=":material/error:")
    targets = []
    for item in raw:
        v = item.replace("SKU:", "").strip()
        if "http" in v or "www." in v:
            if not v.startswith("http"): v = "https://" + v
            targets.append({"type":"url","value":v})
        elif len(v) > 3:
            targets.append({"type":"sku",
                            "value":f"https://www.{d}/catalog/?q={v}",
                            "original_sku":v})
    return targets


# ── Fire mismatch dialog if one is pending ────────────────────────────────────
if st.session_state.get("mismatch_detected"):
    show_country_mismatch_dialog(
        active_country=st.session_state["mismatch_active_country"],
        found_country=st.session_state["mismatch_url_country"],
        context=st.session_state["mismatch_context"],
    )

# ══════════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_analyze, tab_single, tab_bulk, tab_convert = st.tabs([
    "Analyze Products",
    "Tag — Single Image",
    "Tag — Bulk",
    "Convert Tag",
])


# ┌─────────────────────────────────────────────────────────────────────────────
# │  TAB 1 — ANALYZE PRODUCTS
# └─────────────────────────────────────────────────────────────────────────────
with tab_analyze:
    st.subheader(f"Analyze Products  ·  {region_choice}")

    col_txt, col_upl = st.columns(2)
    with col_txt:
        text_in = st.text_area(
            "Paste SKUs or URLs:",
            height=100,
            placeholder="One SKU or URL per line\nExample: SA948MP5EER52NAFAMZ",
            key="a_text"
        )
    with col_upl:
        file_in = st.file_uploader(
            "Upload Excel / CSV with SKUs:",
            type=["xlsx","csv"], key="a_file"
        )

    cat_url_in = st.text_input(
        "Category URL (extracts all products on the page):",
        placeholder=f"https://www.{domain}/smartphones/",
        key="a_cat"
    )
    st.markdown("---")

    if st.button("Start Analysis", type="primary",
                  icon=":material/play_arrow:", key="a_run"):
        targets = process_inputs(text_in, file_in, domain)

        if cat_url_in:
            with st.spinner("Extracting product links from category page…"):
                links = extract_category_links(
                    cat_url_in, not show_browser, timeout_seconds)
                for lnk in links:
                    targets.append({"type":"url","value":lnk,"original_sku":lnk})
                if links:
                    st.success(f"Extracted {len(links)} products from category URL.",
                               icon=":material/check_circle:")
                else:
                    st.warning("No product links found on that category URL.",
                               icon=":material/warning:")

        if not targets:
            st.warning("No valid input. Please enter SKUs, URLs, or a Category URL.",
                       icon=":material/warning:")
        else:
            st.session_state["scraped_results"] = []
            st.session_state["failed_items"]    = []

            prog    = st.progress(0)
            status  = st.empty()
            details = st.empty()
            preview = st.empty()
            status.text(f"Analyzing {len(targets)} products…")
            t0          = time.time()
            batch_size  = max_workers * 2
            all_results = []
            all_failed  = []
            processed   = 0

            for i in range(0, len(targets), batch_size):
                batch = targets[i:i+batch_size]
                bn    = i // batch_size + 1
                bt    = (len(targets) + batch_size - 1) // batch_size
                details.info(f"Batch {bn}/{bt}  ({len(batch)} items)",
                             icon=":material/inventory_2:")

                br, bf = scrape_parallel(
                    batch, max_workers, not show_browser, timeout_seconds, check_images)
                all_results.extend(br)
                all_failed.extend(bf)
                processed += len(batch)
                prog.progress(min(processed / len(targets), 1.0))

                elapsed = time.time() - t0
                rem     = (len(targets) - processed) * (elapsed / processed) if processed else 0
                status.text(
                    f"Processed {processed}/{len(targets)}  "
                    f"({processed/elapsed:.1f}/s)  |  Est. remaining: {rem:.0f}s"
                )
                if br:
                    li = br[-1]
                    with preview.container():
                        c1, c2 = st.columns([1,3])
                        with c1:
                            if li.get("Primary Image URL","N/A") != "N/A":
                                try: st.image(li["Primary Image URL"], width=150)
                                except: pass
                        with c2:
                            st.caption(f"Last: {li.get('Product Name','N/A')[:70]}")
                            st.caption(
                                f"Images: {li.get('Total Product Images',0)}  |  "
                                f"Refurb: {li.get('Is Refurbished','NO')}  |  "
                                f"Grade img: {li.get('Grading last image','NO')}"
                            )

            elapsed = time.time() - t0
            st.session_state["scraped_results"] = all_results
            st.session_state["failed_items"]    = all_failed
            details.empty(); preview.empty()

            if all_failed:
                status.warning(
                    f"Completed with issues: {len(all_results)} ok, "
                    f"{len(all_failed)} failed ({elapsed:.1f}s)",
                    icon=":material/warning:")
            else:
                status.success(
                    f"Done — {len(targets)} products in {elapsed:.1f}s "
                    f"({len(targets)/elapsed:.1f}/s)",
                    icon=":material/check_circle:")
            time.sleep(2)
            st.rerun()

    # Results
    if st.session_state["failed_items"]:
        with st.expander(
                f"Failed Items ({len(st.session_state['failed_items'])})",
                expanded=False):
            st.dataframe(pd.DataFrame(st.session_state["failed_items"]),
                         use_container_width=True)

    if st.session_state["scraped_results"]:
        df = pd.DataFrame(st.session_state["scraped_results"])
        priority_cols = [
            "SKU","Product Name","Brand","Is Refurbished","Has refurb tag",
            "Has Warranty","Warranty Duration","Total Product Images",
            "Grading last image","grading tag","Has info-graphics",
            "Infographic Image Count","Seller Name","Price","Product Rating",
            "Express","Category","Refurbished Indicators",
            "Warranty Source","Warranty Address","Primary Image URL","Input Source",
        ]
        df = df[[c for c in priority_cols if c in df.columns]]

        st.subheader("Summary")
        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("Total Analyzed",  len(df))
        m2.metric("Refurbished",     int((df["Is Refurbished"]=="YES").sum()))
        m3.metric("Grading Image",   int((df.get("Grading last image","NO")=="YES").sum()))
        m4.metric("Red Badges",
                  int(df.get("grading tag","").str.contains("YES", na=False).sum()))
        m5.metric("Avg Images",
                  f"{df.get('Total Product Images', pd.Series([0])).mean():.1f}")

        st.markdown("---")
        st.subheader("Product Gallery")
        gcol, fcol = st.columns([3,1])
        with fcol:
            view_mode        = st.radio("View:", ["Grid","List"],
                                        horizontal=True, key="a_view")
            show_refurb_only = st.checkbox("Refurbished only", key="a_refurb_filter")
        display_df = df[df["Is Refurbished"]=="YES"] if show_refurb_only else df

        if view_mode == "Grid":
            for row in range((len(display_df)+3)//4):
                cols_ = st.columns(4)
                for ci in range(4):
                    idx = row*4+ci
                    if idx >= len(display_df): break
                    item = display_df.iloc[idx]
                    with cols_[ci]:
                        pu = item.get("Primary Image URL","N/A")
                        try:
                            st.image(pu if pu != "N/A" else
                                     "https://via.placeholder.com/200x200?text=No+Image",
                                     use_container_width=True)
                        except:
                            st.image("https://via.placeholder.com/200x200?text=No+Image",
                                     use_container_width=True)
                        st.caption(f"**{item.get('Brand','N/A')}**")
                        pn = item.get("Product Name","N/A")
                        st.caption(pn[:50]+"…" if len(pn)>50 else pn)
                        badges = []
                        if item.get("Is Refurbished")=="YES": badges.append("Refurb")
                        if item.get("Grading last image")=="YES": badges.append("Grade Img")
                        n_img = item.get("Total Product Images",0)
                        if n_img: badges.append(f"{n_img} imgs")
                        if badges: st.caption(" · ".join(f"[{b}]" for b in badges))
                        st.caption(item.get("Price","N/A"))
                        with st.expander("Details"):
                            st.caption(f"SKU: {item.get('SKU','N/A')}")
                            st.caption(f"Seller: {item.get('Seller Name','N/A')}")
        else:
            for _, item in display_df.iterrows():
                with st.container():
                    c1, c2 = st.columns([1,4])
                    with c1:
                        pu = item.get("Primary Image URL","N/A")
                        try:
                            st.image(pu if pu!="N/A" else
                                     "https://via.placeholder.com/150x150?text=No+Image",
                                     width=150)
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

        if (df["Is Refurbished"]=="YES").any():
            st.markdown("---")
            st.subheader("Refurbished Items Detail")
            st.dataframe(df[df["Is Refurbished"]=="YES"], use_container_width=True)

        st.markdown("---")
        st.subheader("Full Results")

        def _highlight(row):
            return ["background-color:#fffacd"]*len(row) \
                   if row.get("Brand")=="Renewed" else [""]*len(row)
        try:
            st.dataframe(df.style.apply(_highlight, axis=1), use_container_width=True)
        except:
            st.dataframe(df, use_container_width=True)

        st.download_button(
            "Download CSV",
            df.to_csv(index=False).encode("utf-8"),
            f"analysis_{int(time.time())}.csv",
            "text/csv",
            icon=":material/download:",
            key="a_dl"
        )


# ┌─────────────────────────────────────────────────────────────────────────────
# │  TAB 2 — TAG: SINGLE IMAGE
# └─────────────────────────────────────────────────────────────────────────────
with tab_single:
    st.subheader(f"Tag — Single Image  ·  Grade: {tag_type}  ·  {region_choice}")

    col_in, col_out = st.columns([1, 1])

    # ── Input column ──────────────────────────────────────────────────────────
    with col_in:
        st.markdown("#### Image Source")

        src_method = st.radio(
            "Source:",
            ["Upload from device", "Load from Image URL", "Load from SKU"],
            horizontal=True, key="s_src"
        )

        # Clear stored image when user switches source method
        if st.session_state.get("s_src_prev") != src_method:
            st.session_state["single_img_bytes"]  = None
            st.session_state["single_img_label"]  = ""
            st.session_state["single_img_source"] = None
            st.session_state["single_scale"]      = 100
            st.session_state["s_src_prev"] = src_method

        # --- Upload ---
        if src_method == "Upload from device":
            f = st.file_uploader(
                "Choose an image file:",
                type=["png","jpg","jpeg","webp"],
                key="s_upload"
            )
            if f is not None:
                fhash = hashlib.md5(f.getvalue()).hexdigest()
                if st.session_state.get("single_img_label") != fhash:
                    # New file uploaded — reset scale and store bytes
                    img = Image.open(f).convert("RGBA")
                    st.session_state["single_img_bytes"]  = pil_to_bytes(img)
                    st.session_state["single_img_label"]  = fhash
                    st.session_state["single_img_source"] = "upload"
                    st.session_state["single_scale"]      = 100

        # --- URL ---
        elif src_method == "Load from Image URL":
            img_url = st.text_input("Image URL:", key="s_url")
            if st.button("Load Image", icon=":material/download:",
                          key="s_url_load"):
                if img_url:
                    with st.spinner("Fetching image…"):
                        try:
                            # Check if this URL belongs to a Jumia country
                            url_country = detect_country_from_url(img_url)
                            r = requests.get(img_url, timeout=15)
                            r.raise_for_status()
                            img = Image.open(BytesIO(r.content)).convert("RGBA")
                            trigger_mismatch_or_commit(
                                img=img, label=img_url, source="url",
                                found_country=url_country,
                                active_country=region_choice,
                                target_slot="single",
                            )
                            if not st.session_state.get("mismatch_detected"):
                                st.success("Image loaded successfully.",
                                           icon=":material/check_circle:")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not load image: {e}",
                                     icon=":material/error:")
                else:
                    st.warning("Please enter a URL.", icon=":material/warning:")

        # --- SKU ---
        else:
            sku_val = st.text_input(
                "Product SKU:",
                placeholder="e.g. GE840EA6C62GANAFAMZ",
                key="s_sku"
            )
            st.caption(f"Searches **{base_url}** first, then all other Jumia countries.")

            if st.button("Search & Extract Image",
                          icon=":material/search:", key="s_sku_search",
                          type="primary"):
                if sku_val.strip():
                    prog_holder = st.empty()
                    prog_holder.info(
                        f"Searching **{region_choice}** for SKU `{sku_val.strip()}`…",
                        icon=":material/search:"
                    )
                    img, found_country = fetch_image_from_sku(
                        sku_val.strip(), base_url, try_all_countries=True)
                    prog_holder.empty()
                    if img is not None:
                        trigger_mismatch_or_commit(
                            img=img, label=sku_val.strip(), source="sku",
                            found_country=found_country,
                            active_country=region_choice,
                            target_slot="single",
                        )
                        if not st.session_state.get("mismatch_detected"):
                            st.success(
                                f"Image loaded for SKU **{sku_val.strip()}**"
                                + (f" (found in {found_country})" if found_country and found_country != region_choice else ""),
                                icon=":material/check_circle:")
                        st.rerun()
                    else:
                        st.error(
                            f"SKU **{sku_val.strip()}** not found on any Jumia country.",
                            icon=":material/search_off:"
                        )
                else:
                    st.warning("Please enter a SKU.", icon=":material/warning:")

        # Show loaded state
        if st.session_state["single_img_bytes"] is not None:
            src  = st.session_state["single_img_source"]
            lbl  = st.session_state["single_img_label"]
            icon = (":material/upload:" if src == "upload" else
                    ":material/link:"   if src == "url"    else
                    ":material/qr_code:")
            st.info(f"Image loaded  —  {lbl}", icon=icon)

        # ── Size control (inline, same column) ──────────────────────────────
        if st.session_state["single_img_bytes"] is not None:
            st.markdown("---")
            st.markdown("#### Image Size")
            st.caption(
                "100% = auto-fit (fills the tag frame with balanced margins). "
                "Increase to fill more of the frame; decrease for more padding."
            )
            new_scale = st.slider(
                "Product size (% of frame):",
                min_value=40, max_value=180,
                value=st.session_state["single_scale"],
                step=5, key="s_scale_slider"
            )
            st.session_state["single_scale"] = new_scale

            sc1, sc2, sc3 = st.columns(3)
            if sc1.button("Smaller", icon=":material/remove:", key="s_smaller"):
                st.session_state["single_scale"] = max(
                    40, st.session_state["single_scale"] - 5)
                st.rerun()
            if sc2.button("Reset (100%)", icon=":material/refresh:", key="s_reset"):
                st.session_state["single_scale"] = 100
                st.rerun()
            if sc3.button("Larger", icon=":material/add:", key="s_larger"):
                st.session_state["single_scale"] = min(
                    180, st.session_state["single_scale"] + 5)
                st.rerun()

    # ── Preview / download column ─────────────────────────────────────────────
    with col_out:
        st.markdown("#### Preview")

        if st.session_state["single_img_bytes"] is not None:
            tag_img = load_tag_image(tag_type)
            if tag_img is not None:
                product_img = bytes_to_pil(
                    st.session_state["single_img_bytes"]).convert("RGBA")
                scale_val   = st.session_state["single_scale"]
                result      = apply_tag(product_img, tag_img, scale_val)

                st.image(result, use_container_width=True,
                         caption=f"Grade: {tag_type}  ·  Size: {scale_val}%")
                st.markdown("---")
                st.download_button(
                    label="Download Tagged Image (JPEG)",
                    data=image_to_jpeg_bytes(result),
                    file_name=f"tagged_{tag_type.lower().replace(' ','_')}.jpg",
                    mime="image/jpeg",
                    use_container_width=True,
                    icon=":material/download:",
                    key="s_dl"
                )
        else:
            st.info(
                "Load an image using one of the source options on the left.",
                icon=":material/image:"
            )


# ┌─────────────────────────────────────────────────────────────────────────────
# │  TAB 3 — TAG: BULK
# └─────────────────────────────────────────────────────────────────────────────
with tab_bulk:
    st.subheader(f"Tag — Bulk Processing  ·  Grade: {tag_type}  ·  {region_choice}")
    st.caption(
        "Images are auto-cropped and fitted automatically. "
        "Per-image size controls are available before processing."
    )

    bulk_method = st.radio(
        "Input method:",
        ["Upload multiple images",
         "Enter URLs manually",
         "Upload Excel file with URLs",
         "Enter SKUs"],
        key="b_method"
    )

    # products_to_process: list of {"bytes": bytes, "name": str}
    products_to_process: list[dict] = []

    # ── Upload ────────────────────────────────────────────────────────────────
    if bulk_method == "Upload multiple images":
        files = st.file_uploader(
            "Choose image files:",
            type=["png","jpg","jpeg","webp"],
            accept_multiple_files=True,
            key="b_upload"
        )
        if files:
            st.info(f"{len(files)} files uploaded", icon=":material/photo_library:")
            for f in files:
                try:
                    img = Image.open(f).convert("RGBA")
                    products_to_process.append({
                        "bytes": pil_to_bytes(img),
                        "name":  f.name.rsplit(".",1)[0],
                    })
                except Exception as e:
                    st.warning(f"Could not load {f.name}: {e}",
                               icon=":material/warning:")

    # ── URLs ──────────────────────────────────────────────────────────────────
    elif bulk_method == "Enter URLs manually":
        raw_urls = st.text_area(
            "Image URLs (one per line):",
            height=160,
            placeholder="https://example.com/image1.jpg",
            key="b_urls"
        )
        if raw_urls.strip():
            url_list = [u.strip() for u in raw_urls.splitlines() if u.strip()]
            with st.spinner(f"Loading {len(url_list)} images…"):
                for i, u in enumerate(url_list):
                    try:
                        r = requests.get(u, timeout=12); r.raise_for_status()
                        img = Image.open(BytesIO(r.content)).convert("RGBA")
                        products_to_process.append({
                            "bytes": pil_to_bytes(img),
                            "name":  f"image_{i+1}",
                        })
                    except Exception as e:
                        st.warning(f"URL {i+1} failed: {e}", icon=":material/warning:")

    # ── Excel ─────────────────────────────────────────────────────────────────
    elif bulk_method == "Upload Excel file with URLs":
        st.caption("**Column A:** Image URLs  ·  **Column B (optional):** Product name")
        xf = st.file_uploader(
            "Excel file (.xlsx / .xls):",
            type=["xlsx","xls"], key="b_excel"
        )
        if xf:
            try:
                df_xl = pd.read_excel(xf)
                urls  = df_xl.iloc[:,0].dropna().astype(str).tolist()
                names = (df_xl.iloc[:,1].dropna().astype(str).tolist()
                         if len(df_xl.columns) > 1
                         else [f"product_{i+1}" for i in range(len(urls))])
                st.info(f"Found {len(urls)} URLs in file.",
                        icon=":material/table:")
                with st.spinner(f"Loading {len(urls)} images…"):
                    for i,(u,n) in enumerate(zip(urls,names)):
                        try:
                            r = requests.get(u, timeout=12); r.raise_for_status()
                            img   = Image.open(BytesIO(r.content)).convert("RGBA")
                            clean = re.sub(r"[^\w\s-]","",n).strip().replace(" ","_")
                            products_to_process.append({
                                "bytes": pil_to_bytes(img),
                                "name":  clean or f"product_{i+1}",
                            })
                        except Exception as e:
                            st.warning(f"Could not load {n}: {e}",
                                       icon=":material/warning:")
            except Exception as e:
                st.error(f"Excel read error: {e}", icon=":material/error:")

    # ── SKUs ──────────────────────────────────────────────────────────────────
    else:
        skus_raw = st.text_area(
            "SKUs (one per line):",
            height=160,
            placeholder="GE840EA6C62GANAFAMZ",
            key="b_skus"
        )
        st.caption(f"Will search on **{base_url}**")

        if skus_raw.strip():
            skus = [s.strip() for s in skus_raw.splitlines() if s.strip()]
            st.info(f"{len(skus)} SKUs entered", icon=":material/list:")

            if st.button("Search All SKUs",
                          icon=":material/search:", key="b_sku_search",
                          type="primary"):
                prog   = st.progress(0)
                status = st.empty()
                new_results: list[dict] = []
                mismatches: list[dict]  = []

                for i, sku in enumerate(skus):
                    status.text(f"Fetching {i+1}/{len(skus)}: {sku}")
                    img, found_country = fetch_image_from_sku(
                        sku, base_url, try_all_countries=True)
                    if img:
                        new_results.append({
                            "bytes": pil_to_bytes(img),
                            "name":  sku,
                        })
                        if found_country and found_country != region_choice:
                            mismatches.append({
                                "sku": sku,
                                "found_in": found_country,
                            })
                    else:
                        st.warning(f"No image for SKU: {sku}",
                                   icon=":material/image_not_supported:")
                    prog.progress((i+1)/len(skus))

                st.session_state["bulk_sku_results"] = new_results

                if mismatches:
                    mismatch_lines = "  \n".join(
                        f"• **{m['sku']}** — found in {m['found_in']}"
                        for m in mismatches
                    )
                    st.warning(
                        f"**{len(mismatches)} SKU(s) found on a different Jumia country "
                        f"than {region_choice}:** \n{mismatch_lines}  \n\n"
                        "Images were loaded successfully. You may want to change "
                        "your active region in the sidebar.",
                        icon=":material/public:"
                    )

                status.success(
                    f"Found {len(new_results)} / {len(skus)} images.",
                    icon=":material/check_circle:")

        # Use persisted SKU results
        products_to_process = st.session_state.get("bulk_sku_results", [])
        if products_to_process:
            st.info(
                f"{len(products_to_process)} SKU images ready. "
                "Click **Search All SKUs** again to refresh.",
                icon=":material/check_circle:"
            )

    # ── Review grid with per-image size controls ──────────────────────────────
    if products_to_process:
        st.markdown("---")
        st.subheader(f"{len(products_to_process)} images ready")
        st.caption(
            "Adjust individual sizes below if needed. "
            "100% = auto-fit default."
        )

        cols_per_row = 4
        for row_s in range(0, len(products_to_process), cols_per_row):
            chunk = products_to_process[row_s:row_s+cols_per_row]
            cols_ = st.columns(cols_per_row)
            for ci, item in enumerate(chunk):
                idx = row_s + ci
                k   = f"bsc_{idx}_{item['name']}"
                if k not in st.session_state["individual_scales"]:
                    st.session_state["individual_scales"][k] = 100
                with cols_[ci]:
                    try:
                        preview_img = bytes_to_pil(item["bytes"]).convert("RGB")
                        st.image(preview_img, caption=item["name"],
                                 use_container_width=True)
                    except Exception:
                        st.caption(f"[{item['name']}]")
                    sc = st.slider(
                        "Size %",
                        min_value=40, max_value=180,
                        value=st.session_state["individual_scales"][k],
                        step=5, key=f"bsl_{k}",
                        label_visibility="collapsed"
                    )
                    st.session_state["individual_scales"][k] = sc
                    st.caption(f"{sc}%")

        st.markdown("---")
        
        if st.button("Process All Images", icon=":material/tune:", key="b_process", type="primary"):
            tag_img = load_tag_image(tag_type)
            if tag_img is not None:
                prog      = st.progress(0)
                processed = []

                for i, item in enumerate(products_to_process):
                    try:
                        k  = f"bsc_{i}_{item['name']}"
                        sc = st.session_state["individual_scales"].get(k, 100)
                        result = apply_tag(
                            bytes_to_pil(item["bytes"]).convert("RGBA"),
                            tag_img, sc
                        )
                        processed.append({"img": result, "name": item["name"]})
                    except Exception as e:
                        st.warning(f"Error on {item['name']}: {e}",
                                   icon=":material/warning:")
                    prog.progress((i+1)/len(products_to_process))

                if processed:
                    st.success(f"{len(processed)} images processed.", icon=":material/check_circle:")
                    zb = BytesIO()
                    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as zf:
                        for p in processed:
                            zf.writestr(f"{p['name']}_1.jpg", image_to_jpeg_bytes(p["img"]))
                    zb.seek(0)
                    
                    # Store variables in session state instead of rendering immediate button
                    st.session_state["b_bulk_zip"] = zb.getvalue()
                    st.session_state["b_bulk_preview"] = processed[:8]
                    st.session_state["b_bulk_total"] = len(processed)
                else:
                    st.error("No images were successfully processed.", icon=":material/error:")

        # --- Show download button completely outside the action logic ---
        if "b_bulk_zip" in st.session_state:
            st.download_button(
                f"Download All {st.session_state['b_bulk_total']} Images (ZIP)",
                st.session_state["b_bulk_zip"],
                f"tagged_{tag_type.lower().replace(' ','_')}.zip",
                "application/zip",
                use_container_width=True,
                icon=":material/download:",
                key="b_dl"
            )
            st.markdown("### Preview")
            pcols = st.columns(4)
            for i, p in enumerate(st.session_state["b_bulk_preview"]):
                with pcols[i%4]:
                    st.image(p["img"], caption=p["name"], use_container_width=True)
            if st.session_state["b_bulk_total"] > 8:
                st.caption(f"Showing 8 of {st.session_state['b_bulk_total']}")

    else:
        st.info("Provide images using one of the input methods above.",
                icon=":material/image:")


# ┌─────────────────────────────────────────────────────────────────────────────
# │  TAB 4 — CONVERT TAG
# └─────────────────────────────────────────────────────────────────────────────
with tab_convert:
    st.subheader(f"Convert Tag  →  {tag_type}  ·  {region_choice}")
    st.caption(
        "Load an already-tagged image from any source. "
        "The old tag is detected automatically via pixel scanning and "
        "replaced with the grade selected in the sidebar."
    )

    conv_qty = st.radio(
        "Processing mode:",
        ["Single image", "Multiple images"],
        horizontal=True, key="cv_qty"
    )

    # ════════════════════════════════════════════════════════════════════════
    #  SINGLE IMAGE
    # ════════════════════════════════════════════════════════════════════════
    if conv_qty == "Single image":
        col_src, col_out = st.columns([1, 1])

        with col_src:
            st.markdown("#### Image Source")
            cv_method = st.radio(
                "Source:",
                ["Upload from device",
                 "Load from Image URL",
                 "Load from Product URL",
                 "Load from SKU"],
                horizontal=False, key="cv_src_method"
            )

            # Clear stored image when source method switches
            if st.session_state.get("cv_src_prev") != cv_method:
                st.session_state["cv_img_bytes"]  = None
                st.session_state["cv_img_label"]  = ""
                st.session_state["cv_img_source"] = None
                st.session_state["cv_src_prev"]   = cv_method

            # ── Upload ────────────────────────────────────────────────────
            if cv_method == "Upload from device":
                cf = st.file_uploader(
                    "Choose a tagged image:",
                    type=["png","jpg","jpeg","webp"],
                    key="cv_s_upload"
                )
                if cf is not None:
                    fhash = hashlib.md5(cf.getvalue()).hexdigest()
                    if st.session_state["cv_img_label"] != fhash:
                        img = Image.open(cf).convert("RGB")
                        st.session_state["cv_img_bytes"]  = pil_to_bytes(img)
                        st.session_state["cv_img_label"]  = fhash
                        st.session_state["cv_img_source"] = "upload"

            # ── Image URL ─────────────────────────────────────────────────
            elif cv_method == "Load from Image URL":
                img_url_cv = st.text_input(
                    "Direct image URL:",
                    placeholder="https://example.com/product.jpg",
                    key="cv_s_img_url"
                )
                if st.button("Load Image", icon=":material/download:", key="cv_s_img_load"):
                    if img_url_cv.strip():
                        with st.spinner("Fetching image…"):
                            try:
                                url_country = detect_country_from_url(img_url_cv.strip())
                                r = requests.get(img_url_cv.strip(), timeout=15)
                                r.raise_for_status()
                                img = Image.open(BytesIO(r.content)).convert("RGB")
                                trigger_mismatch_or_commit(
                                    img=img, label=img_url_cv.strip(), source="url",
                                    found_country=url_country,
                                    active_country=region_choice,
                                    target_slot="cv_single",
                                )
                                if not st.session_state.get("mismatch_detected"):
                                    st.success("Image loaded.", icon=":material/check_circle:")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not load image: {e}", icon=":material/error:")
                    else:
                        st.warning("Please enter a URL.", icon=":material/warning:")

            # ── Product page URL ──────────────────────────────────────────
            elif cv_method == "Load from Product URL":
                prod_url_cv = st.text_input(
                    "Jumia product page URL:",
                    placeholder=f"https://www.{domain}/some-product.html",
                    key="cv_s_prod_url"
                )
                if st.button("Extract Image from Page",
                              icon=":material/travel_explore:", key="cv_s_prod_load"):
                    if prod_url_cv.strip():
                        # Detect country from URL before even fetching
                        url_country = detect_country_from_url(prod_url_cv.strip())
                        with st.spinner("Opening product page and extracting image…"):
                            try:
                                from selenium.webdriver.common.by import By as _By
                                from selenium.webdriver.support.ui import WebDriverWait as _WDW
                                from selenium.webdriver.support import expected_conditions as _EC
                                drv = get_driver(headless=True)
                                if drv is None:
                                    st.error("Browser driver unavailable.", icon=":material/error:")
                                else:
                                    try:
                                        drv.get(prod_url_cv.strip())
                                        _WDW(drv, 12).until(
                                            _EC.presence_of_element_located((_By.TAG_NAME,"h1")))
                                        time.sleep(1)
                                        soup_ = BeautifulSoup(drv.page_source, "html.parser")
                                        og_ = soup_.find("meta", property="og:image")
                                        img_url_ = og_["content"] if (og_ and og_.get("content")) else None
                                        if not img_url_:
                                            for im_ in soup_.find_all("img", limit=20):
                                                s_ = im_.get("data-src") or im_.get("src") or ""
                                                if any(x in s_ for x in ["/product/","/unsafe/","jumia.is"]):
                                                    if s_.startswith("//"): s_ = "https:" + s_
                                                    elif s_.startswith("/"): s_ = base_url + s_
                                                    img_url_ = s_
                                                    break
                                        if img_url_:
                                            r_ = requests.get(img_url_,
                                                headers={"User-Agent":"Mozilla/5.0","Referer":base_url},
                                                timeout=15)
                                            r_.raise_for_status()
                                            img = Image.open(BytesIO(r_.content)).convert("RGB")
                                            trigger_mismatch_or_commit(
                                                img=img, label=prod_url_cv.strip(),
                                                source="product_url",
                                                found_country=url_country,
                                                active_country=region_choice,
                                                target_slot="cv_single",
                                            )
                                            if not st.session_state.get("mismatch_detected"):
                                                st.success("Image extracted from product page.",
                                                           icon=":material/check_circle:")
                                            st.rerun()
                                        else:
                                            st.warning("Could not find an image on that page.",
                                                       icon=":material/image_not_supported:")
                                    finally:
                                        try: drv.quit()
                                        except: pass
                            except Exception as e:
                                st.error(f"Error: {e}", icon=":material/error:")
                    else:
                        st.warning("Please enter a product URL.", icon=":material/warning:")

            # ── SKU ───────────────────────────────────────────────────────
            else:
                sku_cv = st.text_input(
                    "Product SKU:",
                    placeholder="e.g. GE840EA6C62GANAFAMZ",
                    key="cv_s_sku"
                )
                st.caption(f"Searches **{base_url}** first, then all other Jumia countries.")
                if st.button("Search & Extract Image",
                              icon=":material/search:", key="cv_s_sku_search",
                              type="primary"):
                    if sku_cv.strip():
                        prog_cv = st.empty()
                        prog_cv.info(
                            f"Searching **{region_choice}** for SKU `{sku_cv.strip()}`…",
                            icon=":material/search:"
                        )
                        img, found_country = fetch_image_from_sku(
                            sku_cv.strip(), base_url, try_all_countries=True)
                        prog_cv.empty()
                        if img is not None:
                            trigger_mismatch_or_commit(
                                img=img, label=sku_cv.strip(), source="sku",
                                found_country=found_country,
                                active_country=region_choice,
                                target_slot="cv_single",
                            )
                            if not st.session_state.get("mismatch_detected"):
                                st.success(
                                    f"Image loaded for SKU **{sku_cv.strip()}**"
                                    + (f" (found in {found_country})" if found_country and found_country != region_choice else ""),
                                    icon=":material/check_circle:")
                            st.rerun()
                        else:
                            st.error(
                                f"SKU **{sku_cv.strip()}** not found on any Jumia country.",
                                icon=":material/search_off:"
                            )
                    else:
                        st.warning("Please enter a SKU.", icon=":material/warning:")

            # Loaded indicator
            if st.session_state["cv_img_bytes"] is not None:
                src_icons = {
                    "upload":      ":material/upload:",
                    "url":         ":material/link:",
                    "product_url": ":material/travel_explore:",
                    "sku":         ":material/qr_code:",
                }
                st.info(f"Loaded: {st.session_state['cv_img_label']}",
                        icon=src_icons.get(st.session_state["cv_img_source"],":material/image:"))

        # ── Result column ─────────────────────────────────────────────────
        with col_out:
            st.markdown("#### Result")
            if st.session_state["cv_img_bytes"] is not None:
                tag_img = load_tag_image(tag_type)
                if tag_img is not None:
                    tagged_cv = bytes_to_pil(st.session_state["cv_img_bytes"]).convert("RGB")
                    result_cv = strip_and_retag(tagged_cv, tag_img)
                    fname_cv  = re.sub(r"[^\w\s-]","",
                                       st.session_state["cv_img_label"]).strip()[:40] or "converted"
                    bc, ac = st.columns(2)
                    bc.image(tagged_cv, caption="Before (old tag)", use_container_width=True)
                    ac.image(result_cv, caption=f"After → {tag_type}", use_container_width=True)
                    st.markdown("---")
                    st.download_button(
                        f"Download as {tag_type} (JPEG)",
                        image_to_jpeg_bytes(result_cv),
                        f"{fname_cv}_{tag_type.lower().replace(' ','_')}.jpg",
                        "image/jpeg",
                        use_container_width=True,
                        icon=":material/download:",
                        key="cv_s_dl"
                    )
            else:
                st.info("Load an image using one of the source options on the left.",
                        icon=":material/swap_horiz:")

    # ════════════════════════════════════════════════════════════════════════
    #  MULTIPLE IMAGES
    # ════════════════════════════════════════════════════════════════════════
    else:
        st.markdown("#### Image Sources")
        cv_bulk_method = st.radio(
            "Input method:",
            ["Upload multiple images", "Enter Image URLs", "Enter SKUs"],
            horizontal=True, key="cv_bulk_method"
        )
        cv_images: list[dict] = []

        if cv_bulk_method == "Upload multiple images":
            conv_files = st.file_uploader(
                "Choose tagged images:",
                type=["png","jpg","jpeg","webp"],
                accept_multiple_files=True, key="cv_b_upload"
            )
            if conv_files:
                st.info(f"{len(conv_files)} files uploaded", icon=":material/photo_library:")
                for f in conv_files:
                    try:
                        img = Image.open(f).convert("RGB")
                        cv_images.append({"bytes": pil_to_bytes(img), "name": f.name.rsplit(".",1)[0]})
                    except Exception as e:
                        st.warning(f"Could not load {f.name}: {e}", icon=":material/warning:")

        elif cv_bulk_method == "Enter Image URLs":
            raw_cv_urls = st.text_area(
                "Image URLs (one per line):", height=150,
                placeholder="https://example.com/tagged1.jpg", key="cv_b_urls"
            )
            if raw_cv_urls.strip():
                url_list_cv = [u.strip() for u in raw_cv_urls.splitlines() if u.strip()]
                with st.spinner(f"Loading {len(url_list_cv)} images…"):
                    for i, u in enumerate(url_list_cv):
                        try:
                            r = requests.get(u, timeout=12); r.raise_for_status()
                            img = Image.open(BytesIO(r.content)).convert("RGB")
                            cv_images.append({"bytes": pil_to_bytes(img), "name": f"image_{i+1}"})
                        except Exception as e:
                            st.warning(f"URL {i+1} failed: {e}", icon=":material/warning:")

        else:  # SKUs
            cv_skus_raw = st.text_area(
                "SKUs (one per line):", height=150,
                placeholder="GE840EA6C62GANAFAMZ", key="cv_b_skus"
            )
            st.caption(f"Will search on **{base_url}**")
            if cv_skus_raw.strip():
                skus_ = [s.strip() for s in cv_skus_raw.splitlines() if s.strip()]
                st.info(f"{len(skus_)} SKUs entered", icon=":material/list:")
                if st.button("Search All SKUs", icon=":material/search:",
                              key="cv_b_sku_search", type="primary"):
                    prog_   = st.progress(0)
                    status_ = st.empty()
                    new_cv: list[dict] = []
                    cv_mismatches: list[dict] = []
                    for i, sku_ in enumerate(skus_):
                        status_.text(f"Fetching {i+1}/{len(skus_)}: {sku_}")
                        img_, found_ = fetch_image_from_sku(
                            sku_, base_url, try_all_countries=True)
                        if img_:
                            new_cv.append({"bytes": pil_to_bytes(img_.convert("RGB")), "name": sku_})
                            if found_ and found_ != region_choice:
                                cv_mismatches.append({"sku": sku_, "found_in": found_})
                        else:
                            st.warning(f"No image for SKU: {sku_}", icon=":material/image_not_supported:")
                        prog_.progress((i+1)/len(skus_))
                    st.session_state["cv_bulk_sku_results"] = new_cv

                    if cv_mismatches:
                        mm_lines = "  \n".join(
                            f"• **{m['sku']}** — found in {m['found_in']}"
                            for m in cv_mismatches
                        )
                        st.warning(
                            f"**{len(cv_mismatches)} SKU(s) found on a different Jumia "
                            f"country than {region_choice}:** \n{mm_lines}  \n\n"
                            "Images were loaded. You may want to update your region in the sidebar.",
                            icon=":material/public:"
                        )

                    status_.success(f"Found {len(new_cv)}/{len(skus_)} images.", icon=":material/check_circle:")
            cv_images = st.session_state.get("cv_bulk_sku_results", [])
            if cv_images:
                st.info(f"{len(cv_images)} SKU images ready.", icon=":material/check_circle:")

        if cv_images:
            st.markdown("---")
            st.subheader(f"{len(cv_images)} tagged images ready to convert")
            st.markdown("**Originals (with old tags):**")
            for rs in range(0, len(cv_images), 4):
                cols_ = st.columns(4)
                for ci, item in enumerate(cv_images[rs:rs+4]):
                    with cols_[ci]:
                        try:
                            st.image(bytes_to_pil(item["bytes"]).convert("RGB"),
                                     caption=item["name"], use_container_width=True)
                        except Exception:
                            st.caption(f"[{item['name']}]")
            st.markdown("---")
            
            if st.button(f"Convert All to {tag_type}", icon=":material/swap_horiz:",
                          use_container_width=True, key="cv_b_process", type="primary"):
                tag_img = load_tag_image(tag_type)
                if tag_img is not None:
                    prog_   = st.progress(0)
                    converted = []
                    for i, item in enumerate(cv_images):
                        try:
                            tagged_ = bytes_to_pil(item["bytes"]).convert("RGB")
                            converted.append({"img": strip_and_retag(tagged_, tag_img), "name": item["name"]})
                        except Exception as e:
                            st.warning(f"Error on {item['name']}: {e}", icon=":material/warning:")
                        prog_.progress((i+1)/len(cv_images))
                    if converted:
                        st.success(f"{len(converted)} images converted to {tag_type}.", icon=":material/check_circle:")
                        zb = BytesIO()
                        with zipfile.ZipFile(zb,"w",zipfile.ZIP_DEFLATED) as zf:
                            for c in converted:
                                zf.writestr(f"{c['name']}_{tag_type.lower().replace(' ','_')}.jpg",
                                            image_to_jpeg_bytes(c["img"]))
                        zb.seek(0)
                        
                        # Set to Session State
                        st.session_state["cv_bulk_zip"] = zb.getvalue()
                        st.session_state["cv_bulk_preview"] = converted[:8]
                        st.session_state["cv_bulk_total"] = len(converted)
                    else:
                        st.error("No images were successfully converted.", icon=":material/error:")
            
            # --- Show download button outside action logic ---
            if "cv_bulk_zip" in st.session_state:
                st.download_button(
                    f"Download All {st.session_state['cv_bulk_total']} Converted Images (ZIP)",
                    data=st.session_state["cv_bulk_zip"],
                    file_name=f"converted_{tag_type.lower().replace(' ','_')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    icon=":material/download:", 
                    key="cv_b_dl"
                )
                st.markdown("### Preview")
                pcols = st.columns(4)
                for i, c in enumerate(st.session_state["cv_bulk_preview"]):
                    with pcols[i%4]:
                        st.image(c["img"], caption=c["name"], use_container_width=True)
                if st.session_state["cv_bulk_total"] > 8:
                    st.caption(f"Showing 8 of {st.session_state['cv_bulk_total']}")
        else:
            st.info("Provide images using one of the input methods above.", icon=":material/image:")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="
    margin-top: 40px;
    padding: 18px 24px;
    background: linear-gradient(135deg, #1A1A1A 0%, #2D2D2D 100%);
    border-radius: 10px;
    border-top: 3px solid #F68B1E;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
">
  <span style="color:#F68B1E; font-weight:800; font-size:0.95rem; font-family:'Nunito',sans-serif;">
    Jumia Refurbished Suite
  </span>
  <span style="color:#999; font-size:0.78rem; font-family:'Nunito',sans-serif;">
    Auto-crop &nbsp;·&nbsp; Margin-aware fit &nbsp;·&nbsp; Pixel-scan tag removal
  </span>
</div>
""", unsafe_allow_html=True)
