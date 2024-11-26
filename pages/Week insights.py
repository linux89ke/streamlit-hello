import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px

# Function to load the data
def load_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

# Function to generate insights
def generate_insights(data):
    # Summary of approvals and rejections
    total_approved = data[data['Approved'] == 'Yes'].shape[0]
    total_rejected = data[data['Approved'] == 'No'].shape[0]
    total_entries = total_approved + total_rejected
    approval_rate = (total_approved / total_entries) * 100
    rejection_rate = (total_rejected / total_entries) * 100

    # Rejections due to color
    color_rejections = data[data['Rejection Reason'] == 'Missing/Incorrect Color'].shape[0]
    color_rejection_rate = (color_rejections / total_rejected) * 100 if total_rejected > 0 else 0

    # Rejection reasons breakdown
    rejection_reasons = data.groupby('Rejection Reason')['Approved'].count()

    # Top rejected categories
    top_categories = data.groupby('Category')['Approved'].count().sort_values(ascending=False).head(5)

    return total_approved, total_rejected, total_entries, approval_rate, rejection_rate, color_rejection_rate, rejection_reasons, top_categories

# Function to generate a report
def generate_report(data, rejection_reasons, top_categories):
    with pd.ExcelWriter('Insights_Report.xlsx', engine='xlsxwriter') as writer:
        data.to_excel(writer, sheet_name='Data', index=False)
        rejection_reasons.to_excel(writer, sheet_name='Rejection Reasons', index=True)
        top_categories.to_excel(writer, sheet_name='Top Categories', index=True)
    return 'Insights_Report.xlsx'

# Streamlit UI
st.title("Weekly Product Rejection Insights")

# File upload
uploaded_file = st.file_uploader("Upload your weekly data file", type=['csv', 'xlsx'])

if uploaded_file:
    # Load and display the data
    data = load_data(uploaded_file)
    st.dataframe(data)

    # Generate insights
    total_approved, total_rejected, total_entries, approval_rate, rejection_rate, color_rejection_rate, rejection_reasons, top_categories = generate_insights(data)

    # Display summary statistics
    st.subheader("Summary Statistics")
    st.write(f"**Total Approved:** {total_approved}")
    st.write(f"**Total Rejected:** {total_rejected}")
    st.write(f"**Approval Rate:** {approval_rate:.2f}%")
    st.write(f"**Rejection Rate:** {rejection_rate:.2f}%")
    st.write(f"**Rejections due to Missing/Incorrect Color:** {color_rejection_rate:.2f}%")

    # Rejection reasons breakdown - Bar chart
    st.subheader("Rejection Reasons Breakdown")
    rejection_reasons_chart = rejection_reasons.plot(kind='bar', title='Rejection Reasons', figsize=(10, 6), color='skyblue')
    plt.xlabel('Rejection Reason')
    plt.ylabel('Count')
    st.pyplot(rejection_reasons_chart.figure)

    # Top rejected categories - Bar chart
    st.subheader("Top Rejected Categories")
    top_categories_chart = top_categories.plot(kind='bar', title='Top Rejected Categories', figsize=(10, 6), color='lightcoral')
    plt.xlabel('Category')
    plt.ylabel('Count')
    st.pyplot(top_categories_chart.figure)

    # Generate downloadable report
    st.subheader("Download Insights Report")
    if st.button("Generate Report"):
        report_path = generate_report(data, rejection_reasons, top_categories)
        st.success(f"Report generated: {report_path}")
        st.download_button("Download Report", report_path, file_name="Insights_Report.xlsx")
