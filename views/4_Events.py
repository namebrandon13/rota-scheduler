import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, date, timedelta
import pydeck as pdk
import json
import folium
from streamlit_folium import st_folium

# Import your database handler
from gsheets_db import get_user_data, write_user_data

# ======================================================
# AUTH & SETUP
# ======================================================

# Verify user is logged in
if 'sheet_id' not in st.session_state or 'username' not in st.session_state:
    st.error("Please log in to access Event Intelligence.")
    st.stop()

sheet_id = st.session_state['sheet_id']
username = st.session_state['username']
SHEET_EVENTS = "Events"
SHEET_USERS = "Users"

# ======================================================
# HELPERS & BACKEND
# ======================================================

def update_user_location(sheet_id, username, lat, lon):
    """Updates the 'Location' column in the 'Users' sheet for the current user."""
    # 1. Fetch the entire Users sheet
    df_users = get_user_data(sheet_id, SHEET_USERS, username)
    
    if df_users.empty:
        st.error("User record not found in database.")
        return False

    # 2. Prepare the coordinate string as JSON
    location_data = json.dumps({"lat": lat, "lon": lon})

    # 3. Update the 'Location' column for the current username
    if 'Location' in df_users.columns:
        df_users.loc[df_users['Username'] == username, 'Location'] = location_data
        
        # 4. Write back the updated dataframe to Google Sheets
        write_user_data(sheet_id, SHEET_USERS, username, df_users)
        return True
    else:
        st.error("Column 'Location' not found in Users sheet. Please add it to your Excel/Sheets.")
        return False

def impact_color(score):
    if score >= 8: return "#DC2626" # Red
    elif score >= 5: return "#D97706" # Orange
    return "#16A34A" # Green

def impact_label(score):
    if score >= 8: return "HIGH"
    elif score >= 5: return "MEDIUM"
    return "LOW"

def load_data():
    """Load events directly from Google Sheets for the logged-in user."""
    try:
        df = get_user_data(sheet_id, SHEET_EVENTS, username)
        if not df.empty:
            df.columns = df.columns.str.strip()
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
        return df
    except Exception as e:
        st.error(f"Error loading events: {e}")
        return pd.DataFrame()

# ======================================================
# IMPORT EVENT SCANNER
# ======================================================

try:
    from eventapicall import scan_live
except:
    scan_live = None

