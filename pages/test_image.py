import streamlit as st
import pandas as pd
import re
from collections import defaultdict, Counter

# -----------------------------
# CONFIG
# -----------------------------
MIN_FREQUENCY = 2
STOPWORDS = set([
    "men", "women", "shoe", "shoes", "new", "fashion", "leather",
    "black", "brown", "size", "with", "for", "and", "the"
])

# -----------------------------
# TEXT CLEANING
# -----------------------------
def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return text

# -----------------------------
# TOKEN EXTRACTION
# -----------------------------
def extract_tokens(text):
    words = clean_text(text).split()
    tokens = [w for w in words if w not in STOPWORDS and len(w) > 2]
    return tokens

# -----------------------------
# CORE ENGINE
# -----------------------------
def auto_extract_types(df, category_col, title_col):
    category_types = defaultdict(list)

    grouped = df.groupby(category_col)

    for category, group in grouped:
        counter = Counter()

        for title in group[title_col]:
            tokens = extract_tokens(title)
            counter.update(tokens)

        common_terms = [
            word for word, freq in counter.most_common()
            if freq >= MIN_FREQUENCY
        ]

        category_types[category] = common_terms[:15]

    return category_types

# -----------------------------
# FILE LOADER (CSV + XLSX)
# -----------------------------
def load_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith(".xlsx"):
        return pd.read_excel(uploaded_file)
    else:
        st.error("Unsupported file format")
        return None

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Category Type Extractor", layout="wide")

st.title("🧠 Auto Product Type Extraction")
st.write("Upload your product dataset (CSV or XLSX) and automatically discover product types per category.")

uploaded_file = st.file_uploader("Upload file", type=["csv", "xlsx"])

if uploaded_file:
    df = load_file(uploaded_file)

    if df is not None:
        st.subheader("Preview Data")
        st.dataframe(df.head())

        columns = df.columns.tolist()

        category_col = st.selectbox("Select Category Column", columns)
        title_col = st.selectbox("Select Product Title Column", columns)

        if st.button("Run Extraction"):
            result = auto_extract_types(df, category_col, title_col)

            output = []
            for cat, types in result.items():
                output.append({
                    "category": cat,
                    "suggested_types": ", ".join(types)
                })

            output_df = pd.DataFrame(output)

            st.subheader("Results")
            st.dataframe(output_df)

            csv = output_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Results",
                data=csv,
                file_name="category_type_suggestions.csv",
                mime="text/csv"
            )

# -----------------------------
# HOW IT WORKS
# -----------------------------
st.sidebar.title("How it works")
st.sidebar.write("""
1. Upload product data (CSV or XLSX)
2. System cleans text
3. Removes common words (stopwords)
4. Counts frequent terms per category
5. Returns most common meaningful words as product types

Example:
Formal Shoes → oxford, derby, brogue
""")
