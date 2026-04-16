import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, date, timedelta
import pydeck as pdk

# Import your new database handler
from gsheets_db import get_sheet_data, write_sheet_data

# ======================================================
# AUTH & SETUP
# ======================================================

# Verify user is logged in and has a sheet ID assigned
if 'sheet_id' not in st.session_state:
    st.error("Please log in to access Event Intelligence.")
    st.stop()

sheet_id = st.session_state['sheet_id']
SHEET_EVENTS = "Events"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ======================================================
# IMPORT EVENT SCANNER
# ======================================================

try:
    from eventapicall import scan_live
except:
    scan_live = None

# ======================================================
# HELPERS
# ======================================================

def impact_color(score):
    if score >= 8:
        return "#DC2626"
    elif score >= 5:
        return "#D97706"
    return "#16A34A"


def impact_label(score):
    if score >= 8:
        return "HIGH"
    elif score >= 5:
        return "MEDIUM"
    return "LOW"


def load_data():
    """Load events directly from Google Sheets."""
    try:
        df = get_sheet_data(sheet_id, SHEET_EVENTS)
        if not df.empty:
            df.columns = df.columns.str.strip()
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
        return df
    except Exception as e:
        st.error(f"Error loading events from Google Sheets: {e}")
        return pd.DataFrame()


# ======================================================
# CSS
# ======================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.page-title {
    font-size: 2.1rem;
    font-weight: 800;
    color: #111827;
}

.page-sub {
    color: #6B7280;
    margin-bottom: 18px;
}

.metric-box {
    background: white;
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 14px;
}

.calendar-box {
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 10px;
    min-height: 110px;
    background: white;
    text-align: center;
}

