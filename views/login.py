import streamlit as st

st.title("🔒 Manager Login")

# 1. CREATE THE INPUT BOXES (Define variables first!)
username = st.text_input("Username")
password = st.text_input("Password", type="password")

# 2. THE BUTTON CHECK
if st.button("Login"):
    # Now the variables 'username' and 'password' exist, so this line won't crash
    if username == "admin" and password == "1234":
        st.session_state['logged_in'] = True
        st.success("Login successful!")
        st.rerun()  # Forces main.py to reload and show the sidebar
    else:
        st.error("Incorrect username or password")