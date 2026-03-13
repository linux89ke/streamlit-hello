import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Jumia Product Analyzer",
    page_icon=":material/label:",
    layout="wide"
)

# ══════════════════════════════════════════════════════════════════════════════
#  JUMIA BRAND THEME
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

@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Nunito', sans-serif;
    color: #1A1A1A;
}

.stApp { background-color: #FAFAFA; }

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1A1A1A 0%, #2D2D2D 100%);
    border-right: 3px solid #F68B1E;
}
[data-testid="stSidebar"] * { color: #F5F5F5 !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stCheckbox label,
[data-testid="stSidebar"] .stRadio label {
    color: #CCCCCC !important;
    font-size: 0.85rem;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #F68B1E !important;
    font-weight: 800;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #F68B1E44;
    padding-bottom: 4px;
    margin-bottom: 8px;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div:first-child {
    background-color: #3A3A3A !important;
    border-color: #F68B1E !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stSelectboxValue"],
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div {
    color: #FFFFFF !important;
}
[data-baseweb="popover"] [data-baseweb="menu"] { background-color: #2D2D2D !important; }
[data-baseweb="popover"] [role="option"] { background-color: #2D2D2D !important; color: #F5F5F5 !important; }
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"] { background-color: #F68B1E !important; color: #FFFFFF !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #AAAAAA !important; font-size: 0.8rem; }
[data-testid="stSidebar"] .stAlert { background-color: #F68B1E22 !important; border-left: 4px solid #F68B1E !important; color: #F68B1E !important; }

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
.jumia-header h1 { margin: 0; color: #FFFFFF; font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }
.jumia-header p { margin: 4px 0 0; color: #FFE0B2; font-size: 0.9rem; }
.jumia-logo-dot { width: 48px; height: 48px; background: #FFFFFF; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.6rem; flex-shrink: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.2); }

/* ── Primary buttons ──────────────────────────────────────────────────────── */
[data-testid="stButton"] button[kind="primary"], [data-testid="stBaseButton-primary"] { background: linear-gradient(135deg, #F68B1E 0%, #D4730A 100%) !important; color: #FFFFFF !important; border: none !important; border-radius: 8px !important; font-weight: 700 !important; font-size: 0.9rem !important; padding: 10px 20px !important; box-shadow: 0 3px 10px #F68B1E55 !important; transition: all 0.2s ease !important; }
[data-testid="stButton"] button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover { box-shadow: 0 5px 18px #F68B1E88 !important; transform: translateY(-1px); }
[data-testid="stButton"] button:not([kind="primary"]), [data-testid="stBaseButton-secondary"] { background: #FFFFFF !important; color: #F68B1E !important; border: 1.5px solid #F68B1E !important; border-radius: 8px !important; font-weight: 600 !important; transition: all 0.2s ease !important; }
[data-testid="stButton"] button:not([kind="primary"]):hover { background: #FFF4E6 !important; }
[data-testid="stDownloadButton"] button { background: linear-gradient(135deg, #F68B1E 0%, #D4730A 100%) !important; color: #FFFFFF !important; border: none !important; border-radius: 8px !important; font-weight: 700 !important; box-shadow: 0 3px 10px #F68B1E44 !important; }

/* ── UI Elements ──────────────────────────────────────────────────────────── */
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #F0E0CC; border-left: 4px solid #F68B1E; border-radius: 10px; padding: 14px 16px !important; box-shadow: 0 2px 8px rgba(246,139,30,0.1); }
[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #F68B1E; font-weight: 800; font-size: 1.6rem; }
[data-testid="stMetric"] [data-testid="stMetricLabel"] { color: #6B6B6B; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
[data-testid="stExpander"] { border: 1px solid #F0E0CC !important; border-radius: 10px !important; overflow: hidden; }
[data-testid="stExpander"] summary { background: #FFF4E6 !important; color: #1A1A1A !important; font-weight: 600; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea { border: 1.5px solid #E0E0E0 !important; border-radius: 8px !important; font-family: 'Nunito', sans-serif !important; transition: border-color 0.2s; }
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus { border-color: #F68B1E !important; box-shadow: 0 0 0 3px #F68B1E22 !important; }
[data-testid="stAlert"][data-baseweb="notification"] { border-radius: 8px; }
.stSuccess { border-left: 4px solid #F68B1E !important; }
.stInfo    { border-left: 4px solid #F68B1E !important; }
[data-testid="stDataFrame"] th { background-color: #F68B1E !important; color: #FFFFFF !important; font-weight: 700 !important; }
[data-testid="stFileUploader"] { border: 2px dashed #F68B1E !important; border-radius: 10px !important; background: #FFF4E688 !important; }
[data-testid="stFileUploaderDropzone"] { background: transparent !important; }
[data-baseweb="select"]:focus-within { border-color: #F68B1E !important; box-shadow: 0 0 0 3px #F68B1E22 !important; }
hr { border-color: #F0E0CC !important; }
[data-testid="stCaptionContainer"] { color: #6B6B6B; font-size: 0.8rem; }
h2, h3 { color: #1A1A1A; font-weight: 700; }
h2::after { content: ''; display: block; width: 48px; height: 3px; background: #F68B1E; border-radius: 2px; margin-top: 4px; }
[data-testid="stProgress"] div[role="progressbar"] > div { background: linear-gradient(90deg, #F68B1E, #D4730A) !important; }
[data-testid="stSpinner"] svg { color: #F68B1E !important; }
</style>

<div class="jumia-header">
  <div class="jumia-logo-dot">🏷</div>
  <div>
    <h1>Jumia Product Analyzer</h1>
    <p>Analyze listings &nbsp;·&nbsp; Extract product specs &nbsp;·&nbsp; Detect Official Store & Promo Badges</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
DOMAIN_MAP = {
    "Kenya (KE)":   "jumia.co.ke",
    "Uganda (UG)":  "jumia.ug",
    "Nigeria (NG)": "jumia.com.ng",
    "Morocco (MA)": "jumia.ma",
    "Ghana (GH)":   "jumia.com.gh",
}

# ── Reverse map: domain string → country key ──────────────────────────────────
_DOMAIN_TO_COUNTRY: dict[str, str] = {v: k for k, v in DOMAIN_MAP.items()}

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE INITIALISATION
# ══════════════════════════════════════════════════════════════════════════════
_defaults = {
    "scraped_results": [],
    "failed_items":    [],
    "geo_country": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
#  GEO-DETECTION
# ══════════════════════════════════════════════════════════════════════════════
_COUNTRY_CODE_MAP = { "KE": "Kenya (KE)", "UG": "Uganda (UG)", "NG": "Nigeria (NG)", "MA": "Morocco (MA)", "GH": "Ghana (GH)" }

def _detect_country() -> str | None:
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
_default_idx  = _country_list.index(_geo_default) if _geo_default and _geo_default in _country_list else 0

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("Region")
    if _geo_default:
        st.markdown(
            f"""<div style="background:#F68B1E22;border:1px solid #F68B1E55; border-radius:6px;padding:6px 10px;margin-bottom:8px;font-size:0.78rem; color:#F68B1E!important;">
            📍 Auto-detected: <strong style="color:#F68B1E">{_geo_default}</strong>
            </div>""", unsafe_allow_html=True)

    region_choice = st.selectbox("Select Country:", _country_list, index=_default_idx, key="region_select", help="Used for product analysis and all SKU lookups")
    domain   = DOMAIN_MAP[region_choice]
    base_url = f"https://www.{domain}"

    st.markdown(
        f"""<div style="background:linear-gradient(135deg,#F68B1E,#D4730A); border-radius:20px;padding:5px 12px;text-align:center;margin:4px 0 8px; font-size:0.8rem;font-weight:700;color:#fff!important;letter-spacing:0.03em;">
        Active: {region_choice}</div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.header("Analyzer Settings")
    show_browser    = st.checkbox("Show Browser (Debug Mode)", value=False)
    max_workers     = st.slider("Parallel Workers:", 1, 3, 2)
    timeout_seconds = st.slider("Page Timeout (s):", 10, 30, 20)
    st.info(f"{max_workers} workers · {timeout_seconds}s timeout", icon=":material/bolt:")

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
        "--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled",
        "--disable-gpu", "--disable-extensions", "--window-size=1920,1080", "--disable-notifications",
        "--disable-logging", "--log-level=3", "--silent",
    ]:
        opts.add_argument(arg)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    for p in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]:
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
    opts = get_chrome_options(headless)
    driver = None
    try:
        dp = get_driver_path()
        if dp:
            svc = Service(dp)
            svc.log_path = os.devnull
            driver = webdriver.Chrome(service=svc, options=opts)
    except Exception:
        try: driver = webdriver.Chrome(options=opts)
        except Exception: return None
    if driver:
        try:
            driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            driver.set_page_load_timeout(timeout)
            driver.implicitly_wait(5)
        except Exception: pass
    return driver

# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — WARRANTY / SELLER / SKU / BADGES
# ══════════════════════════════════════════════════════════════════════════════
def extract_warranty_info(soup, product_name: str) -> dict:
    data = {"has_warranty":"NO","warranty_duration":"N/A", "warranty_source":"None","warranty_details":"","warranty_address":"N/A"}
    patterns = [ r"(\d+)\s*(?:months?|month|mnths?|mths?)\s*(?:warranty|wrty|wrnty)", r"(\d+)\s*(?:year|yr|years|yrs)\s*(?:warranty|wrty|wrnty)", r"warranty[:\s]*(\d+)\s*(?:months?|years?)"]
    heading = soup.find(["h3","h4","div","dt"], string=re.compile(r"^\s*Warranty\s*$", re.I))
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
                        data.update({"has_warranty":"YES", "warranty_duration":f"{m.group(1)} {unit}", "warranty_source":"Warranty Section", "warranty_details":text[:100]})
                        found = True; break
                if not found:
                    sm = re.search(r"(\d+)\s*(month|year)", text, re.I)
                    if sm: data.update({"has_warranty":"YES","warranty_duration":text.strip(), "warranty_source":"Warranty Section"})
    if data["has_warranty"] == "NO":
        for p in patterns:
            m = re.search(p, product_name, re.I)
            if m:
                unit = "months" if "month" in m.group(0).lower() else "years"
                data.update({"has_warranty":"YES", "warranty_duration":f"{m.group(1)} {unit}", "warranty_source":"Product Name", "warranty_details":m.group(0)})
                break
    lbl = soup.find(string=re.compile(r"Warranty\s+Address", re.I))
    if lbl:
        el = lbl.find_next(["dd","p","div"])
        if el:
            addr = re.sub(r"<[^>]+>", "", el.get_text()).strip()
            if addr and len(addr) > 10: data["warranty_address"] = addr
    if data["has_warranty"] == "NO" and not heading:
        for row in soup.find_all(["tr","div","li"], class_=re.compile(r"spec|detail|attribute|row")):
            text = row.get_text()
            if "warranty" in text.lower():
                for p in patterns:
                    m = re.search(p, text, re.I)
                    if m:
                        unit = "months" if "month" in m.group(0).lower() else "years"
                        data.update({"has_warranty":"YES", "warranty_duration":f"{m.group(1)} {unit}", "warranty_source":"Specifications", "warranty_details":text.strip()[:100]})
                        break
                if data["has_warranty"] == "YES": break
    return data

def extract_seller_info(soup) -> dict:
    data = {"seller_name":"N/A"}
    sec  = soup.find(["h2","h3","div","p"], string=re.compile(r"Seller\s+Information", re.I))
    if not sec: sec = soup.find(["div","section"], class_=re.compile(r"seller-info|seller-box", re.I))
    if sec:
        container = sec.find_parent("div") or sec.parent
        if container:
            el = container.find(["p","div"], class_=re.compile(r"-pbs|-m"))
            if el and len(el.get_text().strip()) > 1:
                data["seller_name"] = el.get_text().strip()
            else:
                for c in container.find_all(["a","p","b"]):
                    text = c.get_text().strip()
                    if not text or any(x in text.lower() for x in ["follow","score","seller","information","%","rating","verified"]): continue
                    if re.search(r"\d+%", text): continue
                    data["seller_name"] = text
                    break
    return data

def clean_jumia_sku(raw: str) -> str:
    if not raw or raw == "N/A": return "N/A"
    raw = raw.upper()
    m = re.search(r"([A-Z0-9]+NAFAM[A-Z])", raw)
    return m.group(1) if m else raw.strip()

# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — CATEGORY EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
def extract_category_links(category_url: str, headless: bool = True, timeout: int = 20, max_pages: int = 1) -> list[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    import re

    driver = get_driver(headless, timeout)
    if not driver: return []
    extracted = set()
    
    base_url = re.sub(r'([?&])page=\d+', r'\1', category_url).replace('&&', '&').replace('?&', '?').rstrip('?&')
    sep = "&" if "?" in base_url else "?"

    try:
        for page in range(1, max_pages + 1):
            current_url = f"{base_url}{sep}page={page}" if page > 1 else base_url
            driver.get(current_url)
            
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd a.core")))
            except TimeoutException:
                break 
                
            driver.execute_script("window.scrollTo(0,document.body.scrollHeight/2);")
            time.sleep(2) 
            
            elements = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
            if not elements:
                break 
                
            for elem in elements:
                href = elem.get_attribute("href")
                if href and ("/product/" in href or ".html" in href): 
                    extracted.add(href)
                    
    except Exception as e: 
        st.error(f"Error extracting category links: {e}", icon=":material/error:")
    finally:
        try: driver.quit()
        except: pass
        
    return list(extracted)

# ══════════════════════════════════════════════════════════════════════════════
#  ANALYZER — FULL PRODUCT SCRAPE
# ══════════════════════════════════════════════════════════════════════════════
def extract_product_data(soup, data: dict, is_sku: bool, target: dict, country_code: str = "KE") -> dict:
    h1           = soup.find("h1")
    product_name = h1.text.strip() if h1 else "N/A"
    data["Product Name"] = product_name

    bl = soup.find(string=re.compile(r"Brand:\s*", re.I))
    if bl and bl.parent:
        ba = bl.parent.find("a")
        data["Brand"] = ba.text.strip() if ba else bl.parent.get_text().replace("Brand:","").split("|")[0].strip()
    brand = data.get("Brand","")
    if any(x in brand for x in ["window.fbq","undefined","function("]): data["Brand"] = "Renewed"
    if not brand or brand in ["N/A"] or brand.lower() in ["generic","renewed","refurbished"]:
        fw = product_name.split()[0] if product_name != "N/A" else "N/A"
        data["Brand"] = "Renewed" if fw.lower() in ["renewed","refurbished"] else fw
    
    data["Seller Name"] = extract_seller_info(soup)["seller_name"]

    cats = [b.text.strip() for b in soup.select(".osh-breadcrumb a,.brcbs a,[class*='breadcrumb'] a") if b.text.strip()]
    data["Category"] = " > ".join(cats) if cats else "N/A"

    sku_el = soup.find(attrs={"data-sku": True})
    if sku_el:
        sku_raw = sku_el["data-sku"]
    else:
        tc  = soup.get_text()
        m   = re.search(r"SKU[:\s]*([A-Z0-9]+NAFAM[A-Z])", tc) or re.search(r"SKU[:\s]*([A-Z0-9\-]+)", tc)
        sku_raw = m.group(1) if m else target.get("original_sku","N/A")
    data["SKU"] = clean_jumia_sku(sku_raw)

    data["Primary Image URL"] = "N/A"
    data["Total Product Images"] = 0
    data["Image URLs"] = []

    # Get primary image and total counts for output
    gallery = soup.find("div", id="imgs") or soup.find("div", class_=re.compile(r"\bsldr\b|\bgallery\b|-pas", re.I))
    scope = gallery if gallery else soup
    image_url = None
    for img in scope.find_all("img"):
        src = (img.get("data-src") or img.get("src") or "").strip()
        if src and "/product/" in src and not src.startswith("data:"):
            if src.startswith("//"): src = "https:" + src
            elif src.startswith("/"): src = "https://www.jumia.co.ke" + src
            if not any(src in eu for eu in data["Image URLs"]):
                data["Image URLs"].append(src)
                if not image_url: image_url = src
    data["Primary Image URL"] = image_url or "N/A"
    data["Total Product Images"] = len(data["Image URLs"])

    # ── Official Store & Tech week deal Detection ──
    data["Official Store"] = "NO"
    data["Tech week deal"] = "NO"

    # Iterate tags near top where badges usually reside
    for el in soup.find_all(["span", "div", "a", "img"]):
        text = el.get_text(strip=True).lower() if el.name != "img" else (el.get("alt") or "").lower()
        if "official store" in text and len(text) < 25:
            data["Official Store"] = "YES"
        if "tech week deal" in text and len(text) < 25:
            data["Tech week deal"] = "YES"

    wi = extract_warranty_info(soup, product_name)
    data["Has Warranty"]      = wi["has_warranty"]
    data["Warranty Duration"] = wi["warranty_duration"]
    data["Warranty Source"]   = wi["warranty_source"]
    data["Warranty Address"]  = wi["warranty_address"]

    if soup.find(["svg","img","span"], attrs={"aria-label": re.compile(r"Jumia Express", re.I)}): data["Express"] = "Yes"

    pt = soup.find("span", class_=re.compile(r"price|prc|-b")) or soup.find(["div","span"], string=re.compile(r"KSh\s*[\d,]+"))
    if pt:
        pm = re.search(r"KSh\s*([\d,]+)", pt.get_text())
        data["Price"] = ("KSh " + pm.group(1)) if pm else pt.get_text().strip()

    re_ = soup.find(["span","div"], class_=re.compile(r"rating|stars"))
    if re_:
        rm = re.search(r"([\d.]+)\s*out of\s*5", re_.get_text())
        if rm: data["Product Rating"] = rm.group(1) + "/5"

    return data


def scrape_item(target: dict, headless: bool = True, timeout: int = 20, country_code: str = "KE") -> dict:
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    url    = target["value"]
    is_sku = target["type"] == "sku"
    data   = {
        "Input Source": target.get("original_sku", url),
        "Product Name":"N/A","Brand":"N/A","Seller Name":"N/A","Category":"N/A",
        "SKU":"N/A", "Official Store":"NO", "Tech week deal":"NO",
        "Has Warranty":"NO","Warranty Duration":"N/A",
        "Warranty Source":"None","Warranty Address":"N/A",
        "Price":"N/A","Product Rating":"N/A",
        "Express":"No",
        "Primary Image URL": "N/A", "Total Product Images": 0, "Image URLs": []
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
                WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd, h1")))
                if "There are no results for" in driver.page_source:
                    data["Product Name"] = "SKU_NOT_FOUND"; return data
                links = driver.find_elements(By.CSS_SELECTOR, "article.prd a.core")
                if links:
                    try: driver.get(links[0].get_attribute("href"))
                    except TimeoutException:
                        data["Product Name"] = "TIMEOUT"; return data
            except (TimeoutException, Exception):
                pass

        try: WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        except TimeoutException: data["Product Name"] = "TIMEOUT"; return data

        for step in [800, 1600, 2400, 3200]:
            try: driver.execute_script(f"window.scrollTo(0,{step});"); time.sleep(0.5)
            except: pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        data = extract_product_data(soup, data, is_sku, target, country_code)

    except TimeoutException:  data["Product Name"] = "TIMEOUT"
    except WebDriverException: data["Product Name"] = "CONNECTION_ERROR"
    except Exception:          data["Product Name"] = "ERROR_FETCHING"
    finally:
        if driver:
            try: driver.quit()
            except: pass
    return data

def scrape_parallel(targets, n_workers, headless=True, timeout=20, country_code="KE"):
    results, failed = [], []
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        fs = {ex.submit(scrape_item, t, headless, timeout, country_code): t for t in targets}
        for f in as_completed(fs):
            t = fs[f]
            try:
                r = f.result()
                if r["Product Name"] in ["SYSTEM_ERROR","TIMEOUT","CONNECTION_ERROR"]:
                    failed.append({"input": t.get("original_sku",t["value"]), "error": r["Product Name"]})
                elif r["Product Name"] != "SKU_NOT_FOUND":
                    results.append(r)
            except Exception as e:
                failed.append({"input": t.get("original_sku",t["value"]), "error": str(e)})
    return results, failed

def process_inputs(text_in, file_in, d: str) -> list[dict]:
    raw = set()
    if text_in: raw.update(i.strip() for i in re.split(r"[\n,]", text_in) if i.strip())
    if file_in:
        try:
            df = pd.read_excel(file_in, header=None) if file_in.name.endswith(".xlsx") else pd.read_csv(file_in, header=None)
            raw.update(str(c).strip() for c in df.values.flatten() if str(c).strip() and str(c).lower() != "nan")
        except Exception as e:
            st.error(f"File read error: {e}", icon=":material/error:")
    targets = []
    for item in raw:
        v = item.replace("SKU:", "").strip()
        # Strict URL check
        if v.startswith("http") or v.startswith("www."):
            if not v.startswith("http"): v = "https://" + v
            targets.append({"type":"url","value":v})
        elif len(v) > 3:
            targets.append({"type":"sku", "value":f"https://www.{d}/catalog/?q={v}", "original_sku":v})
    return targets

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN UI: ANALYZE PRODUCTS
# ══════════════════════════════════════════════════════════════════════════════
st.subheader(f"Analyze Products  ·  {region_choice}")

analyze_method = st.radio(
    "Input method:",
    ["Paste SKUs / URLs", "Upload Excel / CSV", "Category URL"],
    horizontal=True, key="a_method"
)

text_in = None
file_in = None
cat_url_in = None
max_cat_pages = 1

if analyze_method == "Paste SKUs / URLs":
    text_in = st.text_area("Paste SKUs or URLs:", height=100, placeholder="One SKU or URL per line\nExample: SA948MP5EER52NAFAMZ", key="a_text")
elif analyze_method == "Upload Excel / CSV":
    file_in = st.file_uploader("Upload Excel / CSV with SKUs:", type=["xlsx","csv"], key="a_file")
else:
    cat_url_in = st.text_input("Category URL (extracts all products on the page):", placeholder=f"https://www.{domain}/smartphones/", key="a_cat")
    max_cat_pages = st.number_input("Max category pages to scrape (40 products per page):", min_value=1, max_value=50, value=1, step=1)

st.markdown("---")

if st.button("Start Analysis", type="primary", icon=":material/play_arrow:", key="a_run"):
    targets = process_inputs(text_in, file_in, domain)

    if cat_url_in:
        with st.spinner(f"Extracting product links from up to {max_cat_pages} page(s)…"):
            links = extract_category_links(cat_url_in, not show_browser, timeout_seconds, max_cat_pages)
            for lnk in links: targets.append({"type":"url","value":lnk,"original_sku":lnk})
            if links: st.success(f"Extracted {len(links)} products from category URL.", icon=":material/check_circle:")
            else: st.warning("No product links found on that category URL.", icon=":material/warning:")

    if not targets:
        st.warning("No valid input. Please enter SKUs, URLs, or a Category URL.", icon=":material/warning:")
    else:
        st.session_state["scraped_results"] = []
        st.session_state["failed_items"]    = []

        prog    = st.progress(0)
        t0      = time.time()
        batch_size  = max_workers * 2
        all_results = []
        all_failed  = []
        processed   = 0
        
        current_cc = region_choice.split("(")[-1].strip(")")

        with st.status(f"Analyzing {len(targets)} products...", expanded=True) as run_status:
            info_text = st.empty()
            c1, c2 = st.columns([1,4])
            txt_placeholder = c2.empty()

            for i in range(0, len(targets), batch_size):
                batch = targets[i:i+batch_size]
                bn    = i // batch_size + 1
                bt    = (len(targets) + batch_size - 1) // batch_size
                
                br, bf = scrape_parallel(batch, max_workers, not show_browser, timeout_seconds, current_cc)
                
                all_results.extend(br)
                all_failed.extend(bf)
                processed += len(batch)
                prog.progress(min(processed / len(targets), 1.0))

                elapsed = time.time() - t0
                rem     = (len(targets) - processed) * (elapsed / processed) if processed else 0
                
                run_status.update(label=f"Analyzing {len(targets)} products... (Processed {processed}/{len(targets)})")
                info_text.markdown(f"**Speed:** {processed/elapsed:.1f} items/sec &nbsp;|&nbsp; **Est. remaining:** {rem:.0f}s &nbsp;|&nbsp; **Batch:** {bn}/{bt}")
                
                if br:
                    li = br[-1]
                    txt_placeholder.caption(
                        f"**Last Processed:** {li.get('Product Name','N/A')[:70]}  \n"
                        f"**Official Store:** {li.get('Official Store','NO')} | "
                        f"**Tech week deal:** {li.get('Tech week deal','NO')}"
                    )

            if all_failed:
                run_status.update(label=f"Completed with issues: {len(all_results)} ok, {len(all_failed)} failed ({elapsed:.1f}s)", state="error")
            else:
                run_status.update(label=f"Done — {len(targets)} products in {elapsed:.1f}s", state="complete")
                
        st.session_state["scraped_results"] = all_results
        st.session_state["failed_items"]    = all_failed
        time.sleep(1)
        st.rerun()

# Results Section
if st.session_state["failed_items"]:
    with st.expander(f"Failed Items ({len(st.session_state['failed_items'])})", expanded=False):
        st.dataframe(pd.DataFrame(st.session_state["failed_items"]), use_container_width=True)

if st.session_state["scraped_results"]:
    df = pd.DataFrame(st.session_state["scraped_results"])
    
    available_cols = list(df.columns)
    priority_cols = [
        "SKU", "Product Name", "Brand", "Official Store", "Tech week deal", 
        "Has Warranty", "Warranty Duration", "Seller Name", "Price", 
        "Product Rating", "Express", "Category", 
        "Warranty Source", "Warranty Address", "Primary Image URL", "Total Product Images", "Input Source"
    ]
    df = df[[c for c in priority_cols if c in available_cols]]

    st.subheader("Summary")
    st.metric("Total Analyzed", len(df))

    st.markdown("---")

    st.subheader("Full Results")
    st.caption("Use the dropdown to show/hide columns. Select specific rows using the checkboxes on the left to download only those.")

    all_cols = list(df.columns)
    default_visible_cols = [
        "SKU", "Product Name", "Brand", "Official Store", "Tech week deal", 
        "Has Warranty", "Warranty Duration", "Seller Name", "Price"
    ]
    default_visible_cols = [c for c in default_visible_cols if c in all_cols]
    
    selected_cols = st.multiselect("Visible Columns:", options=all_cols, default=default_visible_cols)
    display_full_df = df[selected_cols] if selected_cols else df

    def _highlight(row):
        is_renewed = "Brand" in row.index and row["Brand"] == "Renewed"
        return ["background-color:#fffacd"] * len(row) if is_renewed else [""] * len(row)
        
    try:
        event = st.dataframe(
            display_full_df.style.apply(_highlight, axis=1), 
            use_container_width=True, 
            on_select="rerun", 
            selection_mode="multi-row",
            key="interactive_df"
        )
        selected_indices = event.selection.rows
    except Exception:
        st.dataframe(display_full_df, use_container_width=True)
        selected_indices = []

    if selected_indices:
        download_df = df.iloc[selected_indices]
        st.caption(f"Selected {len(selected_indices)} row(s) for download.")
    else:
        download_df = df
        if 'event' in locals():
            st.caption("No rows selected. Downloading all rows.")

    st.download_button("Download CSV", download_df.to_csv(index=False).encode("utf-8"), f"analysis_{int(time.time())}.csv", "text/csv", icon=":material/download:", key="a_dl")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top: 40px; padding: 18px 24px; background: linear-gradient(135deg, #1A1A1A 0%, #2D2D2D 100%); border-radius: 10px; border-top: 3px solid #F68B1E; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
  <span style="color:#F68B1E; font-weight:800; font-size:0.95rem; font-family:'Nunito',sans-serif;">Product Analyzer</span>
  <span style="color:#999; font-size:0.78rem; font-family:'Nunito',sans-serif;">High-Speed Listing Analyzer</span>
</div>
""", unsafe_allow_html=True)
