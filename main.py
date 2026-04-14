import streamlit as st
import os

# ======================================================
# CLOUD READY MAIN.PY
# ======================================================

# Root project directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ======================================================
# PAGE CONFIG
# ======================================================

st.set_page_config(
    page_title="Rota Master",
    layout="wide"
)

# ======================================================
# SESSION STATE
# ======================================================

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# ======================================================
# SAFE PAGE PATHS
# ======================================================

def view_path(filename):
    return os.path.join(BASE_DIR, "views", filename)

# ======================================================
# DEFINE PAGES
# ======================================================

login_page = st.Page(
    view_path("login.py"),
    title="Log In",
    icon="🔒"
)

rota_page = st.Page(
    view_path("5_Rota.py"),
    title="Rota Dashboard",
    icon="🚀"
)

employees_page = st.Page(
    view_path("1_Employees.py"),
    title="Employees",
    icon="👥"
)

scheduling_page = st.Page(
    view_path("2_Scheduling.py"),
    title="Scheduling",
    icon="🗓️"
)

holidays_page = st.Page(
    view_path("3_Holidays.py"),
    title="Holidays",
    icon="✈️"
)

events_page = st.Page(
    view_path("4_Events.py"),
    title="Events",
    icon="🎫"
)

# ======================================================
# NAVIGATION
# ======================================================

if st.session_state["logged_in"]:

    pg = st.navigation(
        {
            "Dashboard": [
                rota_page
            ],

            "Management": [
                employees_page,
                scheduling_page,
                holidays_page,
                events_page
            ],
        }
    )

else:

    pg = st.navigation([
        login_page
    ])

# ======================================================
# RUN PAGE
# ======================================================

pg.run()
