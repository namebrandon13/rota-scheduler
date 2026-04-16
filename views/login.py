import streamlit as st
import json
import os
import pandas as pd
import hashlib

# --- CONFIG ---
USER_DB_FILE = "users_db.json"

# Basic security hashing for passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USER_DB_FILE, "w") as f:
        json.dump(users, f)

def create_template_excel(file_name):
    """Generates a blank Excel file with all required tabs for a new user."""
    with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
        # Employees Tab
        pd.DataFrame(columns=["ID", "Name", "Max Weekly Hours", "Minimum Contractual Hours", "Designation", "Preferred Day", "Preferred slot", "Fixed Slot", "Fixed Role", "Unavailable Days", "Opening Trained", "Fixed Shift Enabled", "Fixed Weekly Shift"]).to_excel(writer, sheet_name="Employees", index=False)
        # Shift Template Tab
        pd.DataFrame(columns=["Date", "Start", "End", "Minimum Staff", "Maximum Employees", "Minimum closing staff", "Budget"]).to_excel(writer, sheet_name="Shift Template", index=False)
        # Holiday Tab
        pd.DataFrame(columns=["Employee ID", "Name", "Date", "Status", "Reason"]).to_excel(writer, sheet_name="Holiday", index=False)
        # Events Tab
        pd.DataFrame(columns=["Date", "Start Time", "End Time", "Duration", "Event Name", "Venue", "Est. Footfall", "Lat", "Lon", "Source", "Distance (Miles)", "Impact Score"]).to_excel(writer, sheet_name="Events", index=False)

st.title("🔒 Manager Portal")

# Setup Tabs for Login and Register
tab_login, tab_register = st.tabs(["Login", "Register New User"])
users = load_users()

# --- LOGIN TAB ---
with tab_login:
    st.subheader("Login to your account")
    log_user = st.text_input("Username", key="log_user")
    log_pass = st.text_input("Password", type="password", key="log_pass")
    
    if st.button("Login", type="primary"):
        if log_user in users and users[log_user]['password'] == hash_password(log_pass):
            st.session_state['logged_in'] = True
            st.session_state['username'] = log_user
            
            # Retrieve the specific Excel file assigned to this user!
            st.session_state['user_file'] = users[log_user]['excel_file']
            
            st.success(f"Login successful. Loading {users[log_user]['excel_file']}...")
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
        elif reg_user in users:
            st.error("Username already exists! Please choose another.")
        elif reg_pass != reg_pass_confirm:
            st.error("Passwords do not match!")
        else:
            # Assign a unique Excel file name
            new_file_name = f"RotaData_{reg_user}.xlsx"
            
            # Save user
            users[reg_user] = {
                "password": hash_password(reg_pass),
                "excel_file": new_file_name
            }
            save_users(users)
            
            # Create their dedicated Excel file
            create_template_excel(new_file_name)
            
            st.success(f"Account created! Dedicated database ({new_file_name}) initialized. Please log in.")
