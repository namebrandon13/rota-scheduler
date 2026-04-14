import streamlit as st

# 1. SETUP PAGE CONFIG
st.set_page_config(page_title="Rota Master", layout="wide")

# 2. INITIALIZE SESSION STATE
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# 3. DEFINE YOUR PAGES
# We point to the specific filenames in your 'views' folder.
# We can set clean Titles here so the sidebar doesn't show "1_Employees".

login_page = st.Page("views/login.py", title="Log In", icon="🔒")

# The Main App Pages
rota_page       = st.Page("views/5_Rota.py",       title="Rota Dashboard", icon="🚀")
employees_page  = st.Page("views/1_Employees.py",  title="Employees",      icon="👥")
scheduling_page = st.Page("views/2_Scheduling.py", title="Scheduling",     icon="🗓️")
holidays_page   = st.Page("views/3_Holidays.py",    title="Holidays",       icon="✈️")
events_page     = st.Page("views/4_Events.py",      title="Events",         icon="🎫")

# 4. NAVIGATION LOGIC
if st.session_state['logged_in']:
    # --- LOGGED IN VIEW ---
    # You can group them however you like in the dictionary below
    pg = st.navigation(
        {
            "Dashboard": [rota_page],
            "Management": [employees_page, scheduling_page, holidays_page, events_page],
        }
    )
else:
    # --- LOGGED OUT VIEW ---
    # Only the login page exists. Sidebar will be hidden automatically.
    pg = st.navigation([login_page])

# 5. RUN THE SELECTED PAGE
pg.run()