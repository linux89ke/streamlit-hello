import streamlit as st
import pandas as pd

# Function to parse the pasted data (tab-separated format)
def parse_pasted_data(raw_data):
    try:
        # Read the pasted data as a CSV-like structure
        data = pd.read_csv(StringIO(raw_data), sep="\t")
        return data
    except Exception as e:
        st.error(f"Error parsing data: {e}")
        return None

# Streamlit App
st.title("Weekly Product Rejection Insights (Current and Previous Week)")

# User inputs for the country selection
selected_country = st.selectbox("Select Country", ["KE", "UG"])

# Instructions for the user to paste the data for both weeks (current and previous)
st.subheader("Paste Data for the Current Week and Previous Week")
st.write("Please copy and paste the data from Excel into the text areas below. Ensure data is tab-separated.")

# Text areas for current week and previous week data
current_week_data = st.text_area(
    "Paste Current Week Data",
    height=200,
    placeholder="Paste data for current week here (tab-separated)"
)

previous_week_data = st.text_area(
    "Paste Previous Week Data",
    height=200,
    placeholder="Paste data for previous week here (tab-separated)"
)

# If both current and previous week data are provided, process the data
if current_week_data.strip() and previous_week_data.strip():
    # Parse both weeks' data
    current_week_df = parse_pasted_data(current_week_data)
    previous_week_df = parse_pasted_data(previous_week_data)

    # Check if both datasets are successfully parsed
    if current_week_df is not None and previous_week_df is not None:
        # Add a 'Week' column to each dataframe
        current_week_df['Week'] = 'Current Week'
        previous_week_df['Week'] = 'Previous Week'

        # Combine the two dataframes (stack them)
        combined_df = pd.concat([current_week_df, previous_week_df], ignore_index=True)

        # Filter by the selected country
        country_data = combined_df[combined_df["Country"] == selected_country]

        # Display the combined data
        st.subheader(f"Data for {selected_country} (Current Week and Previous Week)")
        st.dataframe(country_data)

        # Insights for each metric (e.g., Approved, Rejected, Total)
        st.subheader("Insights")
        metrics = country_data["Metric"].unique()

        for metric in metrics:
            metric_data = country_data[country_data["Metric"] == metric]
            if len(metric_data) == 2:  # Ensure there are data points for both weeks
                current_value = metric_data[metric_data["Week"] == "Current Week"]["Value"].values[0]
                previous_value = metric_data[metric_data["Week"] == "Previous Week"]["Value"].values[0]

                change = current_value - previous_value
                change_percentage = (change / previous_value) * 100 if previous_value != 0 else 0

                st.write(f"**{metric}**:")
                st.write(f"Current Week: {current_value}")
                st.write(f"Previous Week: {previous_value}")
                st.write(f"Change: {change} ({change_percentage:.2f}%)")
                st.write("---")
            else:
                st.write(f"**{metric}**: Missing data for one of the weeks.")
                st.write("---")

        # Visualization: Comparison of metrics between weeks
        st.subheader("Visualization: Current vs Previous Week")
        if not country_data.empty:
            chart_data = country_data.pivot(index="Metric", columns="Week", values="Value").reset_index()
            st.bar_chart(chart_data.set_index("Metric"))
    else:
        st.error("Error parsing data for current or previous week.")
