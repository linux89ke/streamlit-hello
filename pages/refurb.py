import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io

def add_renewed_tag(input_image):
    # Open the image and convert to RGBA to handle transparency if needed
    img = Image.open(input_image).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # 1. Define Tag Dimensions (Adjust these ratios as needed)
    tag_width = int(width * 0.12)  # 12% of image width
    tag_height = int(height * 0.75) # 75% of image height
    
    # Position: Right side, vertically centered
    x1 = width - tag_width
    y1 = (height - tag_height) // 2
    x2 = width
    y2 = y1 + tag_height

    # 2. Draw the Red Background
    draw.rectangle([x1, y1, x2, y2], fill="#E31E24")

    # 3. Add the "RENEWED" Text
    # Note: You may need to provide a path to a .ttf font file on your system
    try:
        font_size = int(tag_width * 0.6)
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # Create a separate canvas for the vertical text
    text_str = "RENEWED"
    # Calculate text size using a dummy image or textbbox
    tw, th = draw.textbbox((0, 0), text_str, font=font)[2:]
    
    txt_img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(txt_img)
    d.text((0, 0), text_str, font=font, fill="white")
    
    # Rotate text 90 degrees and paste it onto the main image
    rotated_txt = txt_img.rotate(90, expand=1)
    
    # Center the rotated text inside the red bar
    paste_x = x1 + (tag_width - rotated_txt.width) // 2
    paste_y = y1 + (tag_height - rotated_txt.height) // 2
    img.paste(rotated_txt, (paste_x, paste_y), rotated_txt)

    return img

# --- Streamlit UI ---
st.title("Laptop Tag Automator")
st.write("Upload an image to automatically add the red 'RENEWED' banner.")

uploaded_file = st.file_uploader("Choose a laptop image...", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Process image
    result_img = add_renewed_tag(uploaded_file)
    
    # Display side-by-side
    st.image(result_img, caption="Processed Image", use_container_width=True)
    
    # Download button
    buf = io.BytesIO()
    result_img.save(buf, format="JPEG")
    byte_im = buf.getvalue()
    
    st.download_button(
        label="Download Tagged Image",
        data=byte_im,
        file_name="renewed_laptop.jpg",
        mime="image/jpeg"
    )
