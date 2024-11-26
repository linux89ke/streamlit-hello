import streamlit as st
import pandas as pd

# Title
st.title("QC Regional Weekly Review Insights")
st.write("Upload the Weekly Review file to analyze data for Kenya and Uganda, including rejection categories, rejection reasons, and top rejected sellers.")

# File Upload
uploaded_file = st.file_uploader("Choose the Weekly Review Excel file", type=["xls", "xlsx"])

if uploaded_file:
    try:
        # Load the file
        raw_data = pd.read_excel(uploaded_file, sheet_name="Sheet3", header=None)
        
        # Get dynamic weeks (from the first row of the file)
        week_columns = raw_data.iloc[0, 1:].values  # Week numbers
        countries = ["KE", "UG"]
        platforms = ["SellerCentre", "PIM"]
        
        # Extract platform and work data for SellerCentre, PIM, and total work
        sellercentre_data = raw_data.iloc[2:5, 1:].values
        pim_data = raw_data.iloc[6:9, 1:].values
        total_data = raw_data.iloc[11:14, 1:].values

        # Build main dataframes
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

        # Ensure values are numeric
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

        # Dynamic Rejection Categories (Week-by-Week Data)
        st.subheader("Top Rejection Categories (Week-by-Week)")
        rejection_categories = {}
        
        # Rejection categories are based on data from another part of the file, assume we extract them from rows 15-18 (example)
        for week in week_columns:
            rejection_categories[week] = {
                "Kenya": raw_data.iloc[15:20, 1].values.tolist(),  # Adjust to actual row positions in your file
                "Uganda": raw_data.iloc[15:20, 2].values.tolist()  # Adjust to actual row positions in your file
            }

        for week, data in rejection_categories.items():
            st.write(f"**Week {week}**")
            for country, categories in data.items():
                st.write(f"**{country}**: {', '.join(categories)}")
        
        # Dynamic Rejection Reasons (Week-by-Week Data)
        st.subheader("Top Rejection Reasons (Week-by-Week)")
        rejection_reasons = {}

        # Rejection reasons can be in another part of the sheet, adjust row positions
        for week in week_columns:
            rejection_reasons[week] = {
                "Kenya": raw_data.iloc[20:25, 1].values.tolist(),  # Adjust row index as needed
                "Uganda": raw_data.iloc[20:25, 2].values.tolist()  # Adjust row index as needed
            }

        for week, data in rejection_reasons.items():
            st.write(f"**Week {week}**")
            for country, reasons in data.items():
                st.write(f"**{country}**: {', '.join(reasons)}")
        
        # Dynamic Top Rejected Sellers (Week-by-Week Data)
        st.subheader("Top Rejected Sellers (Week-by-Week)")
        rejected_sellers = {}

        # Sellers info will come from another part of the sheet
        for week in week_columns:
            rejected_sellers[week] = {
                "Kenya": raw_data.iloc[25:30, 1].values.tolist(),  # Adjust row index as needed
                "Uganda": raw_data.iloc[25:30, 2].values.tolist()  # Adjust row index as needed
            }

        for week, data in rejected_sellers.items():
            st.write(f"**Week {week}**")
            for country, sellers in data.items():
                st.write(f"**{country}**: {', '.join(sellers)}")
                
    except Exception as e:
        st.error(f"An error occurred: {e}")
