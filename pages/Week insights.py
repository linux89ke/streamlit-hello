import streamlit as st
import pandas as pd

# Title
st.title("QC Regional Weekly Review Insights")
st.write("Upload the Excel file to analyze Seller Center and PIM performance.")

# File Upload
uploaded_file = st.file_uploader("Choose the Weekly Review Excel file", type=["xls", "xlsx"])

if uploaded_file:
    try:
        # Load Excel data
        data = pd.read_excel(uploaded_file, sheet_name=None)
        st.success("File uploaded successfully!")
        
        # Sheet Selection
        sheet_names = list(data.keys())
        selected_sheet = st.selectbox("Select a sheet to analyze:", sheet_names)
        
        df = data[selected_sheet]
        st.write(f"Preview of `{selected_sheet}`:")
        st.dataframe(df.head())
        
        # Ensure column names are strings
        df.columns = df.columns.map(str)
        
        # Filter data by platforms
        st.subheader("Data Segmentation by Platform")
        
        platforms = ["Seller Center", "PIM"]
        for platform in platforms:
            st.write(f"**Platform: {platform}**")
            
            # Filter platform data
            platform_data = df[df["Platform"].str.contains(platform, case=False, na=False)]
            
            if platform_data.empty:
                st.warning(f"No data found for {platform}.")
                continue
            
            st.write(platform_data)
            
            # Separate Approved, Rejected, and Total Work Done
            approved = platform_data["Approved"].sum()
            rejected = platform_data["Rejected"].sum()
            total_work_done = platform_data["Total Work Done"].sum()
            
            # Approval and Rejection Rates
            approval_rate = (approved / total_work_done) * 100 if total_work_done > 0 else 0
            rejection_rate = (rejected / total_work_done) * 100 if total_work_done > 0 else 0
            
            # Display Metrics
            st.metric(label=f"Total Work Done ({platform})", value=int(total_work_done))
            st.metric(label=f"Approval Rate ({platform})", value=f"{approval_rate:.2f}%")
            st.metric(label=f"Rejection Rate ({platform})", value=f"{rejection_rate:.2f}%")
            
            # Insights Visualization
            st.write(f"**Weekly Trends for {platform}**")
            week_columns = [col for col in platform_data.columns if "Week" in col or col.startswith("W")]
            weekly_data = platform_data[week_columns].sum()
            st.line_chart(weekly_data)
        
        # Overall Insights
        st.subheader("Overall Insights")
        
        overall_approved = df["Approved"].sum()
        overall_rejected = df["Rejected"].sum()
        overall_total_work_done = df["Total Work Done"].sum()
        
        st.metric(label="Overall Total Work Done", value=int(overall_total_work_done))
        st.metric(label="Overall Approval Rate", value=f"{(overall_approved / overall_total_work_done) * 100:.2f}%" if overall_total_work_done > 0 else "0%")
        st.metric(label="Overall Rejection Rate", value=f"{(overall_rejected / overall_total_work_done) * 100:.2f}%" if overall_total_work_done > 0 else "0%")
        
        # Comparison Visualization
        st.write("**Platform Comparison**")
        comparison_df = pd.DataFrame({
            "Platform": platforms,
            "Total Work Done": [df[df["Platform"].str.contains(p, case=False, na=False)]["Total Work Done"].sum() for p in platforms],
            "Approved": [df[df["Platform"].str.contains(p, case=False, na=False)]["Approved"].sum() for p in platforms],
            "Rejected": [df[df["Platform"].str.contains(p, case=False, na=False)]["Rejected"].sum() for p in platforms],
        })
        st.bar_chart(comparison_df.set_index("Platform"))
    
    except Exception as e:
        st.error(f"An error occurred: {e}")
