import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, date, time, timedelta
import pydeck as pdk

# Import your new database handler
from gsheets_db import get_user_data, write_user_data

# ======================================================
# AUTH & SETUP
# ======================================================

# Verify user is logged in and has a sheet ID AND username assigned
if 'sheet_id' not in st.session_state or 'username' not in st.session_state:
    st.error("Please log in to access the Scheduling Management.")
    st.stop()

sheet_id = st.session_state['sheet_id']
username = st.session_state['username']
SHEET_TEMPLATE = "Shift Template"
SHEET_EVENTS = "Events"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ======================================================
# IMPORT EVENT SCANNER
# ======================================================

try:
    from eventapicall import scan_week
except:
    scan_week = None

# ======================================================
# STYLE
# ======================================================

SHARED_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.page-title{font-size:2em;font-weight:900;color:#1E293B;}
.page-sub{font-size:0.88em;color:#64748B;margin-bottom:14px;}
div[data-testid="stButton"]>button{border-radius:8px;font-weight:600;}
div[data-testid="stMetric"]{
    background:white;
    border:1px solid #E2E8F0;
    border-radius:12px;
    padding:14px;
}
.cal-cell{
    border-radius:14px;
    padding:14px 6px 8px;
    text-align:center;
    min-height:125px;
    border:1px solid #E2E8F0;
    background:white;
}
.cell-sched{background:#EFF6FF;border-color:#BFDBFE;}
.cell-empty{background:#F8FAFC;}
.day-num{font-size:2.5em;font-weight:900;}
.day-badge{
    display:inline-block;
    padding:3px 10px;
    border-radius:20px;
    font-size:0.82em;
    font-weight:700;
}
.badge-sched{background:#2563EB;color:white;}
.badge-empty{background:#E5E7EB;color:#64748B;}
.event-alert{
    background:#FEF3C7;
    border:1px solid #F59E0B;
    border-radius:12px;
    padding:12px 16px;
    margin:8px 0;
}
.event-high{
    background:#FEE2E2;
    border-color:#DC2626;
}
.calendar-box{
    border:1px solid #E5E7EB;
    border-radius:10px;
    padding:8px;
    min-height:80px;
    background:white;
    text-align:center;
}
.calendar-box .day-number{
    font-size:1.3rem;
    font-weight:800;
    margin-bottom:4px;
}
</style>
"""
st.markdown(SHARED_CSS, unsafe_allow_html=True)

# ======================================================
# SESSION
# ======================================================

defaults = {
    "sched_view": "calendar",
    "sched_yr": datetime.today().year,
    "sched_mo": datetime.today().month,
    "sched_ws": None,
    "week_events": None,
    "events_scanned": False
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ======================================================
# HELPERS
# ======================================================

def get_week_start(d):
    if isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, pd.Timestamp):
        d = d.date()
    return d - timedelta(days=d.weekday())

@st.cache_data(ttl=10)
def load_all(user):
    try:
        # Fetch only this user's templates
        df = get_user_data(sheet_id, SHEET_TEMPLATE, user)
        if df.empty:
            return pd.DataFrame()
            
        df.columns = df.columns.str.strip()
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Start", "End"]:
            try:
                df[col] = pd.to_datetime(df[col].astype(str)).dt.time
            except:
                pass
        return df
    except Exception as e:
        st.error(f"Error loading schedule: {e}")
        return pd.DataFrame()

def load_events_for_week(ws, user):
    try:
        # Fetch only this user's events
        df = get_user_data(sheet_id, SHEET_EVENTS, user)
        if df.empty:
            return pd.DataFrame()
            
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        we = ws + timedelta(days=6)
        df = df[(df['Date'] >= ws) & (df['Date'] <= we)]
        return df.sort_values('Date')
    except Exception as e:
        st.error(f"Error loading events: {e}")
        return pd.DataFrame()

def save_all(df, user):
    try:
        # CRITICAL REPAIR: Drop any duplicated days so the database stays perfectly clean
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').drop_duplicates(subset=['Date'], keep='last')

        df_upload = df.copy()
        if 'Date' in df_upload.columns:
            df_upload['Date'] = df_upload['Date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')
        for col in ['Start', 'End']:
            if col in df_upload.columns:
                df_upload[col] = df_upload[col].apply(lambda x: x.strftime('%H:%M:%S') if pd.notna(x) else '')
                
        # Save only to this user's partition
        write_user_data(sheet_id, SHEET_TEMPLATE, user, df_upload)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Error saving to Google Sheets: {e}")

def nav_to(view, ws=None):
    st.session_state.sched_view = view
    if ws is not None:
        st.session_state.sched_ws = ws
    if view != "add":
        st.session_state.week_events = None
        st.session_state.events_scanned = False
    st.rerun()

def week_label(ws):
    we = ws + timedelta(days=6)
    wn = (ws + timedelta(days=3)).isocalendar()[1]
    return f"Week {wn} · {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}"

def impact_color(score):
    if score >= 8: return "#DC2626"
    elif score >= 5: return "#D97706"
    return "#16A34A"

def impact_label(score):
    if score >= 8: return "HIGH"
    elif score >= 5: return "MEDIUM"
    return "LOW"

# ======================================================
# SIDEBAR
# ======================================================

def get_sched_weeks(user):
    df = load_all(user)
    if df.empty: return set()
    return {get_week_start(d) for d in df["Date"]}

def render_sidebar():
    sw = get_sched_weeks(username)
    with st.sidebar:
        st.markdown("### 📊 Scheduling")
        st.metric("Weeks Configured", len(sw))

render_sidebar()

# ======================================================
# CALENDAR VIEW
# ======================================================

def show_calendar():
    sw = get_sched_weeks(username)
    st.markdown("<div class='page-title'>📅 Scheduling</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Manage weekly templates</div>", unsafe_allow_html=True)

    yr = st.session_state.sched_yr
    mo = st.session_state.sched_mo

    c1, c2, c3 = st.columns([1, 6, 1])
    with c1:
        if st.button("◀", key="prev_cal"):
            st.session_state.sched_mo = 12 if mo == 1 else mo - 1
            if mo == 1: st.session_state.sched_yr = yr - 1
            st.rerun()
    with c2:
        st.markdown(f"## {datetime(yr, mo, 1).strftime('%B %Y')}")
    with c3:
        if st.button("▶", key="next_cal"):
            st.session_state.sched_mo = 1 if mo == 12 else mo + 1
            if mo == 12: st.session_state.sched_yr = yr + 1
            st.rerun()

    st.write("")
    headers = st.columns(7)
    for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        headers[i].markdown(f"**{d}**")

    for week in calendar.monthcalendar(yr, mo):
        cols = st.columns(7)
        for i, dn in enumerate(week):
            with cols[i]:
                if dn == 0:
                    st.write("")
                    continue

                curr = date(yr, mo, dn)
                ws = get_week_start(curr)
                has_data = ws in sw

                badge = "✓ Set" if has_data else "+ Add"
                css = "cell-sched" if has_data else "cell-empty"

                st.markdown(
                    f"""
                    <div class='cal-cell {css}'>
                    <div class='day-num'>{dn}</div>
                    <span class='day-badge {'badge-sched' if has_data else 'badge-empty'}'>
                    {badge}
                    </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if st.button("Edit" if has_data else "Add", key=f"day_{yr}_{mo}_{dn}"):
                    nav_to("week" if has_data else "add", ws=ws)

# ======================================================
# EDIT WEEK 
# ======================================================

def show_week_view():
    ws = st.session_state.sched_ws
    if ws is None:
        nav_to("calendar")
        return

    df_all = load_all(username)
    if df_all.empty:
        st.warning("No data found.")
        return

    # Use strict string comparison to fix the 'duplicates' bug
    ws_str = ws.strftime('%Y-%m-%d')
    df_all["_ws_str"] = df_all["Date"].apply(
        lambda x: (pd.to_datetime(x).date() - timedelta(days=pd.to_datetime(x).weekday())).strftime('%Y-%m-%d')
    )
    
    wd = df_all[df_all["_ws_str"] == ws_str].copy()

    st.markdown(f"<div class='page-title'>✏️ {week_label(ws)}</div>", unsafe_allow_html=True)

    if wd.empty:
        st.warning("No schedule found.")
        return

    wd = wd.drop(columns=["_ws_str"])
    budget = int(wd["Budget"].max()) if "Budget" in wd.columns else 300

    new_budget = st.number_input("Weekly Budget", value=budget, min_value=0, max_value=3000)
    edited = st.data_editor(wd, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save", type="primary", use_container_width=True):
            edited["Budget"] = new_budget
            others = df_all[df_all["_ws_str"] != ws_str].drop(columns=["_ws_str"])
            final = pd.concat([others, edited], ignore_index=True)
            save_all(final, username)
            st.success("Saved.")
            st.rerun()

    with c2:
        if st.button("◀ Back", use_container_width=True):
            nav_to("calendar")

# ======================================================
# ADD WEEK 
# ======================================================

def show_add_view():
    ws = st.session_state.sched_ws
    if ws is None:
        nav_to("calendar")
        return

    we = ws + timedelta(days=6)
    today = date.today()

    st.markdown(f"<div class='page-title'>➕ {ws.strftime('%d %b')} – {we.strftime('%d %b')}</div>", unsafe_allow_html=True)

    # EVENT SCANNING SECTION
    if ws >= today:
        st.subheader("🎫 Events This Week")
        col_scan1, col_scan2 = st.columns([3, 1])
        
        with col_scan2:
            if st.button("🔄 Scan Events", use_container_width=True):
                st.session_state.events_scanned = False
                st.session_state.week_events = None
                st.rerun()
        
        if not st.session_state.events_scanned:
            with st.spinner("🔍 Scanning for events..."):
                if scan_week:
                    try:
                        scanned_df = scan_week(ws)
                        st.session_state.week_events = scanned_df
                        st.session_state.events_scanned = True
                    except Exception as e:
                        st.error(f"Event scan error: {e}")
                        st.session_state.week_events = pd.DataFrame()
                        st.session_state.events_scanned = True
                else:
                    st.session_state.week_events = load_events_for_week(ws, username)
                    st.session_state.events_scanned = True
                st.rerun()
        
        events_df = st.session_state.week_events
        
        if events_df is not None and not events_df.empty:
            if 'Date' in events_df.columns:
                events_df = events_df.copy()
                if not isinstance(events_df['Date'].iloc[0], date):
                    events_df['Date'] = pd.to_datetime(events_df['Date']).dt.date
                events_df = events_df.sort_values('Date', ascending=True)
            
            st.success(f"Found **{len(events_df)} event(s)** this week!")
            
            with st.expander("🔍 Filters", expanded=False):
                fc1, fc2 = st.columns(2)
                with fc1:
                    if "Impact Score" in events_df.columns:
                        min_impact = int(events_df["Impact Score"].min())
                        max_impact = int(events_df["Impact Score"].max())
                        impact_range = st.slider("Impact Score", min_value=0, max_value=10, value=(min_impact, max_impact), key="add_impact_filter")
                    else:
                        impact_range = (0, 10)
                
                with fc2:
                    if "Distance (Miles)" in events_df.columns:
                        max_dist = float(events_df["Distance (Miles)"].max())
                        distance_filter = st.slider("Max Distance (Miles)", min_value=0.0, max_value=max(max_dist, 5.0), value=max(max_dist, 5.0), step=0.1, key="add_distance_filter")
                    else:
                        distance_filter = 10.0
            
            filtered_events = events_df.copy()
            if "Impact Score" in filtered_events.columns:
                filtered_events = filtered_events[(filtered_events["Impact Score"] >= impact_range[0]) & (filtered_events["Impact Score"] <= impact_range[1])]
            
            if "Distance (Miles)" in filtered_events.columns:
                filtered_events = filtered_events[filtered_events["Distance (Miles)"] <= distance_filter]
            
            if len(filtered_events) != len(events_df):
                st.caption(f"Showing {len(filtered_events)} of {len(events_df)} events (filtered)")
            
            tab_cards, tab_cal, tab_map = st.tabs(["🃏 Cards", "📅 Calendar", "🗺️ Map"])
            
            with tab_cards:
                if filtered_events.empty:
                    st.info("No events match the current filters.")
                else:
                    cols = st.columns(2)
                    for i, (_, ev) in enumerate(filtered_events.iterrows()):
                        score = int(ev.get('Impact Score', 0))
                        color = impact_color(score)
                        label = impact_label(score)
                        ev_date = ev['Date']
                        ev_date_str = ev_date.strftime('%a %d %b') if isinstance(ev_date, date) else str(ev_date)[:10]
                        distance = ev.get('Distance (Miles)', 0)
                        
                        with cols[i % 2]:
                            with st.container(border=True):
                                hc1, hc2 = st.columns([3, 1])
                                with hc1: st.markdown(f"**{ev.get('Event Name', 'Unknown')}**")
                                with hc2: st.markdown(f"<span style='background:{color};color:white;padding:4px 8px;border-radius:20px;font-size:0.72em;font-weight:700'>{label}</span>", unsafe_allow_html=True)
                                st.caption(f"📅 {ev_date_str} · 🕐 {ev.get('Start Time', '')}")
                                st.caption(f"📍 {ev.get('Venue', '')} · 📏 {distance:.1f} mi")
                                st.progress(score / 10, text=f"Impact: {score}/10")
            
            with tab_cal:
                event_map = {}
                for _, ev in filtered_events.iterrows():
                    d = ev['Date']
                    if isinstance(d, date):
                        event_map.setdefault(d, []).append(ev)
                
                for d in event_map:
                    event_map[d] = sorted(event_map[d], key=lambda x: x.get('Impact Score', 0), reverse=True)
                
                day_cols = st.columns(7)
                for i, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
                    day_cols[i].markdown(f"**{day_name}**")
                
                week_cols = st.columns(7)
                for i in range(7):
                    day_date = ws + timedelta(days=i)
                    day_events = event_map.get(day_date, [])
                    
                    with week_cols[i]:
                        if day_events:
                            max_score = max(int(x.get("Impact Score", 0)) for x in day_events)
                            bg = impact_color(max_score) + "22"
                            border = impact_color(max_score)
                        else:
                            bg = "#FFFFFF"
                            border = "#E5E7EB"
                        
                        event_names = "<br>".join([f"<span style='font-size:0.7em;color:{impact_color(int(x.get('Impact Score', 0)))}'>● {str(x.get('Event Name', ''))[:20]}</span>" for x in day_events])
                        min_height = max(100, 60 + len(day_events) * 18)
                        
                        st.markdown(
                            f"""
                            <div style='border:2px solid {border};border-radius:10px;padding:8px;
                                min-height:{min_height}px;background:{bg};text-align:center'>
                                <div style='font-size:1.4rem;font-weight:800;color:#1E293B'>{day_date.day}</div>
                                <div style='font-size:0.75em;color:#64748B;margin-bottom:4px'>{day_date.strftime('%b')}</div>
                                {event_names if day_events else "<span style='color:#CBD5E1;font-size:0.8em'>No events</span>"}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
            
            with tab_map:
                if "Lat" not in filtered_events.columns or "Lon" not in filtered_events.columns:
                    st.warning("No map coordinates available.")
                else:
                    map_df = filtered_events.dropna(subset=["Lat", "Lon"])
                    if map_df.empty:
                        st.warning("No map data for filtered events.")
                    else:
                        map_data = []
                        for _, row in map_df.iterrows():
                            score = int(row.get('Impact Score', 0))
                            if score >= 8: color = [220, 38, 38, 200]
                            elif score >= 5: color = [217, 119, 6, 200]
                            else: color = [22, 163, 74, 200]
                            
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
                            get_radius=150,
                            get_fill_color='color',
                            pickable=True
                        )
                        
                        avg_lat = sum(d['lat'] for d in map_data) / len(map_data)
                        avg_lon = sum(d['lon'] for d in map_data) / len(map_data)
                        view_state = pdk.ViewState(latitude=avg_lat, longitude=avg_lon, zoom=13)
                        
                        deck = pdk.Deck(
                            layers=[layer],
                            initial_view_state=view_state,
                            tooltip={
                                "html": "<b>{name}</b><br>📍 {venue}<br>⚡ Impact: {score}/10",
                                "style": {"backgroundColor": "#1E293B", "color": "white"}
                            }
                        )
                        st.pydeck_chart(deck, use_container_width=True)
                        st.caption("🔴 High (8-10) · 🟠 Medium (5-7) · 🟢 Low (1-4)")
            
            if any(filtered_events['Impact Score'] >= 8):
                st.warning("⚠️ **High-impact events detected!** Consider adjusting staffing levels.")
        else:
            st.info("✅ No significant events found for this week.")
        st.divider()

    st.subheader("📋 Weekly Schedule Template")
    budget = st.number_input("Weekly Budget (hours)", value=300, min_value=0, max_value=3000)

    rows = []
    for i in range(7):
        day_date = ws + timedelta(days=i)
        rows.append({
            "Date": pd.Timestamp(day_date),
            "Start": time(7, 0),
            "End": time(22, 0),
            "Minimum Staff": 4,
            "Maximum Employees": 6,
            "Minimum closing staff": 2
        })

    base = pd.DataFrame(rows)
    edited = st.data_editor(base, use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save New Week", type="primary", use_container_width=True):
            edited["Budget"] = budget
            df_all = load_all(username)

            if df_all.empty:
                final = edited
            else:
                final = pd.concat([df_all, edited], ignore_index=True)

            save_all(final, username)
            st.success("Week saved!")
            nav_to("calendar")
    
    with col2:
        if st.button("◀ Back", use_container_width=True):
            nav_to("calendar")

# ======================================================
# ROUTER
# ======================================================
view = st.session_state.sched_view
if view == "calendar": show_calendar()
elif view == "week": show_week_view()
elif view == "add": show_add_view()
