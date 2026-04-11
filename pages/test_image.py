import streamlit as st
import pandas as pd

# -----------------------------
# CATEGORY INTELLIGENCE (NO PRODUCT DATA)
# -----------------------------
CATEGORY_LIBRARY = {
    "formal shoes": ["oxford", "derby", "brogue", "wingtip", "monk strap", "loafer", "wholecut", "cap toe"],
    "sneakers": ["running", "trainer", "casual", "sports", "chunky"],
    "boots": ["chelsea", "chukka", "combat", "hiking", "work"],
    "t shirts": ["graphic", "plain", "oversized", "v neck", "polo"],
    "car polishes": ["wax", "polish", "compound", "sealant", "scratch remover"],
    "cleaning kits": ["brush", "cloth", "sponge", "detergent", "spray"],
    "exterior care": ["wax", "polish", "coating", "protectant"],
}

# -----------------------------
# MATCHING FUNCTION
# -----------------------------
def suggest_types_from_category(category):
    category_lower = category.lower()

    for key in CATEGORY_LIBRARY:
        if key in category_lower:
            return CATEGORY_LIBRARY[key]

    return []

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Category Type Generator", layout="wide")

st.title("🧠 Category-Based Product Type Generator")
st.write("Works WITHOUT product data. Uses intelligent category matching.")

uploaded_file = st.file_uploader("Upload category file (CSV or XLSX)", type=["csv", "xlsx"])

# -----------------------------
# FILE LOADER
# -----------------------------
def load_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith(".xlsx"):
        return pd.read_excel(uploaded_file)
    else:
        st.error("Unsupported file format")
        return None

if uploaded_file:
    df = load_file(uploaded_file)

    if df is not None:
        st.subheader("Preview Data")
        st.dataframe(df.head())

        column = st.selectbox("Select Category Column", df.columns)

        if st.button("Generate Types"):
            df["suggested_types"] = df[column].apply(
                lambda x: ", ".join(suggest_types_from_category(str(x)))
            )

            st.subheader("Results")
            st.dataframe(df)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Results",
                data=csv,
                file_name="category_type_suggestions.csv",
                mime="text/csv"
            )

# -----------------------------
# SIDEBAR INFO
# -----------------------------
st.sidebar.title("How it works")
st.sidebar.write("""
Since no product data is available, the system uses a predefined
category intelligence library.

It matches keywords inside category names and assigns likely product types.

Example:
Formal Shoes → oxford, derby, brogue
Car Polishes → wax, polish, compound

You can expand the CATEGORY_LIBRARY to improve accuracy.
""")
