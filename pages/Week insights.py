import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Function to load and parse the data
def load_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

# Function to calculate insights
def generate_insights(data):
    # Calculate totals and rejection percentages
    total_approved_ke = data['Approved'].iloc[0]
    total_rejected_ke = data['Rejected'].iloc[0]
    total_entries_ke = total_approved_ke + total_rejected_ke
    approval_rate_ke = (total_approved_ke / total_entries_ke) * 100
    rejection_rate_ke = (total_rejected_ke / total_entries_ke) * 100

    total_approved_ug = data['Approved'].iloc[1]
    total_rejected_ug = data['Rejected'].iloc[1]
    total_entries_ug = total_approved_ug + total_rejected_ug
    approval_rate_ug = (total_approved_ug / total_entries_ug) * 100
    rejection_rate_ug = (total_rejected_ug / total_entries_ug) * 100

    # Rejections due to color
    color_rejections_ke = data['Rejection Reasons'].str.contains('color', case=False).sum()
    color_rejection_rate_ke = (color_rejections_ke / total_rejected_ke) * 100 if total_rejected_ke > 0 else 0

    color_rejections_ug = data['Rejection Reasons'].str.contains('color', case=False).sum()
    color_rejection_rate_ug = (color_rejections_ug / total_rejected_ug) * 100 if total_rejected_ug > 0 else 0

    # Rejection Reasons Breakdown
    rejection_reasons_ke = data['Rejection Reasons'].value_counts()
    rejection_reasons_ug = data['Rejection Reasons'].value_counts()

    # Top rejected categories
    top_categories_ke = data.groupby('Category')['Rejected'].sum().sort_values(ascending=False).head(5)
    top_categories_ug = data.groupby('Category')['Rejected'].sum().sort_values(ascending=False).head(5)

    return (approval_rate_ke, rejection_rate_ke, color_rejection_rate_ke,
            approval_rate_ug, rejection_rate_ug, color_rejection_rate_ug,
            rejection_reasons_ke, rejection_reasons_ug, top_categories_ke, top_categories_ug)

# Streamlit UI
st.title("Weekly Product Rejection Insights")

# File upload
uploaded_file = st.file_uploader("Upload your weekly data file", type=['csv', 'xlsx'])

if uploaded_file:
    # Load the data
    data = load_data(uploaded_file)

    st.dataframe(data)  # Display the uploaded data

    # Generate insights
    (approval_rate_ke, rejection_rate_ke, color_rejection_rate_ke,
     approval_rate_ug, rejection_rate_ug, color_rejection_rate_ug,
     rejection_reasons_ke, rejection_reasons_ug,
     top_categories_ke, top_categories_ug) = generate_insights(data)

    # Display summary statistics for both Kenya and Uganda
    st.subheader("Summary Statistics")
    st.write(f"**Kenya - Approval Rate:** {approval_rate_ke:.2f}%")
    st.write(f"**Kenya - Rejection Rate:** {rejection_rate_ke:.2f}%")
    st.write(f"**Kenya - Rejections due to Missing/Incorrect Color:** {color_rejection_rate_ke:.2f}%")

    st.write(f"**Uganda - Approval Rate:** {approval_rate_ug:.2f}%")
    st.write(f"**Uganda - Rejection Rate:** {rejection_rate_ug:.2f}%")
    st.write(f"**Uganda - Rejections due to Missing/Incorrect Color:** {color_rejection_rate_ug:.2f}%")

    # Rejection Reasons Breakdown - Bar chart using matplotlib
    st.subheader("Rejection Reasons Breakdown (Kenya)")
    rejection_reasons_chart_ke = rejection_reasons_ke.plot(kind='bar', title='Rejection Reasons (Kenya)', figsize=(10, 6), color='skyblue')
    plt.xlabel('Rejection Reason')
    plt.ylabel('Count')
    st.pyplot(rejection_reasons_chart_ke.figure)

    st.subheader("Rejection Reasons Breakdown (Uganda)")
    rejection_reasons_chart_ug = rejection_reasons_ug.plot(kind='bar', title='Rejection Reasons (Uganda)', figsize=(10, 6), color='lightcoral')
    plt.xlabel('Rejection Reason')
    plt.ylabel('Count')
    st.pyplot(rejection_reasons_chart_ug.figure)

    # Top rejected categories - Bar chart using matplotlib
    st.subheader("Top Rejected Categories (Kenya)")
    top_categories_chart_ke = top_categories_ke.plot(kind='bar', title='Top Rejected Categories (Kenya)', figsize=(10, 6), color='lightgreen')
    plt.xlabel('Category')
    plt.ylabel('Rejected Products')
    st.pyplot(top_categories_chart_ke.figure)

    st.subheader("Top Rejected Categories (Uganda)")
    top_categories_chart_ug = top_categories_ug.plot(kind='bar', title='Top Rejected Categories (Uganda)', figsize=(10, 6), color='orange')
    plt.xlabel('Category')
    plt.ylabel('Rejected Products')
    st.pyplot(top_categories_chart_ug.figure)

    # Generate downloadable report
    st.subheader("Download Insights Report")
    def generate_report(data, rejection_reasons_ke, rejection_reasons_ug, top_categories_ke, top_categories_ug):
        with pd.ExcelWriter('Insights_Report.xlsx', engine='xlsxwriter') as writer:
            data.to_excel(writer, sheet_name='Data', index=False)
            rejection_reasons_ke.to_excel(writer, sheet_name='Rejection Reasons (Kenya)', index=True)
            rejection_reasons_ug.to_excel(writer, sheet_name='Rejection Reasons (Uganda)', index=True)
            top_categories_ke.to_excel(writer, sheet_name='Top Categories (Kenya)', index=True)
            top_categories_ug.to_excel(writer, sheet_name='Top Categories (Uganda)', index=True)
        return 'Insights_Report.xlsx'

    if st.button("Generate Report"):
        report_path = generate_report(data, rejection_reasons_ke, rejection_reasons_ug, top_categories_ke, top_categories_ug)
        st.success(f"Report generated: {report_path}")
        st.download_button("Download Report", report_path, file_name="Insights_Report.xlsx")