.day-number {
    font-size: 1.45rem;
    font-weight: 800;
    margin-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# SESSION
# ======================================================

if "ev_year" not in st.session_state:
    st.session_state.ev_year = datetime.today().year

if "ev_month" not in st.session_state:
    st.session_state.ev_month = datetime.today().month

# ======================================================
# LOAD DATA
# ======================================================

df = load_data()
today = pd.Timestamp(date.today())

# ======================================================
# HEADER
# ======================================================

st.markdown("<div class='page-title'>🎫 Event Intelligence</div>", unsafe_allow_html=True)
st.markdown("<div class='page-sub'>Track local events that may affect staffing demand.</div>", unsafe_allow_html=True)

# ======================================================
# ACTIONS
# ======================================================

c1, c2, c3 = st.columns([1.5, 1.5, 4])

with c1:
    if st.button("🔄 Run Live Scan", type="primary", use_container_width=True):
        if scan_live:
            with st.spinner("Scanning today + 30 days & syncing to cloud..."):
                try:
                    result = scan_live(30)  # Scan today + 30 days
                    if result is not None and not result.empty:
                        # Upload directly to Google Sheets
                        df_upload = result.copy()
                        if "Date" in df_upload.columns:
                            df_upload["Date"] = pd.to_datetime(df_upload["Date"]).dt.strftime('%Y-%m-%d')
                        write_sheet_data(sheet_id, SHEET_EVENTS, df_upload)
                        
                        st.success(f"Found {len(result)} events and synced to cloud!")
                    else:
                        st.info("No new events found.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Scan error: {e}")
        else:
            st.error("Event scanner not available.")

with c2:
    st.caption("Scans: Today → +30 days")

# ======================================================
# NO DATA
# ======================================================

if df.empty:
    st.info("No event data available in the cloud. Click 'Run Live Scan' to fetch events.")
    st.stop()

# ======================================================
# METRICS
# ======================================================

upcoming = df[df["Date"] >= today]
past = df[df["Date"] < today]

m1, m2, m3, m4 = st.columns(4)

m1.metric("Total Events", len(df))
m2.metric("Upcoming", len(upcoming))
m3.metric("Past", len(past))

if "Impact Score" in df.columns:
    m4.metric("High Impact", len(df[df["Impact Score"] >= 8]))
else:
    m4.metric("High Impact", 0)

st.divider()

# ======================================================
# FILTERS
# ======================================================

st.subheader("🔍 Filters")

fc1, fc2, fc3 = st.columns(3)

with fc1:
    # DEFAULT: Hide past events (checkbox unchecked = show only future)
    show_past = st.checkbox("Show Past Events", value=False)

with fc2:
    if "Impact Score" in df.columns:
        score_range = st.slider("Impact Score", 0, 10, (0, 10))
    else:
        score_range = (0, 10)

with fc3:
    search = st.text_input("Search Event")

# ======================================================
# APPLY FILTERS
# ======================================================

filtered = df.copy()

# DEFAULT: Only show today and future events
if not show_past:
    filtered = filtered[filtered["Date"] >= today]

if "Impact Score" in filtered.columns:
    filtered = filtered[
        (filtered["Impact Score"] >= score_range[0]) &
        (filtered["Impact Score"] <= score_range[1])
    ]

if search:
    filtered = filtered[
        filtered["Event Name"]
        .astype(str)
        .str.contains(search, case=False, na=False)
    ]

filtered = filtered.sort_values("Date")

# ======================================================
# TABS
# ======================================================

tab1, tab2, tab3 = st.tabs(["🃏 Cards", "📅 Calendar", "🗺️ Map"])

# ======================================================
# CARDS
# ======================================================

with tab1:
    if filtered.empty:
        if not show_past:
            st.info("No upcoming events. Enable 'Show Past Events' to see historical data.")
        else:
            st.info("No matching events.")
    else:
        # Show count
        st.caption(f"Showing {len(filtered)} event(s)")
        
        cols = st.columns(3)

        for i, (_, row) in enumerate(filtered.iterrows()):
            score = int(row.get("Impact Score", 0))
            color = impact_color(score)
            label = impact_label(score)
            event_name = str(row.get("Event Name", ""))
            venue = str(row.get("Venue", ""))
            event_date = row["Date"].strftime("%d %b %Y")
            start_time = str(row.get("Start Time", ""))

            with cols[i % 3]:
                with st.container(border=True):
                    # Header row with title and badge
                    hc1, hc2 = st.columns([3, 1])
                    with hc1:
                        st.markdown(f"**{event_name}**")
                    with hc2:
                        st.markdown(
                            f"<span style='background:{color};color:white;padding:4px 8px;"
                            f"border-radius:20px;font-size:0.72em;font-weight:700'>{label}</span>",
                            unsafe_allow_html=True
                        )
                    
                    # Event details
                    st.caption(f"📅 {event_date} · 🕐 {start_time}")
                    st.caption(f"📍 {venue}")
                    
                    # Score bar
                    st.progress(score / 10, text=f"Impact: {score}/10")

# ======================================================
# CALENDAR
# ======================================================

with tab2:
    yr = st.session_state.ev_year
    mo = st.session_state.ev_month

    n1, n2, n3 = st.columns([1, 4, 1])

    with n1:
        if st.button("◀", key="prev_month"):
            if mo == 1:
                st.session_state.ev_month = 12
                st.session_state.ev_year -= 1
            else:
                st.session_state.ev_month -= 1
            st.rerun()

    with n2:
        st.markdown(f"### {datetime(yr, mo, 1).strftime('%B %Y')}")

    with n3:
        if st.button("▶", key="next_month"):
            if mo == 12:
                st.session_state.ev_month = 1
                st.session_state.ev_year += 1
            else:
                st.session_state.ev_month += 1
            st.rerun()

    headers = st.columns(7)
    for i, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        headers[i].markdown(f"**{day_name}**")

    # Use filtered data for calendar (respects show_past checkbox)
    event_map = {}
    for _, row in filtered.iterrows():
        d = row["Date"].date()
        event_map.setdefault(d, []).append(row)

    for week in calendar.monthcalendar(yr, mo):
        cols = st.columns(7)

        for i, day_num in enumerate(week):
            with cols[i]:
                if day_num == 0:
                    st.write("")
                    continue

                curr = date(yr, mo, day_num)
                day_events = event_map.get(curr, [])

                if day_events:
                    score = max(int(x.get("Impact Score", 0)) for x in day_events)
                    bg = impact_color(score) + "22"
                else:
                    bg = "#FFFFFF"

                txt = "<br>".join([str(x["Event Name"])[:16] for x in day_events[:2]])

                st.markdown(
                    f"""
                    <div class='calendar-box' style='background:{bg}'>
                        <div class='day-number'>{day_num}</div>
                        <div style='font-size:0.75rem'>{txt}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# ======================================================
# MAP
# ======================================================

with tab3:
    if "Lat" not in filtered.columns or "Lon" not in filtered.columns:
        st.warning("No map coordinates available.")
    else:
        map_df = filtered.dropna(subset=["Lat", "Lon"])

        if map_df.empty:
            st.warning("No map data for filtered events.")
        else:
            # Create a clean list of dicts for pydeck (avoids serialization issues)
            map_data = []
            for _, row in map_df.iterrows():
                score = int(row.get('Impact Score', 0))
                if score >= 8:
                    color = [220, 38, 38, 200]
                elif score >= 5:
                    color = [217, 119, 6, 200]
                else:
                    color = [22, 163, 74, 200]
                
                map_data.append({
                    'lat': float(row['Lat']),
                    'lon': float(row['Lon']),
                    'name': str(row.get('Event Name', 'Unknown')),
                    'venue': str(row.get('Venue', '')),
                    'score': score,
                    'color': color
                })

            layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_data,
                get_position='[lon, lat]',
                get_radius=200,
                get_fill_color='color',
                pickable=True
            )

            avg_lat = sum(d['lat'] for d in map_data) / len(map_data)
            avg_lon = sum(d['lon'] for d in map_data) / len(map_data)

            view_state = pdk.ViewState(
                latitude=avg_lat,
                longitude=avg_lon,
                zoom=12
            )

            deck = pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={
                    "html": "<b>{name}</b><br>📍 {venue}<br>⚡ Impact: {score}/10",
                    "style": {"backgroundColor": "#1E293B", "color": "white"}
                }
            )

            st.pydeck_chart(deck, use_container_width=True)
            
            # Legend
            st.markdown("""
            **Map Legend:**
            🔴 High Impact (8-10) · 🟠 Medium Impact (5-7) · 🟢 Low Impact (1-4)
            """)
