import streamlit as st
import hashlib
from gsheets_db import get_user_database, register_user_in_db

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

st.title("🔒 Manager Portal")

tab_login, tab_register = st.tabs(["Login", "Register New User"])

# --- LOGIN TAB ---
with tab_login:
    st.subheader("Login to your account")
    log_user = st.text_input("Username", key="log_user")
    log_pass = st.text_input("Password", type="password", key="log_pass")
    
    if st.button("Login", type="primary"):
        with st.spinner("Verifying credentials..."):
            # 1. Get the users dict (ensure it uses the new row.to_dict() logic)
            users = get_user_database()
            
            if log_user in users:
                user_data = users[log_user]
                
                # Check for 'Password' (Capital P) as it appears in your Excel
                # We use .get() to prevent the app from crashing if the column is missing
                stored_password = user_data.get('Password') or user_data.get('password')
                
                if stored_password and stored_password == hash_password(log_pass):
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = log_user
                    # Store the sheet ID associated with this user
                    st.session_state['sheet_id'] = user_data.get('SheetID') 
                    st.success("Logged in!")
                    st.rerun()
                else:
                    st.error("Invalid password.")
            else:
                st.error("User not found.")

# --- REGISTER TAB ---
with tab_register:
    st.subheader("Create a new account")
    reg_user = st.text_input("New Username", key="reg_user")
    reg_pass = st.text_input("New Password", type="password", key="reg_pass")
    reg_pass_confirm = st.text_input("Confirm Password", type="password", key="reg_pass_confirm")
    
    if st.button("Register Account"):
        if not reg_user or not reg_pass:
            st.warning("Please fill in all fields.")
        elif reg_pass != reg_pass_confirm:
            st.error("Passwords do not match!")
        else:
            with st.spinner("Registering user..."):
                users = get_user_database()
                if reg_user in users:
                    st.error("Username already exists! Please choose another.")
                else:
                    register_user_in_db(reg_user, hash_password(reg_pass))
                    st.success("Account created successfully! You can now log in.")
