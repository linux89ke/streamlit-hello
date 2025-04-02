import streamlit as st
import pandas as pd
import csv
import io
import math
import zipfile
import datetime

# Default country distribution percentages
default_distribution = {
    "Nigeria": (43.00, "NG"),
    "Kenya": (23.00, "KE"),
    "Uganda": (11.80, "UG"),
    "Ghana": (12.00, "GH"),
    "Egypt": (0.00, "EG"),
    "Morocco": (0.00, "MA"),
    "Ivory Coast": (6.00, "IC"),
    "Senegal": (5.00, "SN"),
}

def generate_filename(base_name, extension="xlsx"):
    date_str = datetime.datetime.today().strftime("%d-%m-%Y")
    return f"{base_name} {date_str}.{extension}"

def save_individual_country_files(df, country_counts):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for country in country_counts[:-1]:  # Skip total row
            country_code = country["Country Code"]
            country_name = country["Country"]
            if not country_code:
                continue
            country_df = df[df["Countries"] == country_code]
            country_file_name = generate_filename(f"PIM QC ALL COUNTRIES {country_code}")
            file_buffer = io.BytesIO()
            with pd.ExcelWriter(file_buffer, engine="xlsxwriter") as writer:
                country_df.to_excel(writer, sheet_name="Data", index=False)
            file_buffer.seek(0)
            zip_file.writestr(country_file_name, file_buffer.read())
    zip_buffer.seek(0)
    return zip_buffer

# Streamlit UI
st.title("📊 PIM QC Data Processor")

selected_countries = st.multiselect(
    "Select countries for distribution:",
    options=list(default_distribution.keys()),
    default=[c for c, v in default_distribution.items() if v[0] > 0]
)

uploaded_files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)

if uploaded_files:
    merged_df, file_stats, country_counts = merge_csv_files(uploaded_files, selected_countries)

    if merged_df is not None:
        output_excel = io.BytesIO()
        final_filename = generate_filename("PIM QC ALL COUNTRIES")
        
        with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
            merged_df.to_excel(writer, sheet_name="Merged Data", index=False)
        output_excel.seek(0)

        st.write("### Merged Data Preview:")
        st.dataframe(merged_df.head())

        st.download_button(
            label="📥 Download Merged Excel",
            data=output_excel,
            file_name=final_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        zip_file_buffer = save_individual_country_files(merged_df, country_counts)
        st.download_button(
            label="📥 Download All Country Files (ZIP)",
            data=zip_file_buffer,
            file_name=generate_filename("PIM QC ALL COUNTRIES", "zip"),
            mime="application/zip"
        )
