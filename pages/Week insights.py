import streamlit as st
import pandas as pd


# Function to load and parse the data
def load_and_parse_data(uploaded_file):
    # Load file based on type
    if uploaded_file.name.endswith('.csv') or uploaded_file.name.endswith('.txt'):
        df = pd.read_csv(uploaded_file, sep="\t")
    elif uploaded_file.name.endswith('.xls') or uploaded_file.name.endswith('.xlsx'):
        df = pd.read_excel(uploaded_file)
    else:
        st.error("Unsupported file format! Please upload .xls, .xlsx, .csv, or .txt files.")
        return None

    # Display dataset columns for debugging
    st.write("Columns in the dataset:", df.columns.tolist())

    # Detect week-related columns dynamically
    week_columns = [col for col in df.columns if "Week" in col]

    if not week_columns:
        st.error("No columns found for weeks (e.g., 'Week 46 KE'). Please check the dataset format.")
        return None

    # Handle datasets without "Section" or "Metric" columns
    if "Section" in df.columns and "Metric" in df.columns:
        id_vars = ["Section", "Metric"]
    else:
        id_vars = []  # No id_vars if the dataset lacks these columns

    # Reshape data into a long format
    reshaped_df = df.melt(
        id_vars=id_vars,
        value_vars=week_columns,
        var_name="Week_Country",
        value_name="Value"
    )

    # Extract week and country from 'Week_Country'
    reshaped_df[['Week', 'Country']] = reshaped_df['Week_Country'].str.extract(r'(Week \d+)\s+(KE|UG)')
    reshaped_df.drop(columns=["Week_Country"], inplace=True)

    # Display reshaped data for debugging
    st.write("Reshaped Dataset:", reshaped_df.head())

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
        unique_weeks = data["Week"].dropna().unique()
        unique_countries = data["Country"].dropna().unique()
        unique_metrics = data["Metric"].dropna().unique() if "Metric" in data.columns else None
        unique_sections = data["Section"].dropna().unique() if "Section" in data.columns else None

        # Debugging step: Display the unique weeks, countries, metrics, and sections
        st.write(f"Unique Weeks: {unique_weeks}")
        st.write(f"Unique Countries: {unique_countries}")
        st.write(f"Unique Metrics: {unique_metrics}")
        st.write(f"Unique Sections: {unique_sections}")

        # User inputs for dynamic selection
        selected_week = st.selectbox("Select Week", unique_weeks)
        selected_country = st.selectbox("Select Country", unique_countries)

        if unique_sections is not None:
            selected_section = st.selectbox("Select Section", unique_sections)
        else:
            selected_section = None

        if unique_metrics is not None:
            selected_metric = st.selectbox("Select Metric", unique_metrics)
        else:
            selected_metric = None

        # Filter data based on user selections
        filtered_data = data[
            (data["Week"] == selected_week) &
            (data["Country"] == selected_country)
        ]
        if selected_section:
            filtered_data = filtered_data[filtered_data["Section"] == selected_section]
        if selected_metric:
            filtered_data = filtered_data[filtered_data["Metric"] == selected_metric]

        # Display insights
        st.subheader(f"Insights for {selected_week} - {selected_country}")
        if not filtered_data.empty:
            total_value = filtered_data["Value"].sum()
            st.write(f"**Total Value:** {total_value}")
        else:
            st.write("No data available for the selected filters.")

        # Visualization
        st.subheader("Visualization")
        if not filtered_data.empty:
            chart_data = filtered_data.pivot(index="Country", columns="Metric", values="Value").reset_index()
            st.bar_chart(chart_data.set_index("Country"))
