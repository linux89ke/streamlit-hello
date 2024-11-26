import streamlit as st
import pandas as pd


# Custom function to parse raw data
def parse_and_reshape_data(raw_data):
    # Load raw data
    df = pd.read_csv(raw_data, sep="\t")  # Assumes tab-separated data
    
    # Detect week columns dynamically
    week_columns = [col for col in df.columns if "Week" in col]
    
    # Reshape the data into a long format for easier processing
    reshaped_df = df.melt(id_vars=["Section", "Metric"], 
                          value_vars=week_columns, 
                          var_name="Week_Country", 
                          value_name="Value")
    
    # Extract week and country from the 'Week_Country' column
    reshaped_df[['Week', 'Country']] = reshaped_df['Week_Country'].str.extract(r'(Week \d+)\s+(KE|UG)')
    reshaped_df.drop(columns=["Week_Country"], inplace=True)
    
    # Return the reshaped DataFrame
    return reshaped_df


# Streamlit App
st.title("Dynamic Weekly Product Rejection Insights")

# File upload
uploaded_file = st.file_uploader("Upload your weekly data file (tab-separated)", type=['csv', 'txt'])

if uploaded_file:
    # Parse the data
    data = parse_and_reshape_data(uploaded_file)
    
    st.subheader("Uploaded Dataset")
    st.dataframe(data)
    
    # Extract unique weeks and metrics
    unique_weeks = data["Week"].unique()
    unique_metrics = data["Metric"].unique()
    unique_sections = data["Section"].unique()
    
    # User inputs for selection
    selected_week = st.selectbox("Select Week", unique_weeks)
    selected_section = st.selectbox("Select Section", unique_sections)
    selected_metric = st.selectbox("Select Metric", unique_metrics)
    
    # Filter data based on selections
    filtered_data = data[(data["Week"] == selected_week) & 
                         (data["Section"] == selected_section) & 
                         (data["Metric"] == selected_metric)]
    
    st.subheader(f"Insights for {selected_week} - {selected_section} - {selected_metric}")
    if not filtered_data.empty:
        # Display insights
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
