import streamlit as st
import pandas as pd


# Function to load and parse the data
def load_and_parse_data(uploaded_file):
    # Load file based on type
    if uploaded_file.name.endswith('.csv') or uploaded_file.name.endswith('.txt'):
        df = pd.read_csv(uploaded_file, sep="\t")  # Tab-separated for .csv or .txt
    elif uploaded_file.name.endswith('.xls') or uploaded_file.name.endswith('.xlsx'):
        df = pd.read_excel(uploaded_file)
    else:
        st.error("Unsupported file format! Please upload .xls, .xlsx, .csv, or .txt files.")
        return None

    # Detect week-related columns dynamically
    week_columns = [col for col in df.columns if "Week" in col]

    # Reshape data into a long format
    reshaped_df = df.melt(id_vars=["Section", "Metric"],
                          value_vars=week_columns,
                          var_name="Week_Country",
                          value_name="Value")

    # Extract week and country from 'Week_Country'
    reshaped_df[['Week', 'Country']] = reshaped_df['Week_Country'].str.extract(r'(Week \d+)\s+(KE|UG)')
    reshaped_df.drop(columns=["Week_Country"], inplace=True)

    return reshaped_df


# Streamlit App
st.title("Dynamic Weekly Product Rejection Insights")

# File upload
uploaded_file = st.file_uploader("Upload your data file (.xls, .xlsx, .csv, or .txt)", type=['xls', 'xlsx', 'csv', 'txt'])

if uploaded_file:
    # Load and parse the data
    data = load_and_parse_data(uploaded_file)

    if data is not None:
        # Display the reshaped dataset
        st.subheader("Parsed Dataset")
        st.dataframe(data)

        # Extract unique weeks, sections, and metrics
        unique_weeks = data["Week"].unique()
        unique_sections = data["Section"].unique()
        unique_metrics = data["Metric"].unique()

        # User inputs for dynamic selection
        selected_week = st.selectbox("Select Week", unique_weeks)
        selected_section = st.selectbox("Select Section", unique_sections)
        selected_metric = st.selectbox("Select Metric", unique_metrics)

        # Filter data based on user selections
        filtered_data = data[(data["Week"] == selected_week) &
                             (data["Section"] == selected_section) &
                             (data["Metric"] == selected_metric)]

        st.subheader(f"Insights for {selected_week} - {selected_section} - {selected_metric}")
        if not filtered_data.empty:
            # Display insights for each country
            for country in filtered_data["Country"].unique():
                country_data = filtered_data[filtered_data["Country"] == country]
                value = country_data["Value"].sum()
                st.write(f"**{country}: {value}**")
        else:
            st.write("No data available for the selected filters.")

        # Visualization
        st.subheader("Visualization")
        if not filtered_data.empty:
            chart_data = filtered_data.pivot(index="Country", columns="Metric", values="Value").reset_index()
            st.bar_chart(chart_data.set_index("Country"))
