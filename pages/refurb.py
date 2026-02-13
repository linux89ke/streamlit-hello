import streamlit as st
from PIL import Image
import requests
from io import BytesIO
import numpy as np

# Page config
st.set_page_config(
    page_title="Refurbished Tag Generator",
    page_icon="🏷️",
    layout="wide"
)

# Title and description
st.title("🏷️ Refurbished Product Tag Generator")
st.markdown("Upload a product image and add a refurbished grade tag to it!")

# Sidebar for tag selection
st.sidebar.header("Tag Settings")
tag_type = st.sidebar.selectbox(
    "Select Refurbished Grade:",
    ["Renewed", "Grade A", "Grade B", "Grade C"]
)

# Tag file mapping - will check multiple locations
import os

def get_tag_path(filename):
    """Check multiple possible locations for tag files"""
    possible_paths = [
        filename,  # Same directory as script
        os.path.join(os.path.dirname(__file__), filename),  # Script directory
        os.path.join(os.getcwd(), filename),  # Current working directory
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # If not found, return the filename (will show error)
    return filename

tag_files = {
    "Renewed": "RefurbishedStickerUpdated-Renewd.png",
    "Grade A": "Refurbished-StickerUpdated-Grade-A.png",
    "Grade B": "Refurbished-StickerUpdated-Grade-B.png",
    "Grade C": "Refurbished-StickerUpdated-Grade-C.png"
}

show_bottom_banner = st.sidebar.checkbox(
    "Show condition banner at bottom",
    value=True,
    help="Display the condition text banner at the bottom of the image"
)

st.sidebar.markdown("---")
st.sidebar.info("""
**Layout:**
- Tag overlays on the right side of the product
- Tag height matches product height  
- Optional bottom condition banner
- Output maintains original product dimensions
""")

# Main content area
col1, col2 = st.columns(2)

with col1:
    st.subheader("📤 Upload Product Image")
    
    # Upload method selection
    upload_method = st.radio(
        "Choose upload method:",
        ["Upload from device", "Load from URL"]
    )
    
    product_image = None
    
    if upload_method == "Upload from device":
        uploaded_file = st.file_uploader(
            "Choose an image file",
            type=["png", "jpg", "jpeg", "webp"]
        )
        if uploaded_file is not None:
            product_image = Image.open(uploaded_file).convert("RGBA")
    
    else:
        image_url = st.text_input("Enter image URL:")
        if image_url:
            try:
                response = requests.get(image_url)
                product_image = Image.open(BytesIO(response.content)).convert("RGBA")
                st.success("✅ Image loaded successfully!")
            except Exception as e:
                st.error(f"❌ Error loading image: {str(e)}")

with col2:
    st.subheader("✨ Preview")
    
    if product_image is not None:
        # Load the selected tag
        try:
            tag_filename = tag_files[tag_type]
            tag_path = get_tag_path(tag_filename)
            
            if not os.path.exists(tag_path):
                st.error(f"❌ Tag file not found: {tag_filename}")
                st.info("""
                **Please make sure the tag PNG files are in the same directory as this app.**
                
                Required files:
                - RefurbishedStickerUpdated-Renewd.png
                - Refurbished-StickerUpdated-Grade-A.png
                - Refurbished-StickerUpdated-Grade-B.png
                - Refurbished-StickerUpdated-Grade-C.png
                """)
                st.stop()
            
            tag_image = Image.open(tag_path).convert("RGBA")
            
            # Get original dimensions
            prod_width, prod_height = product_image.size
            tag_img_width, tag_img_height = tag_image.size
            
            # The tag images have a bottom banner (~10% of height)
            # If user doesn't want the banner, crop it out
            if not show_bottom_banner:
                # Calculate banner height (approximately 10% of tag image)
                banner_height = int(tag_img_height * 0.15)
                # Crop the tag to remove bottom banner
                tag_image = tag_image.crop((0, 0, tag_img_width, tag_img_height - banner_height))
            
            # Calculate new tag size to match product height
            new_tag_height = prod_height
            tag_aspect_ratio = tag_image.size[0] / tag_image.size[1]  # width/height
            new_tag_width = int(new_tag_height * tag_aspect_ratio)
            
            # Resize tag to match product height
            tag_resized = tag_image.resize((new_tag_width, new_tag_height), Image.Resampling.LANCZOS)
            
            # Create a new canvas that fits both product and tag side by side
            # Keep original product dimensions
            result_width = prod_width
            result_height = prod_height
            
            # Create new image with white background for JPEG compatibility
            result_image = Image.new("RGB", (result_width, result_height), (255, 255, 255))
            
            # Paste product image first
            if product_image.mode == 'RGBA':
                result_image.paste(product_image, (0, 0), product_image)
            else:
                result_image.paste(product_image, (0, 0))
            
            # Calculate position for tag - align to right edge
            tag_x_position = prod_width - new_tag_width
            
            # Paste tag on top, overlaying the right side
            if tag_resized.mode == 'RGBA':
                result_image.paste(tag_resized, (tag_x_position, 0), tag_resized)
            else:
                result_image.paste(tag_resized, (tag_x_position, 0))
            
            # Display the result
            st.image(result_image, use_container_width=True)
            
            # Download button
            st.markdown("---")
            
            # Convert image to bytes as JPEG
            buf = BytesIO()
            result_image.save(buf, format="JPEG", quality=95)
            buf.seek(0)
            
            st.download_button(
                label="⬇️ Download Tagged Image (JPEG)",
                data=buf,
                file_name=f"refurbished_product_{tag_type.lower().replace(' ', '_')}.jpg",
                mime="image/jpeg",
                use_container_width=True
            )
            
        except Exception as e:
            st.error(f"❌ Error processing image: {str(e)}")
    else:
        st.info("👆 Upload or provide a URL for a product image to get started!")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
    <p>💡 Tip: The tag will automatically scale to match your product image height</p>
    </div>
    """,
    unsafe_allow_html=True
)
