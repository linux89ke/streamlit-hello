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

# Tag file mapping
tag_files = {
    "Renewed": "RefurbishedStickerUpdated-Renewd.png",
    "Grade A": "Refurbished-StickerUpdated-Grade-A.png",
    "Grade B": "Refurbished-StickerUpdated-Grade-B.png",
    "Grade C": "Refurbished-StickerUpdated-Grade-C.png"
}

# Tag size settings
st.sidebar.header("Tag Size Settings")
tag_width_percent = st.sidebar.slider(
    "Tag Width (% of image width)",
    min_value=10,
    max_value=50,
    value=25,
    step=5
)

# Position settings
st.sidebar.header("Position Settings")
horizontal_position = st.sidebar.selectbox(
    "Horizontal Position:",
    ["Right", "Left"]
)

vertical_position = st.sidebar.selectbox(
    "Vertical Position:",
    ["Top", "Middle", "Bottom"]
)

# Padding settings
horizontal_padding = st.sidebar.slider(
    "Horizontal Padding (pixels)",
    min_value=0,
    max_value=100,
    value=20,
    step=5
)

vertical_padding = st.sidebar.slider(
    "Vertical Padding (pixels)",
    min_value=0,
    max_value=100,
    value=20,
    step=5
)

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
            tag_image = Image.open(tag_files[tag_type]).convert("RGBA")
            
            # Get original dimensions
            prod_width, prod_height = product_image.size
            
            # Calculate new tag size based on percentage of image width
            new_tag_width = int(prod_width * (tag_width_percent / 100))
            tag_aspect_ratio = tag_image.size[1] / tag_image.size[0]
            new_tag_height = int(new_tag_width * tag_aspect_ratio)
            
            # Resize tag
            tag_resized = tag_image.resize((new_tag_width, new_tag_height), Image.Resampling.LANCZOS)
            
            # Calculate position
            if horizontal_position == "Right":
                x_position = prod_width - new_tag_width - horizontal_padding
            else:  # Left
                x_position = horizontal_padding
            
            if vertical_position == "Top":
                y_position = vertical_padding
            elif vertical_position == "Middle":
                y_position = (prod_height - new_tag_height) // 2
            else:  # Bottom
                y_position = prod_height - new_tag_height - vertical_padding
            
            # Create a copy of the product image
            result_image = product_image.copy()
            
            # Paste the tag onto the product image
            result_image.paste(tag_resized, (x_position, y_position), tag_resized)
            
            # Display the result
            st.image(result_image, use_container_width=True)
            
            # Download button
            st.markdown("---")
            
            # Convert to RGB for JPEG or keep RGBA for PNG
            output_format = st.selectbox("Output format:", ["PNG", "JPEG"])
            
            # Convert image to bytes
            buf = BytesIO()
            if output_format == "JPEG":
                # Convert RGBA to RGB for JPEG
                rgb_image = result_image.convert("RGB")
                rgb_image.save(buf, format="JPEG", quality=95)
                file_extension = "jpg"
                mime_type = "image/jpeg"
            else:
                result_image.save(buf, format="PNG")
                file_extension = "png"
                mime_type = "image/png"
            
            buf.seek(0)
            
            st.download_button(
                label=f"⬇️ Download Tagged Image ({output_format})",
                data=buf,
                file_name=f"refurbished_product_{tag_type.lower().replace(' ', '_')}.{file_extension}",
                mime=mime_type,
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
    <p>💡 Tip: Adjust the tag size and position using the sidebar controls</p>
    </div>
    """,
    unsafe_allow_html=True
)
