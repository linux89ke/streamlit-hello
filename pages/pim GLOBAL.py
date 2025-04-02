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
    date_str = datetime.datetime.today().strftime("%d-%m-%Y")
    folder_name = f"PIM QC ALL COUNTRIES {date_str}/"
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for country in country_counts[:-1]:  # Skip total row
            country_code = country["Country Code"]
            if not country_code:
                continue
            country_df = df[df["Countries"] == country_code]
            file_buffer = io.BytesIO()
            with pd.ExcelWriter(file_buffer, engine="xlsxwriter") as writer:
                country_df.to_excel(writer, sheet_name="Data", index=False)
            file_buffer.seek(0)
            zip_file.writestr(f"{folder_name}PIM QC {country_code}.xlsx", file_buffer.read())
    zip_buffer.seek(0)
    return zip_buffer

def detect_delimiter(file):
    sample = file.read(2048)
    file.seek(0)
    return ';' if b';' in sample else ','

def repair_csv(file, delimiter):
    cleaned_data = []
    header = None
    expected_columns = None
    row_count = 0

    file.seek(0)
    text_data = file.read().decode("utf-8").splitlines()
    reader = csv.reader(text_data, delimiter=delimiter)

    for i, row in enumerate(reader):
        if i == 0:
            header = row
            expected_columns = len(header)
            cleaned_data.append(row)
        else:
            row_count += 1
            if len(row) == expected_columns:
                cleaned_data.append(row)
            elif len(row) > expected_columns:
                row = row[:expected_columns - 1] + [" ".join(row[expected_columns - 1:])]
                cleaned_data.append(row)
            elif len(row) < expected_columns:
                row.extend([""] * (expected_columns - len(row)))
                cleaned_data.append(row)

    return pd.DataFrame(cleaned_data[1:], columns=cleaned_data[0]), row_count

def distribute_countries(df, selected_countries):
    total_rows = len(df)
    active_distribution = {k: v for k, v in default_distribution.items() if k in selected_countries}
    total_percentage = sum(v[0] for v in active_distribution.values())
    adjusted_distribution = {k: (v[0] / total_percentage, v[1]) for k, v in active_distribution.items()}
    country_rows = {k: math.floor(v[0] * total_rows) for k, v in adjusted_distribution.items()}
    assigned_rows = sum(country_rows.values())
    remaining_rows = total_rows - assigned_rows
    sorted_countries = sorted(active_distribution.keys(), key=lambda c: -adjusted_distribution[c][0])
    for i in range(remaining_rows):
        country_rows[sorted_countries[i % len(sorted_countries)]] += 1
    df_list = []
    country_counts = []
    start_idx = 0
    for country, code in [(k, adjusted_distribution[k][1]) for k in sorted_countries]:
        count = country_rows[country]
        if count > 0:
            df_subset = df.iloc[start_idx:start_idx + count].copy()
            df_subset["Countries"] = code
            df_list.append(df_subset)
            start_idx += count
            country_counts.append({"Country": country, "Country Code": code, "Assigned Rows": count})
    country_counts.append({"Country": "**Total**", "Country Code": "", "Assigned Rows": total_rows})
    return pd.concat(df_list, ignore_index=True), country_counts

def merge_csv_files(files, selected_countries):
    dataframes = []
    file_stats = []
    total_rows = 0
    for file in files:
        delimiter = detect_delimiter(file)
        try:
            df, row_count = repair_csv(file, delimiter)
            dataframes.append(df)
            file_stats.append({"Filename": file.name, "Rows (Excluding Header)": row_count})
            total_rows += row_count
        except Exception as e:
            st.error(f"⚠️ Error processing {file.name}: {e}")
    if dataframes:
        merged_df = pd.concat(dataframes, ignore_index=True)
        if 'CATEGORY' in merged_df.columns:
            merged_df = merged_df.sort_values(by='CATEGORY', ascending=True)
        merged_df, country_counts = distribute_countries(merged_df, selected_countries)
        file_stats.append({"Filename": "**Total**", "Rows (Excluding Header)": total_rows})
        return merged_df, file_stats, country_counts
    return None, file_stats, []

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

        st.write("### File Statistics (Reorderable)")
        file_stats_df = pd.DataFrame(file_stats)
        file_stats_df = st.data_editor(file_stats_df, use_container_width=True)

        st.write("### Country Distribution")
        st.table(country_counts)

        st.download_button("📥 Download Merged Excel", output_excel, final_filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        zip_file_buffer = save_individual_country_files(merged_df, country_counts)
        st.download_button("📥 Download All Country Files (ZIP)", zip_file_buffer, generate_filename("PIM QC ALL COUNTRIES", "zip"), mime="application/zip")
