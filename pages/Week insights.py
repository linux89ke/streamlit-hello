import streamlit as st
import pandas as pd
from io import StringIO
from st_aggrid import AgGrid, GridOptionsBuilder
import matplotlib.pyplot as plt

# Function to parse raw data from text area
def parse_data(raw_data):
    try:
        # Convert the pasted data into a DataFrame
        data = pd.read_csv(StringIO(raw_data), sep="\t")
        return data
    except Exception as e:
        st.error("Error parsing data. Ensure it is tab-separated like a CSV.")
        return None

# Streamlit App
st.title("Editable Weekly Product Rejection Insights")

# Tabs for different input methods
tab1, tab2 = st.tabs(["Paste Data", "Editable Grid"])

# **Tab 1: Paste Data**
with tab1:
    st.subheader("Paste Your Data Below")
    raw_data = st.text_area(
        "Copy data from Excel and paste it here (Ensure it's tab-separated)",
        height=200,
        placeholder="E.g.\nWeek\tCountry\tApproved\tRejected\nWeek 46\tKE\t109878\t8653\n...",
    )

    if raw_data.strip():  # Process only if there is input
        data = parse_data(raw_data)
        if data is not None:
            st.subheader("Parsed Dataset")
            st.dataframe(data)

            # Perform basic calculations
            st.subheader("Basic Insights")
            for week in data["Week"].unique():
                for country in data["Country"].unique():
                    subset = data[(data["Week"] == week) & (data["Country"] == country)]
                    if not subset.empty:
                        approved = subset["Approved"].values[0]
                        rejected = subset["Rejected"].values[0]
                        total = approved + rejected
                        approval_rate = (approved / total) * 100 if total > 0 else 0
                        rejection_rate = (rejected / total) * 100 if total > 0 else 0

                        st.write(f"**{week} - {country}**")
                        st.write(f"Approved: {approved}, Rejected: {rejected}")
                        st.write(f"Approval Rate: {approval_rate:.2f}%, Rejection Rate: {rejection_rate:.2f}%")

# **Tab 2: Editable Grid**
with tab2:
    st.subheader("Editable Dataset")
    # Default dataset for demonstration
    default_data = {
        "Week": ["Week 46", "Week 46", "Week 47", "Week 47"],
        "Country": ["KE", "UG", "KE", "UG"],
        "Approved": [109878, 100893, 88683, 97322],
        "Rejected": [8653, 31673, 84354, 16823],
        "Total": [118531, 132566, 173037, 114145],
    }
    df = pd.DataFrame(default_data)

    # Set up AgGrid options
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_pagination(enabled=True)
    gb.configure_default_column(editable=True)  # Allow editing
    grid_options = gb.build()

    # Display editable grid
    grid_response = AgGrid(df, gridOptions=grid_options, editable=True, fit_columns_on_grid_load=True)
    updated_data = pd.DataFrame(grid_response['data'])  # Extract updated data

    st.subheader("Updated Dataset")
    st.dataframe(updated_data)

    # Perform basic calculations
    st.subheader("Basic Insights")
    for week in updated_data["Week"].unique():
        for country in updated_data["Country"].unique():
            subset = updated_data[(updated_data["Week"] == week) & (updated_data["Country"] == country)]
            if not subset.empty:
                approved = subset["Approved"].values[0]
                rejected = subset["Rejected"].values[0]
                total = approved + rejected
                approval_rate = (approved / total) * 100 if total > 0 else 0
                rejection_rate = (rejected / total) * 100 if total > 0 else 0

                st.write(f"**{week} - {country}**")
                st.write(f"Approved: {approved}, Rejected: {rejected}")
                st.write(f"Approval Rate: {approval_rate:.2f}%, Rejection Rate: {rejection_rate:.2f}%")

# Optional: Downloadable report
st.subheader("Download Insights Report")
def generate_report(data):
    report_path = "Editable_Insights_Report.xlsx"
    with pd.ExcelWriter(report_path, engine='xlsxwriter') as writer:
        data.to_excel(writer, sheet_name='Data', index=False)
    return report_path

if st.button("Generate Report"):
    # Determine active data (from text or grid)
    final_data = updated_data if 'updated_data' in locals() else data
    if final_data is not None:
        report_path = generate_report(final_data)
        st.success("Report generated successfully!")
        st.download_button("Download Report", report_path, file_name="Editable_Insights_Report.xlsx")
