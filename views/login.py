import streamlit as st

st.title("🔒 Manager Login")

username = st.text_input("Username")
password = st.text_input("Password", type="password")

if st.button("Login"):
    if username == "admin" and password == "1234":
        st.session_state['logged_in'] = True
        
        # ADD THIS: Store the specific Google Sheet ID for this user
        # (Currently hardcoded to your only secret, scalable later)
        try:
            st.session_state['sheet_id'] = st.secrets["google_sheets"]["spreadsheet_id"]
        except KeyError:
            st.error("Google Sheets ID not found in secrets.")
            st.stop()
            
        st.success("Login successful!")
        st.rerun()
    else:
        st.error("Incorrect username or password")
