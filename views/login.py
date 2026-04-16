import streamlit as st
import hashlib
import pandas as pd

# Import the new database functions
from gsheets_db import get_user_database, create_new_user_sheet, register_user_in_db

# Basic security hashing for passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

st.title("🔒 Manager Portal")

# Setup Tabs for Login and Register
tab_login, tab_register = st.tabs(["Login", "Register New User"])

# --- LOGIN TAB ---
with tab_login:
    st.subheader("Login to your account")
    log_user = st.text_input("Username", key="log_user")
    log_pass = st.text_input("Password", type="password", key="log_pass")
    
    if st.button("Login", type="primary"):
        with st.spinner("Verifying credentials with Google Sheets..."):
            users = get_user_database()
            
            if log_user in users and users[log_user]['password'] == hash_password(log_pass):
                st.session_state['logged_in'] = True
                st.session_state['username'] = log_user
                
                # Retrieve the specific Google Sheet ID assigned to this user!
                st.session_state['user_file'] = users[log_user]['sheet_id']
                
                st.success("Login successful! Loading dashboard...")
                st.rerun()
            else:
                st.error("Incorrect username or password.")

# --- REGISTER TAB ---
with tab_register:
    st.subheader("Create a new account")
    reg_user = st.text_input("New Username", key="reg_user")
    reg_pass = st.text_input("New Password", type="password", key="reg_pass")
    reg_pass_confirm = st.text_input("Confirm Password", type="password", key="reg_pass_confirm")
    
    if st.button("Register & Create Database"):
        if not reg_user or not reg_pass:
            st.warning("Please fill in all fields.")
        elif reg_pass != reg_pass_confirm:
            st.error("Passwords do not match!")
        else:
            with st.spinner("Generating dedicated Google Sheet Database (this takes ~10 seconds)..."):
                users = get_user_database()
                
                if reg_user in users:
                    st.error("Username already exists! Please choose another.")
                else:
                    try:
                        # 1. Create the new Google Sheet file
                        new_sheet_id = create_new_user_sheet(reg_user)
                        
                        # 2. Save the user details to the Master DB
                        hashed_pw = hash_password(reg_pass)
                        register_user_in_db(reg_user, hashed_pw, new_sheet_id)
                        
                        st.success(f"Account created! A new Google Sheet named 'Rota_Scheduler_{reg_user}' has been generated and shared with your admin email. Please log in.")
                    except Exception as e:
                        st.error(f"Failed to create account: {e}")
