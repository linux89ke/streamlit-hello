import streamlit as st
import streamlit_authenticator as stauth
import os
from dotenv import load_dotenv
import pandas as pd
from io import BytesIO
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Streamlit Authentication
st.title("Product Validation Tool")

# Set up the credentials for authentication
try:
    # Fetch environment variables
    usernames = os.getenv('ST_AUTH_USERNAMES', 'user1,user2').split(',')
    passwords = os.getenv('ST_AUTH_PASSWORDS', 'password1,password2').split(',')
    names = os.getenv('ST_AUTH_NAMES', 'User One,User Two').split(',')

    # Debugging: Check environment variables
    st.write("Usernames:", usernames)
    st.write("Passwords:", passwords)
    st.write("Names:", names)

    # Ensure passwords are loaded and not empty
    if not passwords:
        st.error("No passwords found in environment variables. Please set them properly.")
        st.stop()

    # Hash the passwords using streamlit-authenticator's Hasher class
    # The Hasher expects a list of passwords
    hashed_passwords = stauth.Hasher(passwords).generate()

    # Authenticate users
    authenticator = stauth.Authenticate(
        usernames,
        names,
        hashed_passwords,
        cookie_name="product_validation_cookie",
        key="my_secret_key",
        cookie_expiry_days=30,
    )

    # Check if the user is authenticated
    name, authentication_status = authenticator.login("Login", "main")

    if authentication_status:
        st.write(f"Welcome {name}!")
    elif authentication_status is False:
        st.error("Username or password is incorrect.")
        st.stop()
    elif authentication_status is None:
        st.warning("Please enter your username and password.")
        st.stop()

except Exception as e:
    st.error(f"Error in authentication setup: {e}")
    st.stop()

# If authenticated, load the product validation functionality
if authentication_status:
    # Function to load blacklisted words from a file
    @st.cache_data
    def load_blacklisted_words():
        try:
            with open('blacklisted.txt', 'r') as f:
                return [line.strip() for line in f.readlines()]
        except FileNotFoundError:
            st.error("blacklisted.txt file not found!")
            return []
        except Exception as e:
            st.error(f"Error loading blacklisted words: {e}")
            return []

    # Load blacklisted words
    blacklisted_words = load_blacklisted_words()

    # File upload section
    uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

    # Process uploaded file
    if uploaded_file is not None:
        try:
            data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
            
            if data.empty:
                st.warning("The uploaded file is empty.")
                st.stop()

            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Validation checks
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            
            # Example of displaying issues
            if not missing_color.empty:
                st.write(f"Missing COLOR in {len(missing_color)} products")
            if not missing_brand_or_name.empty:
                st.write(f"Missing BRAND or NAME in {len(missing_brand_or_name)} products")
            if not single_word_name.empty:
                st.write(f"Single-word NAME in {len(single_word_name)} products")

            # Export function for CSV download
            @st.cache_data
            def convert_df_to_csv(df):
                return df.to_csv(index=False).encode('utf-8')

            # Convert data to CSV and prepare the download button
            csv_data = convert_df_to_csv(data)
            st.download_button(
                label="Download Validation Report",
                data=csv_data,
                file_name="validation_report.csv",
                mime="text/csv"
            )

        except Exception as e:
            st.error(f"Error processing file: {e}")
