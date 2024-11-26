import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Function to load data
def load_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

# Extract week-related columns dynamically
def extract_weeks(columns):
    return [col for col in columns if "Week" in col]

# Function to generate insights for a specific week
def calculate_week_insights(data, week_prefix, country):
    approved_col = f"{week_prefix} {country} Approved"
    rejected_col = f"{week_prefix} {country} Rejected"
    if approved_col in data.columns and rejected_col in data.columns:
        approved = data[approved_col].iloc[0]
        rejected = data[rejected_col].iloc[0]
        total = approved + rejected
        approval_rate = (approved / total) * 100 if total > 0 else 0
        rejection_rate = (rejected / total) * 100 if total > 0 else 0
        return approved, rejected, total, approval_rate, rejection_rate
    else:
        return 0, 0, 0, 0, 0

# Streamlit UI
st.title("Dynamic Weekly Product Rejection Insights")

# File upload
uploaded_file = st.file_uploader("Upload your weekly data file", type=['csv', 'xlsx'])

if uploaded_file:
    # Load data
    data = load_data(uploaded_file)
    st.dataframe(data)  # Display data
    
    # Extract week-related columns
    week_columns = extract_weeks(data.columns)
    weeks = sorted(set(col.split()[0] for col in week_columns))  # Extract unique week numbers
    
    # Dynamic week selection
    st.subheader("Select Weeks and Countries")
    selected_week = st.selectbox("Choose a Week", weeks)
    countries = ["KE", "UG"]
    selected_country = st.radio("Choose a Country", countries)
    
    # Calculate insights for the selected week and country
    approved, rejected, total, approval_rate, rejection_rate = calculate_week_insights(data, selected_week, selected_country)
    
    # Display insights
    st.subheader(f"Insights for {selected_week} - {selected_country}")
    st.write(f"**Approved:** {approved}")
    st.write(f"**Rejected:** {rejected}")
    st.write(f"**Total Work Done:** {total}")
    st.write(f"**Approval Rate:** {approval_rate:.2f}%")
    st.write(f"**Rejection Rate:** {rejection_rate:.2f}%")
    
    # Visualizations for rejection reasons
    st.subheader("Rejection Reasons Breakdown")
    rejection_reasons = data['Rejection Reasons'].value_counts()
    rejection_reasons_chart = rejection_reasons.plot(kind='bar', title='Rejection Reasons', figsize=(10, 6), color='skyblue')
    plt.xlabel('Rejection Reason')
    plt.ylabel('Count')
    st.pyplot(rejection_reasons_chart.figure)
    
    # Report generation (optional)
    st.subheader("Download Insights Report")
    if st.button("Generate Report"):
        report_path = "Dynamic_Insights_Report.xlsx"
        with pd.ExcelWriter(report_path, engine='xlsxwriter') as writer:
            data.to_excel(writer, sheet_name='Data', index=False)
        st.success("Report generated successfully!")
        st.download_button("Download Report", report_path, file_name="Dynamic_Insights_Report.xlsx")

