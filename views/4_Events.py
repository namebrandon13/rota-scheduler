import streamlit as st
import pandas as pd
import os
import subprocess
import sys
import calendar
from datetime import datetime, date
import pydeck as pdk

# ======================================================
# CLOUD READY PATHS
# ======================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_FILE = os.path.join(BASE_DIR, "EventsData.xlsx")
EVENT_SCRIPT = os.path.join(BASE_DIR, "eventapicall.py")

# ======================================================
# PAGE CONFIG
# ======================================================

st.set_page_config(page_title="Events", layout="wide")

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
    if not os.path.exists(EVENTS_FILE):
        return pd.DataFrame()

    try:
        df = pd.read_excel(EVENTS_FILE)
        df.columns = df.columns.str.strip()

        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])

        return df

    except:
        return pd.DataFrame()


def run_scan():
    try:
        if not os.path.exists(EVENT_SCRIPT):
            return False, "eventapicall.py not found"

        subprocess.run(
            [sys.executable, EVENT_SCRIPT],
            cwd=BASE_DIR,
            check=True
        )

        return True, "Scan complete"

    except Exception as e:
        return False, str(e)


# ======================================================
# CSS
# ======================================================

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: Inter, sans-serif;
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

.event-card {
    background: white;
    border: 1px solid #E5E7EB;
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 14px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
}

.badge {
    padding: 4px 10px;
    border-radius: 30px;
    font-size: 0.75rem;
    font-weight: 700;
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

c1, c2 = st.columns([1.5, 5])

with c1:
    if st.button("🔄 Run Live Scan", type="primary", use_container_width=True):
        with st.spinner("Scanning..."):
            ok, msg = run_scan()

        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

# ======================================================
# NO DATA
# ======================================================

if df.empty:
    st.info("No event data available.")
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
    show_past = st.checkbox("Show Past Events", value=True)

with fc2:
    if "Impact Score" in df.columns:
        score_range = st.slider(
            "Impact Score",
            0,
            10,
            (0, 10)
        )
    else:
        score_range = (0, 10)

with fc3:
    search = st.text_input("Search Event")

# ======================================================
# APPLY FILTERS
# ======================================================

filtered = df.copy()

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

tab1, tab2, tab3 = st.tabs([
    "🃏 Cards",
    "📅 Calendar",
    "🗺️ Map"
])

# ======================================================
# CARDS
# ======================================================

with tab1:

    if filtered.empty:
        st.info("No matching events.")
    else:

        cols = st.columns(3)

        for i, (_, row) in enumerate(filtered.iterrows()):

            score = int(row.get("Impact Score", 0))
            color = impact_color(score)
            label = impact_label(score)

            with cols[i % 3]:

                st.markdown(
                    f"""
                    <div class='event-card'>
                        <div style='display:flex;justify-content:space-between;gap:10px'>
                            <div style='font-weight:800'>
                                {row.get("Event Name","")}
                            </div>
                            <div class='badge'
                                 style='background:{color};color:white'>
                                 {label}
                            </div>
                        </div>

                        <div style='margin-top:8px;color:#6B7280'>
                            📅 {row["Date"].strftime("%d %b %Y")}
                        </div>

                        <div style='margin-top:6px'>
                            📍 {row.get("Venue","")}
                        </div>

                        <div style='margin-top:8px'>
                            ⚡ {score}/10
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

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
        st.markdown(
            f"### {datetime(yr, mo, 1).strftime('%B %Y')}"
        )

    with n3:
        if st.button("▶", key="next_month"):
            if mo == 12:
                st.session_state.ev_month = 1
                st.session_state.ev_year += 1
            else:
                st.session_state.ev_month += 1
            st.rerun()

    headers = st.columns(7)

    for i, day_name in enumerate(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    ):
        headers[i].markdown(f"**{day_name}**")

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
                    score = max(
                        int(x.get("Impact Score", 0))
                        for x in day_events
                    )
                    bg = impact_color(score) + "22"
                else:
                    bg = "#FFFFFF"

                txt = "<br>".join(
                    [
                        str(x["Event Name"])[:16]
                        for x in day_events[:2]
                    ]
                )

                st.markdown(
                    f"""
                    <div class='calendar-box'
                         style='background:{bg}'>
                        <div class='day-number'>{day_num}</div>
                        <div style='font-size:0.75rem'>
                            {txt}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# ======================================================
# MAP
# ======================================================

with tab3:

    if (
        "Lat" not in filtered.columns or
        "Lon" not in filtered.columns
    ):
        st.warning("No map coordinates available.")

    else:

        map_df = filtered.dropna(
            subset=["Lat", "Lon"]
        )

        if map_df.empty:
            st.warning("No map data.")
        else:

            layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position='[Lon, Lat]',
                get_radius=180,
                get_fill_color='[220, 38, 38, 180]',
                pickable=True
            )

            view_state = pdk.ViewState(
                latitude=map_df["Lat"].mean(),
                longitude=map_df["Lon"].mean(),
                zoom=11
            )

            deck = pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={
                    "text": "{Event Name}\n{Venue}"
                }
            )

            st.pydeck_chart(
                deck,
                use_container_width=True
            )
