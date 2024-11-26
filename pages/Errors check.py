import streamlit as st
import pandas as pd
from io import BytesIO

# Custom CSS to style the file uploader background colors
st.markdown(
    """
    <style>
    .file-uploader1 {
        background-color: #FFDDC1;  /* Light orange */
        padding: 10px;
        border-radius: 5px;
    }
    .file-uploader2 {
        background-color: #D1E7FF;  /* Light blue */
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title('Erro Files Check')

# Function to load data from uploaded files
def load_data(file):
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    elif file.name.endswith('.xlsx'):
        return pd.read_excel(file)
    else:
        return None

# File uploaders for the first and second set of files with custom CSS classes
st.markdown('<div class="file-uploader1">', unsafe_allow_html=True)
uploaded_files_1 = st.file_uploader("Choose the set of error files (CSV or XLSX)", type=["csv", "xlsx"], accept_multiple_files=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="file-uploader2">', unsafe_allow_html=True)
uploaded_file_2 = st.file_uploader("Choose the PIM file (CSV or XLSX)", type=["csv", "xlsx"])
st.markdown('</div>', unsafe_allow_html=True)

if uploaded_files_1 and uploaded_file_2:
    # Read the second file
    df2 = load_data(uploaded_file_2)
    
    # Check if the necessary columns exist in the second file
    if df2 is not None and 'PRODUCT_SET_SID' in df2.columns and 'SELLER_NAME' in df2.columns and 'CATEGORY' in df2.columns:
        # Initialize an empty list to store merged dataframes
        merged_dfs = []
        
        # Iterate over each file in the first set
        for uploaded_file_1 in uploaded_files_1:
            df1 = load_data(uploaded_file_1)

            # Check if the necessary columns exist in the first file
            if df1 is not None and 'ProductSetSid' in df1.columns:
                # Merge the two dataframes on 'ProductSetSid' from df1 and 'PRODUCT_SET_SID' from df2
                df1.rename(columns={'ProductSetSid': 'PRODUCT_SET_SID'}, inplace=True)
                merged_df = pd.merge(df1, df2[['PRODUCT_SET_SID', 'SELLER_NAME', 'CATEGORY']], on='PRODUCT_SET_SID', how='left')
                
                # Add the merged dataframe to the list
                merged_dfs.append(merged_df)
            else:
                st.error(f"One or more files could not be read or the necessary columns are not present in {uploaded_file_1.name}.")
        
        # Concatenate all merged dataframes
        result_df = pd.concat(merged_dfs, ignore_index=True)
        
        st.write("Result of VLOOKUP:")
        st.dataframe(result_df)
        
        # Option to download the result as an XLSX file
        output = BytesIO()
        result_df.to_excel(output, index=False, sheet_name='Sheet1')  # Save directly to BytesIO object
        
        output.seek(0)
        
        st.download_button(
            label="Download result as XLSX",
            data=output,
            file_name='vlookup_result.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    else:
        st.error("The necessary columns are not present in the second file.")
else:
    st.info("Please upload both files.")