# ======================================================
# CSS STYLING
# ======================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.page-title { font-size: 2.1rem; font-weight: 800; color: #111827; }
.page-sub { color: #6B7280; margin-bottom: 18px; }
.calendar-box {
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 10px;
    min-height: 110px;
    background: white;
    text-align: center;
}
.day-number { font-size: 1.45rem; font-weight: 800; margin-bottom: 6px; }
</style>
""", unsafe_allow_html=True)

# ======================================================
# SESSION STATE
# ======================================================

if "ev_year" not in st.session_state:
    st.session_state.ev_year = datetime.today().year

if "ev_month" not in st.session_state:
    st.session_state.ev_month = datetime.today().month

# ======================================================
# HEADER & LOCATION PICKER
# ======================================================

st.markdown("<div class='page-title'>🎫 Event Intelligence</div>", unsafe_allow_html=True)
st.markdown("<div class='page-sub'>Track local events that affect staffing demand.</div>", unsafe_allow_html=True)

# Map Picker UI in an expander
with st.expander("📍 Set/Update Business Location", expanded=False):
    st.markdown("<div style='font-size:0.85em; color:#6B7280; margin-bottom:10px;'>Click the map to pin your business. We use this to find events within your radius.</div>", unsafe_allow_html=True)
    
    # Render map centered on London by default
    m = folium.Map(location=[51.5074, -0.1278], zoom_start=12)
    map_data = st_folium(m, width=700, height=300)

    if map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lon = map_data["last_clicked"]["lng"]
        st.write(f"**Selected:** `{lat:.5f}, {lon:.5f}`")
        
        if st.button("📍 Save as My Business Location", use_container_width=True):
            if update_user_location(sheet_id, username, lat, lon):
                st.success("Location saved to your profile!")
                st.rerun()

st.divider()

# ======================================================
# ACTIONS (Run Scan)
# ======================================================

c1, c2, c3 = st.columns([1.5, 1.5, 4])

with c1:
    if st.button("🔄 Run Live Scan", type="primary", use_container_width=True):
        if scan_live:
            with st.spinner("Scanning surroundings & syncing..."):
                try:
                    result = scan_live(30)
                    if result is not None and not result.empty:
                        df_upload = result.copy()
                        if "Date" in df_upload.columns:
                            df_upload["Date"] = pd.to_datetime(df_upload["Date"]).dt.strftime('%Y-%m-%d')
                        write_user_data(sheet_id, SHEET_EVENTS, username, df_upload)
                        st.success(f"Found {len(result)} events!")
                    else:
                        st.info("No new events found.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Scan error: {e}")
        else:
            st.error("Scanner module not found.")

with c2:
    st.caption("Radius based on saved location.")

# ======================================================
# MAIN CONTENT
# ======================================================

df = load_data()
today_ts = pd.Timestamp(date.today())

if df.empty:
    st.info("No event data available. Use the map above to set your location, then 'Run Live Scan'.")
    st.stop()

# Metrics
upcoming = df[df["Date"] >= today_ts]
m1, m2, m3 = st.columns(3)
m1.metric("Total Events", len(df))
m2.metric("Upcoming", len(upcoming))
m3.metric("High Impact", len(df[df["Impact Score"] >= 8]) if "Impact Score" in df.columns else 0)

# Filters
st.subheader("🔍 Filters")
fc1, fc2, fc3 = st.columns(3)
with fc1: show_past = st.checkbox("Show Past Events", value=False)
with fc2: score_range = st.slider("Impact Score", 0, 10, (0, 10))
with fc3: search = st.text_input("Search Event Name")

# Filtering Logic
filtered = df.copy()
if not show_past: filtered = filtered[filtered["Date"] >= today_ts]
if "Impact Score" in filtered.columns:
    filtered = filtered[(filtered["Impact Score"] >= score_range[0]) & (filtered["Impact Score"] <= score_range[1])]
if search:
    filtered = filtered[filtered["Event Name"].astype(str).str.contains(search, case=False, na=False)]
filtered = filtered.sort_values("Date")

# Tabs
tab1, tab2, tab3 = st.tabs(["🃏 Cards", "📅 Calendar", "🗺️ Map"])

with tab1:
    if filtered.empty:
        st.info("No matching events found.")
    else:
        cols = st.columns(3)
        for i, (_, row) in enumerate(filtered.iterrows()):
            score = int(row.get("Impact Score", 0))
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{row.get('Event Name', 'Event')}**")
                    st.progress(score / 10)
                    st.caption(f"📅 {row['Date'].strftime('%d %b')} · 📍 {row.get('Venue', 'Local')}")

with tab2:
    # Basic Calendar Implementation
    yr, mo = st.session_state.ev_year, st.session_state.ev_month
    n1, n2, n3 = st.columns([1, 4, 1])
    with n1: 
        if st.button("◀", key="p_mo"): 
            st.session_state.ev_month = 12 if mo == 1 else mo - 1
            if mo == 1: st.session_state.ev_year -= 1
            st.rerun()
    with n2: st.markdown(f"<center><b>{datetime(yr, mo, 1).strftime('%B %Y')}</b></center>", unsafe_allow_html=True)
    with n3:
        if st.button("▶", key="n_mo"):
            st.session_state.ev_month = 1 if mo == 12 else mo + 1
            if mo == 12: st.session_state.ev_year += 1
            st.rerun()

    event_map = {}
    for _, row in filtered.iterrows():
        d = row["Date"].date()
        event_map.setdefault(d, []).append(row)

    for week in calendar.monthcalendar(yr, mo):
        cols = st.columns(7)
        for i, day_num in enumerate(week):
            if day_num == 0: continue
            curr = date(yr, mo, day_num)
            with cols[i]:
                bg = impact_color(max([x.get("Impact Score", 0) for x in event_map[curr]])) + "22" if curr in event_map else "#FFFFFF"
                st.markdown(f"<div class='calendar-box' style='background:{bg}'><div class='day-number'>{day_num}</div></div>", unsafe_allow_html=True)

with tab3:
    if "Lat" in filtered.columns and "Lon" in filtered.columns:
        map_df = filtered.dropna(subset=["Lat", "Lon"])
        if not map_df.empty:
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/light-v9',
                initial_view_state=pdk.ViewState(latitude=map_df["Lat"].mean(), longitude=map_df["Lon"].mean(), zoom=11),
                layers=[pdk.Layer("ScatterplotLayer", data=map_df, get_position='[Lon, Lat]', get_color='[200, 30, 0, 160]', get_radius=200)]
            ))
