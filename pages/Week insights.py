import streamlit as st
import pandas as pd

# Title
st.title("QC Regional Weekly Review Insights")
st.write("Upload the Excel file to analyze data for Seller Center and PIM across Kenya and Uganda.")

# File Upload
uploaded_file = st.file_uploader("Choose the Weekly Review Excel file", type=["xls", "xlsx"])

if uploaded_file:
    try:
        # Load Excel data
        data = pd.read_excel(uploaded_file, sheet_name=None)  # Load all sheets
        st.success("File uploaded successfully!")
        
        # Sheet Selection
        sheet_names = list(data.keys())
        selected_sheet = st.selectbox("Select a sheet to analyze:", sheet_names)
        df = data[selected_sheet]
        st.write(f"Preview of `{selected_sheet}`:")
        st.dataframe(df.head())
        
        # Ensure column names are strings
        df.columns = df.columns.map(str)
        
        # Separate data for Seller Center and PIM
        st.subheader("Data Segmentation by Platform and Region")
        
        # Extract rows for Kenya and Uganda separately
        kenya_data = df[df["Country"].str.contains("Kenya", case=False, na=False)]
        uganda_data = df[df["Country"].str.contains("Uganda", case=False, na=False)]
        
        # Process Seller Center Data
        st.write("**Seller Center Analysis**")
        seller_center_data = df[df["Platform"].str.contains("Seller Center", case=False, na=False)]
        
        if not seller_center_data.empty:
            st.write(seller_center_data)
            approved_sc = seller_center_data["Approved"].sum()
            rejected_sc = seller_center_data["Rejected"].sum()
            total_work_sc = seller_center_data["Total Work Done"].sum()
            
            # Approval and Rejection Rates
            approval_rate_sc = (approved_sc / total_work_sc) * 100 if total_work_sc > 0 else 0
            rejection_rate_sc = (rejected_sc / total_work_sc) * 100 if total_work_sc > 0 else 0
            
            # Metrics
            st.metric("Total Work Done (Seller Center)", value=int(total_work_sc))
            st.metric("Approval Rate (Seller Center)", value=f"{approval_rate_sc:.2f}%")
            st.metric("Rejection Rate (Seller Center)", value=f"{rejection_rate_sc:.2f}%")
        else:
            st.warning("No data found for Seller Center.")

        # Process PIM Data
        st.write("**PIM Analysis**")
        pim_data = df[df["Platform"].str.contains("PIM", case=False, na=False)]
        
        if not pim_data.empty:
            st.write(pim_data)
            approved_pim = pim_data["Approved"].sum()
            rejected_pim = pim_data["Rejected"].sum()
            total_work_pim = pim_data["Total Work Done"].sum()
            
            # Approval and Rejection Rates
            approval_rate_pim = (approved_pim / total_work_pim) * 100 if total_work_pim > 0 else 0
            rejection_rate_pim = (rejected_pim / total_work_pim) * 100 if total_work_pim > 0 else 0
            
            # Metrics
            st.metric("Total Work Done (PIM)", value=int(total_work_pim))
            st.metric("Approval Rate (PIM)", value=f"{approval_rate_pim:.2f}%")
            st.metric("Rejection Rate (PIM)", value=f"{rejection_rate_pim:.2f}%")
        else:
            st.warning("No data found for PIM.")

        # Comparative Insights
        st.subheader("Comparison Between Platforms")
        comparison_data = pd.DataFrame({
            "Metric": ["Total Work Done", "Approved", "Rejected"],
            "Seller Center": [total_work_sc, approved_sc, rejected_sc],
            "PIM": [total_work_pim, approved_pim, rejected_pim]
        }).set_index("Metric")
        st.bar_chart(comparison_data)
    
    except Exception as e:
        st.error(f"An error occurred: {e}")
