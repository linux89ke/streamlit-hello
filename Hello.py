import os
import streamlit as st
import streamlit_authenticator as stauth

# Fetch the environment variables
usernames = os.getenv('ST_AUTH_USERNAMES', 'user1,user2').split(',')
passwords = os.getenv('ST_AUTH_PASSWORDS', 'password1,password2').split(',')
names = os.getenv('ST_AUTH_NAMES', 'User One,User Two').split(',')

# Proceed with hashing and authentication
hashed_passwords = stauth.Hasher(passwords).generate()

# Use Streamlit-Authenticator for authentication
authenticator = stauth.Authenticate(
    usernames,
    names,
    hashed_passwords,
    cookie_name="product_validation_cookie",
    key="my_secret_key",
    cookie_expiry_days=30,
)

name, authentication_status = authenticator.login("Login", "main")

if authentication_status:
    st.write(f"Welcome {name}!")
elif authentication_status is False:
    st.error("Username or password is incorrect.")
elif authentication_status is None:
    st.warning("Please enter your username and password.")
