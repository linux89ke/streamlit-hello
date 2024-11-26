import streamlit as st
import pandas as pd

# Title
st.title("QC Regional Weekly Review Insights")
st.write("Upload the Excel file to analyze data for Kenya and Uganda, along with rejection categories, reasons, and top rejected sellers.")

# File Upload
uploaded_file = st.file_uploader("Choose the Weekly Review Excel file", type=["xls", "xlsx"])

if uploaded_file:
    try:
        # Load the file
        raw_data = pd.read_excel(uploaded_file, sheet_name="Sheet3", header=None)
        
        # Get the dynamic weeks from the first row (assuming week data starts at column 1)
        week_columns = raw_data.iloc[0, 1:].values  # Get the week numbers
        countries = ["KE", "UG"]  # Kenya and Uganda
        platforms = ["SellerCentre", "PIM"]
        
        # Extract data for SellerCentre, PIM, and total work
        sellercentre_data = raw_data.iloc[2:5, 1:].values
        pim_data = raw_data.iloc[6:9, 1:].values
        total_data = raw_data.iloc[11:14, 1:].values

        # Build dataframes for SellerCentre, PIM, and Total Work data
        metrics = ["Approved", "Rejected", "Total"]
        dfs = []

        for platform, data in zip(platforms + ["Total"], [sellercentre_data, pim_data, total_data]):
            for i, metric in enumerate(metrics):
                for j, week in enumerate(week_columns):
                    for k, country in enumerate(countries):
                        dfs.append({
                            "Platform": platform,
                            "Week": week,
                            "Country": country,
                            "Metric": metric,
                            "Value": data[i, j * 2 + k]
                        })
        
        main_df = pd.DataFrame(dfs)
        
        # Ensure numeric values
        main_df["Value"] = pd.to_numeric(main_df["Value"], errors="coerce")
        
        # Display the restructured data
        st.subheader("Restructured Data")
        st.dataframe(main_df)

        # Insights by Platform and Country
        st.subheader("Platform and Country Insights")
        
        for platform in main_df["Platform"].unique():
            st.write(f"**{platform} Analysis**")
            platform_data = main_df[main_df["Platform"] == platform]

            for country in countries:
                country_data = platform_data[platform_data["Country"] == country]
                total_work = country_data[country_data["Metric"] == "Total"]["Value"].sum()
                approved = country_data[country_data["Metric"] == "Approved"]["Value"].sum()
                rejected = country_data[country_data["Metric"] == "Rejected"]["Value"].sum()
                
                st.write(f"**{country}**")
                st.metric(f"Total Work Done ({country})", value=int(total_work))
                st.metric(f"Approval Rate ({country})", value=f"{(approved / total_work) * 100:.2f}%" if total_work > 0 else "0%")
                st.metric(f"Rejection Rate ({country})", value=f"{(rejected / total_work) * 100:.2f}%" if total_work > 0 else "0%")
        
        # Weekly Trends
        st.subheader("Weekly Trends")
        trend_data = main_df.groupby(["Week", "Metric", "Platform"])["Value"].sum().unstack()
        st.line_chart(trend_data)

        # Extract rejection categories and reasons dynamically
        st.subheader("Dynamic Rejection Categories and Reasons")

        rejection_categories_column_start = 15  # Adjust based on file structure
        rejection_reasons_column_start = 20  # Adjust based on file structure
        top_rejected_sellers_column_start = 25  # Adjust based on file structure
        
        rejection_categories_kenya = {}
        rejection_categories_uganda = {}
        rejection_reasons_kenya = {}
        rejection_reasons_uganda = {}
        rejected_sellers_kenya = {}
        rejected_sellers_uganda = {}

        # Extract data for rejection categories
        for i, week in enumerate(week_columns):
            rejection_categories_kenya[week] = raw_data.iloc[rejection_categories_column_start + i, 1:6].dropna().values.tolist()
            rejection_categories_uganda[week] = raw_data.iloc[rejection_categories_column_start + i, 6:11].dropna().values.tolist()
        
        # Display rejection categories for each week and country
        st.write("### Rejection Categories")
        for week in week_columns:
            st.write(f"**Week {week}**")
            st.write(f"**Kenya**: {', '.join(rejection_categories_kenya.get(week, []))}")
            st.write(f"**Uganda**: {', '.join(rejection_categories_uganda.get(week, []))}")
        
        # Extract data for rejection reasons
        for i, week in enumerate(week_columns):
            rejection_reasons_kenya[week] = raw_data.iloc[rejection_reasons_column_start + i, 1:6].dropna().values.tolist()
            rejection_reasons_uganda[week] = raw_data.iloc[rejection_reasons_column_start + i, 6:11].dropna().values.tolist()
        
        # Display rejection reasons for each week and country
        st.write("### Rejection Reasons")
        for week in week_columns:
            st.write(f"**Week {week}**")
            st.write(f"**Kenya**: {', '.join(rejection_reasons_kenya.get(week, []))}")
            st.write(f"**Uganda**: {', '.join(rejection_reasons_uganda.get(week, []))}")
        
        # Extract data for top rejected sellers
        for i, week in enumerate(week_columns):
            rejected_sellers_kenya[week] = raw_data.iloc[top_rejected_sellers_column_start + i, 1:6].dropna().values.tolist()
            rejected_sellers_uganda[week] = raw_data.iloc[top_rejected_sellers_column_start + i, 6:11].dropna().values.tolist()
        
        # Display rejected sellers for each week and country
        st.write("### Top Rejected Sellers")
        for week in week_columns:
            st.write(f"**Week {week}**")
            st.write(f"**Kenya**: {', '.join(rejected_sellers_kenya.get(week, []))}")
            st.write(f"**Uganda**: {', '.join(rejected_sellers_uganda.get(week, []))}")
                
    except Exception as e:
        st.error(f"An error occurred: {e}")
