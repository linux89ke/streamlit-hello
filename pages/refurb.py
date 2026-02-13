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
- Output dimensions match the refurbished tag
- Product scaled to fit in left area
- Vertical tag at original size on right
- Optional bottom banner (full width)
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
            orig_prod_width, orig_prod_height = product_image.size
            canvas_width, canvas_height = tag_image.size
            
            # The tag PNG already has the complete layout:
            # - Black/transparent left area for product
            # - Red vertical tag on right
            # - Red banner at bottom
            
            # Approximate measurements from the 680x680 tag:
            # - Banner height: ~65 pixels (9.5% of height)
            # - Vertical tag width: ~110 pixels (need to be more conservative - use 18%)
            
            banner_height = int(canvas_height * 0.095)
            vert_tag_width = int(canvas_width * 0.18)  # Increased from 0.16 to 0.18
            
            # Available area for product (need to leave room for the tag)
            available_width = canvas_width - vert_tag_width
            if show_bottom_banner:
                available_height = canvas_height - banner_height
            else:
                available_height = canvas_height
                # If hiding banner, we need to crop it from the tag image
                tag_image = tag_image.crop((0, 0, canvas_width, canvas_height - banner_height))
                canvas_height = canvas_height - banner_height
            
            # Scale product to fit in available area with more padding
            # Reduce available space by 15% on each side for more padding
            padding_factor = 0.80  # Changed from 0.90 to 0.80 for smaller product
            fit_width = int(available_width * padding_factor)
            fit_height = int(available_height * padding_factor)
            
            product_aspect_ratio = orig_prod_height / orig_prod_width
            
            # Try fitting by width
            new_prod_width = fit_width
            new_prod_height = int(new_prod_width * product_aspect_ratio)
            
            # If too tall, fit by height
            if new_prod_height > fit_height:
                new_prod_height = fit_height
                new_prod_width = int(new_prod_height / product_aspect_ratio)
            
            # Resize product
            product_resized = product_image.resize((new_prod_width, new_prod_height), Image.Resampling.LANCZOS)
            
            # Create result by starting with white background
            result_image = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
            
            # Center product in the available left area
            prod_x = (available_width - new_prod_width) // 2
            prod_y = (available_height - new_prod_height) // 2
            
            # Paste product FIRST
            if product_resized.mode == 'RGBA':
                result_image.paste(product_resized, (prod_x, prod_y), product_resized)
            else:
                result_image.paste(product_resized, (prod_x, prod_y))
            
            # Then paste the tag template ON TOP (so it overlays the product)
            if tag_image.mode == 'RGBA':
                result_image.paste(tag_image, (0, 0), tag_image)
            else:
                result_image.paste(tag_image, (0, 0))
            
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
