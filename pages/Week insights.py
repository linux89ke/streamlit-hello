import streamlit as st
import pandas as pd

# Title
st.title("QC Regional Weekly Review Insights")
st.write("Upload the Excel file to analyze data for Kenya and Uganda.")

# File Upload
uploaded_file = st.file_uploader("Choose the Weekly Review Excel file", type=["xls", "xlsx"])

if uploaded_file:
    try:
        # Load the file
        raw_data = pd.read_excel(uploaded_file, sheet_name="Sheet3", header=None)
        
        # Extract week and country information
        weeks = raw_data.iloc[0, 1:].values  # Week numbers
        countries = raw_data.iloc[1, 1:].values  # Country identifiers (KE, UG)
        
        # Extract metric labels and values
        metrics = raw_data.iloc[2:, 0].values  # Approved, Rejected, Total
        values = raw_data.iloc[2:, 1:].values  # Numeric values
        
        # Restructure data into a tidy format
        tidy_data = []
        for metric_idx, metric in enumerate(metrics):
            for col_idx, week in enumerate(weeks):
                tidy_data.append({
                    "Week": week,
                    "Country": countries[col_idx],
                    "Metric": metric,
                    "Value": values[metric_idx, col_idx]
                })
        
        df = pd.DataFrame(tidy_data)
        df["Value"] = pd.to_numeric(df["Value"], errors="coerce")  # Ensure numeric values
        
        # Show the tidy dataframe
        st.subheader("Restructured Data")
        st.dataframe(df)
        
        # Insights
        st.subheader("Insights and Metrics")
        
        # Compute overall totals
        total_approved = df[df["Metric"] == "Approved"]["Value"].sum()
        total_rejected = df[df["Metric"] == "Rejected"]["Value"].sum()
        total_work = df[df["Metric"] == "Total"]["Value"].sum()
        
        st.metric("Total Work Done", value=int(total_work))
        st.metric("Approval Rate", value=f"{(total_approved / total_work) * 100:.2f}%" if total_work > 0 else "0%")
        st.metric("Rejection Rate", value=f"{(total_rejected / total_work) * 100:.2f}%" if total_work > 0 else "0%")
        
        # Weekly trends
        st.subheader("Weekly Trends")
        weekly_data = df.groupby(["Week", "Metric"])["Value"].sum().unstack()
        st.line_chart(weekly_data)
        
        # Country-specific analysis
        st.subheader("Country Analysis")
        countries = df["Country"].unique()
        for country in countries:
            country_data = df[df["Country"] == country]
            approved = country_data[country_data["Metric"] == "Approved"]["Value"].sum()
            rejected = country_data[country_data["Metric"] == "Rejected"]["Value"].sum()
            total = country_data[country_data["Metric"] == "Total"]["Value"].sum()
            
            st.write(f"**{country}**")
            st.metric(f"Total Work Done ({country})", value=int(total))
            st.metric(f"Approval Rate ({country})", value=f"{(approved / total) * 100:.2f}%" if total > 0 else "0%")
            st.metric(f"Rejection Rate ({country})", value=f"{(rejected / total) * 100:.2f}%" if total > 0 else "0%")
        
    except Exception as e:
        st.error(f"An error occurred: {e}")
