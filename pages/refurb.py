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
- Product centered in left area
- Vertical tag on right side (full height)
- Optional bottom banner (full width)
- Clean, professional e-commerce layout
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
            tag_full_width, tag_full_height = tag_image.size
            
            # The tag images include both the vertical tag AND bottom banner
            # Bottom banner is approximately 10% of the tag image height
            banner_height_ratio = 0.095  # More precise ratio
            banner_height = int(tag_full_height * banner_height_ratio)
            
            # Separate the vertical tag from the banner
            vertical_tag = tag_image.crop((0, 0, tag_full_width, tag_full_height - banner_height))
            bottom_banner = tag_image.crop((0, tag_full_height - banner_height, tag_full_width, tag_full_height))
            
            # Output canvas dimensions
            canvas_width = orig_prod_width
            canvas_height = orig_prod_height
            
            # Calculate sizes based on whether banner is shown
            if show_bottom_banner:
                # Scale banner to canvas width
                banner_final_height = int(canvas_width * banner_height_ratio * 0.15)  # Keep banner proportional
                banner_resized = bottom_banner.resize((canvas_width, banner_final_height), Image.Resampling.LANCZOS)
                
                # Vertical tag should span from top to just above banner
                available_height_for_tag = canvas_height - banner_final_height
            else:
                banner_final_height = 0
                available_height_for_tag = canvas_height
            
            # The vertical tag should take full height (top to banner)
            new_tag_height = available_height_for_tag
            tag_aspect_ratio = vertical_tag.size[0] / vertical_tag.size[1]  # width/height
            new_tag_width = int(new_tag_height * tag_aspect_ratio)
            
            # Resize the vertical tag to full height
            tag_resized = vertical_tag.resize((new_tag_width, new_tag_height), Image.Resampling.LANCZOS)
            
            # Calculate available space for product (left side)
            available_width_for_product = canvas_width - new_tag_width
            
            if available_width_for_product < 100:
                st.error("❌ Image is too small. Please upload a larger image.")
                st.stop()
            
            # Scale product to fit in the available area (left side, above banner if shown)
            available_height_for_product = available_height_for_tag
            
            # Calculate product scaling to fit in left area
            product_aspect_ratio = orig_prod_height / orig_prod_width
            
            # Try fitting by width first
            new_prod_width = available_width_for_product
            new_prod_height = int(new_prod_width * product_aspect_ratio)
            
            # If too tall, fit by height instead
            if new_prod_height > available_height_for_product:
                new_prod_height = available_height_for_product
                new_prod_width = int(new_prod_height / product_aspect_ratio)
            
            # Validate dimensions
            if new_prod_width <= 0 or new_prod_height <= 0:
                st.error("❌ Cannot fit product. Please try a larger image.")
                st.stop()
            
            # Resize product
            product_resized = product_image.resize((new_prod_width, new_prod_height), Image.Resampling.LANCZOS)
            
            # Create result image with white background
            result_image = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
            
            # Position product in the left area, centered vertically in available space
            prod_y_position = (available_height_for_tag - new_prod_height) // 2
            prod_x_position = (available_width_for_product - new_prod_width) // 2
            
            # Paste product image
            if product_resized.mode == 'RGBA':
                result_image.paste(product_resized, (prod_x_position, prod_y_position), product_resized)
            else:
                result_image.paste(product_resized, (prod_x_position, prod_y_position))
            
            # Position vertical tag on the right side (full height from top to banner)
            tag_x_position = canvas_width - new_tag_width
            tag_y_position = 0
            
            # Paste vertical tag
            if tag_resized.mode == 'RGBA':
                result_image.paste(tag_resized, (tag_x_position, tag_y_position), tag_resized)
            else:
                result_image.paste(tag_resized, (tag_x_position, tag_y_position))
            
            # Paste bottom banner at the bottom (full width) if enabled
            if show_bottom_banner:
                banner_y_position = canvas_height - banner_final_height
                if banner_resized.mode == 'RGBA':
                    result_image.paste(banner_resized, (0, banner_y_position), banner_resized)
                else:
                    result_image.paste(banner_resized, (0, banner_y_position))
            
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
