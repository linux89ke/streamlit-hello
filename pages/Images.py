import streamlit as st
import pandas as pd
import requests
from PIL import Image
from io import BytesIO

# Streamlit app title
st.title("Product Details with Images in Two-Column Table")

# File uploader
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

# Initialize an empty list to store the product details
product_data = []

if uploaded_file:
    try:
        # Read the CSV file with the correct delimiter
        df = pd.read_csv(uploaded_file, on_bad_lines='skip', encoding='utf-8', sep=";")

        # Strip whitespace from column names
        df.columns = df.columns.str.strip()

        # Check if the column 'MAIN_IMAGE' exists
        if 'MAIN_IMAGE' not in df.columns:
            st.error("The file does not contain a 'MAIN_IMAGE' column. Please ensure the column is correctly named.")
        else:
            # Create a list to store the product details (excluding image for the table)
            for index, row in df.iterrows():
                image_url = row['MAIN_IMAGE']
                try:
                    # Fetch the image
                    response = requests.get(image_url, timeout=10)
                    response.raise_for_status()
                    img = Image.open(BytesIO(response.content))

                    # Add product details to the list (excluding image object)
                    product_data.append({
                        "SELLER NAME": row.get('SELLER_NAME', 'N/A'),
                        "NAME": row.get('NAME', 'N/A'),
                        "COLOR": row.get('COLOR', 'N/A'),
                        "CATEGORY": row.get('CATEGORY', 'N/A'),
                        "PRODUCT SET SID": row.get('PRODUCT_SET_SID', 'N/A'),
                        "PARENTSKU": row.get('PARENTSKU', 'N/A'),
                        "GLOBAL PRICE": row.get('GLOBAL_PRICE', 'N/A'),
                        "GLOBAL SALE PRICE": row.get('GLOBAL_SALE_PRICE', 'N/A'),
                        "Image URL": image_url,  # Keep image URL in the table for reference
                        "Issue": None  # Placeholder for issue selection
                    })

                    # Display images and product details in a two-column layout
                    col1, col2 = st.columns([1, 3])  # Adjust the size ratio as needed
                    with col1:
                        # Add hover effect CSS for enlarging image on hover
                        st.markdown(
                            f"""
                            <style>
                            .img-hover-container {{
                                position: relative;
                                display: inline-block;
                            }}
                            .img-hover-container img {{
                                width: 100%;
                                height: auto;
                                border-radius: 10px;
                            }}
                            .img-hover-container:hover img {{
                                transform: scale(1.5);  /* Make the image bigger on hover */
                                transition: transform 0.3s ease;
                            }}
                            </style>
                            <div class="img-hover-container">
                                <img src="{image_url}" alt="Image for {row.get('NAME', 'N/A')}" />
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    with col2:
                        st.write(f"**SELLER NAME**: {row.get('SELLER_NAME', 'N/A')}")
                        st.write(f"**NAME**: {row.get('NAME', 'N/A')}")
                        st.write(f"**COLOR**: {row.get('COLOR', 'N/A')}")
                        st.write(f"**CATEGORY**: {row.get('CATEGORY', 'N/A')}")
                        st.write(f"**PRODUCT SET SID**: {row.get('PRODUCT_SET_SID', 'N/A')}")
                        st.write(f"**PARENTSKU**: {row.get('PARENTSKU', 'N/A')}")
                        st.write(f"**GLOBAL PRICE**: {row.get('GLOBAL_PRICE', 'N/A')}")
                        st.write(f"**GLOBAL SALE PRICE**: {row.get('GLOBAL_SALE_PRICE', 'N/A')}")

                    # Add radio buttons to select the issue (only one option can be selected)
                    issue = st.radio(
                        f"Select issue for {row.get('NAME', 'N/A')}",
                        options=["", "Image looks stretched", "Image Is Blurry", "Poor Image Quality/Editing", "Wrong category"],
                        key=f"issue_{index}"
                    )
                    product_data[-1]["Issue"] = issue  # Store the selected issue

                except Exception as e:
                    # Handle errors in image fetching and add a placeholder for missing images
                    product_data.append({
                        "SELLER NAME": row.get('SELLER_NAME', 'N/A'),
                        "NAME": row.get('NAME', 'N/A'),
                        "COLOR": row.get('COLOR', 'N/A'),
                        "CATEGORY": row.get('CATEGORY', 'N/A'),
                        "PRODUCT SET SID": row.get('PRODUCT_SET_SID', 'N/A'),
                        "PARENTSKU": row.get('PARENTSKU', 'N/A'),
                        "GLOBAL PRICE": row.get('GLOBAL_PRICE', 'N/A'),
                        "GLOBAL SALE PRICE": row.get('GLOBAL_SALE_PRICE', 'N/A'),
                        "Image URL": f"Error loading image: {e}",
                        "Issue": None
                    })

                # Add a separator between products
                st.markdown("---")

            # Add a button to export selected products
            if st.button("Export Products with Issues"):
                # Filter products with an issue selected
                products_with_issues = [product for product in product_data if product["Issue"]]

                if products_with_issues:
                    # Create a DataFrame from the products with issues
                    issue_df = pd.DataFrame(products_with_issues)

                    # Save the DataFrame as an Excel file
                    output_file = "/mnt/data/products_with_issues.xlsx"
                    issue_df.to_excel(output_file, index=False)

                    # Provide a download link for the user
                    st.download_button(
                        label="Download Excel with Products and Issues",
                        data=open(output_file, "rb").read(),
                        file_name="products_with_issues.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("No products have been marked with an issue. Please select at least one issue.")

    except Exception as e:
        st.error(f"An error occurred: {e}")
else:
    st.info("Please upload a CSV file to proceed.")
