import streamlit as st
import pandas as pd

# Title and File Upload
st.title("QC Regional Weekly Review Analysis")
st.write("Upload the Excel file to begin.")

# Upload Section
uploaded_file = st.file_uploader("Choose the Weekly Review Excel file", type=["xls", "xlsx"])

if uploaded_file:
    # Load the Excel file
    try:
        # Load all sheets from the Excel file
        data = pd.read_excel(uploaded_file, sheet_name=None)  # Dictionary of sheets
        st.success("File uploaded successfully!")
        
        # Display sheet selection
        sheet_names = list(data.keys())
        selected_sheet = st.selectbox("Select a sheet to analyze:", sheet_names)
        
        # Load selected sheet
        df = data[selected_sheet]
        st.write(f"Preview of the `{selected_sheet}` sheet:")
        st.dataframe(df.head())  # Display first few rows
        
        # Convert column names to strings to handle mixed types
        df.columns = df.columns.map(str)
        
        # Dynamic Week Analysis
        st.subheader("Dynamic Week Analysis")
        
        # Extract and identify week-related columns
        week_columns = [col for col in df.columns if "Week" in col or col.startswith("W")]
        st.write("Identified Week Columns:", week_columns)
        
        if week_columns:
            # Ensure week columns contain numerical data
            week_data = df[week_columns].apply(pd.to_numeric, errors='coerce')
            
            # Example Calculation: Weekly Totals
            st.write("Performing Example Calculation...")
            weekly_totals = week_data.sum()
            st.bar_chart(weekly_totals)
            
            # Display Calculations
            st.write("Weekly Totals:")
            st.write(weekly_totals)
            
            # User-Defined Analysis (if needed)
            st.write("Select a column for additional analysis:")
            selected_col = st.selectbox("Select a column:", df.columns)
            
            if selected_col:
                st.write(f"Summary of `{selected_col}`:")
                st.write(df[selected_col].describe())
        else:
            st.warning("No week-related columns were found.")
    
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")

# Footer
st.write("Developed with ❤️ using Streamlit.")
