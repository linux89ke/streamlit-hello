import cv2
import numpy as np
import requests

def extract_product_data(soup, data, is_sku_search, target):
    # 1. Basic Info (Existing)
    h1 = soup.find('h1')
    data['Product Name'] = h1.text.strip() if h1 else "N/A"
    
    # 2. Warranty Extraction
    # Look for "Warranty" in the sidebar or details section
    warranty_box = soup.find('div', string=re.compile(r'Warranty', re.I))
    if not warranty_box:
        # Fallback: search the whole page text for "X Months Warranty"
        warranty_match = re.search(r'(\d+\s*(?:Month|Year)s?\s*WRTY|Warranty)', soup.get_text(), re.I)
        data['Warranty'] = warranty_match.group(0) if warranty_match else "No Warranty Info"
    else:
        data['Warranty'] = warranty_box.parent.get_text(strip=True)

    # 3. Seller Name (Improved)
    seller_link = soup.select_one('a[href*="/seller/"]')
    data['Seller Name'] = seller_link.text.strip() if seller_link else "Jumia"

    # 4. Keyword Flags (Title & Refurbished Tag)
    name_upper = data['Product Name'].upper()
    data['Has Refurbished Title'] = "REFURBISHED" in name_upper or "RENEWED" in name_upper
    
    # Check for the official Jumia "Refurbished" badge/tag in HTML
    refurb_badge = soup.find('span', string=re.compile(r'Refurbished', re.I))
    data['Has Refurbished Tag'] = refurb_badge is not None

    # 5. Image Processing (Red "Renewed" Tag Detection)
    data['Has Red Image Tag'] = "No"
    image_element = soup.select_one('img[data-main-img]')
    img_url = image_element.get('data-src') or image_element.get('src') if image_element else None
    
    if img_url:
        if img_url.startswith('//'): img_url = 'https:' + img_url
        try:
            # Download image for analysis
            resp = requests.get(img_url, stream=True, timeout=5)
            image_array = np.asarray(bytearray(resp.content), dtype=np.uint8)
            img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            # Define "Red" range in HSV
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            lower_red = np.array([0, 120, 70])
            upper_red = np.array([10, 255, 255])
            mask = cv2.inRange(hsv, lower_red, upper_red)
            
            # If a significant red block exists (the banner), flag it
            if np.sum(mask) > 5000: # Threshold for the "Renewed" banner size
                data['Has Red Image Tag'] = "Yes"
        except:
            pass

    return data
