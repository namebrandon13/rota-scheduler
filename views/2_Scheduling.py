import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, date, time, timedelta
import pydeck as pdk
import math

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
SHEET_EMPLOYEES = "Employees" # Added to fetch contract hours

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

@st.cache_data(ttl=10)
def get_required_shifts(user):
    """Calculates the absolute minimum shifts required across all employees."""
    try:
        df = get_user_data(sheet_id, SHEET_EMPLOYEES, user)
        if df.empty: return 0
        
        def calc_shifts(hrs):
            try:
                h = float(hrs)
                if pd.isna(h): return 0
                return math.ceil(h / 9.0) # Assuming 9 is MAX_SHIFT_LENGTH
            except: return 0
        
        if 'Minimum Contractual Hours' in df.columns:
            return sum(df['Minimum Contractual Hours'].apply(calc_shifts))
        return 0
    except:
        return 0

def save_all(df, user):
    try:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').drop_duplicates(subset=['Date'], keep='last')

        df_upload = df.copy()
        if 'Date' in df_upload.columns:
            df_upload['Date'] = df_upload['Date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')
        for col in ['Start', 'End']:
            if col in df_upload.columns:
                df_upload[col] = df_upload[col].apply(lambda x: x.strftime('%H:%M:%S') if pd.notna(x) else '')
                
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

def display_compact_events(events_df):
    """A clean, compact event display for the Edit/Add screens."""
    if events_df is None or events_df.empty:
        st.info("✅ No significant events found for this week.")
        return
        
    st.markdown("##### 🎫 Weekly Events Context")
    for _, ev in events_df.iterrows():
        score = int(ev.get('Impact Score', 0))
        color = impact_color(score)
        label = impact_label(score)
        ev_date = ev['Date']
        ev_date_str = ev_date.strftime('%A') if isinstance(ev_date, date) else str(ev_date)[:10]
        
        st.markdown(f"""
        <div style='border-left: 4px solid {color}; background: #F8FAFC; padding: 8px 12px; margin-bottom: 6px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;'>
            <div>
                <strong style='color: #1E293B;'>{ev.get('Event Name', 'Event')}</strong>
                <span style='color: #64748B; font-size: 0.85em; margin-left: 8px;'>📅 {ev_date_str} @ {ev.get('Start Time', '')}</span>
            </div>
            <span style='background:{color}; color:white; padding:2px 8px; border-radius:12px; font-size:0.75em; font-weight:bold;'>{label} IMPACT ({score}/10)</span>
        </div>
        """, unsafe_allow_html=True)

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
    
    # 1. Budget Input
    new_budget = st.number_input("Weekly Budget (hours)", value=budget, min_value=0, max_value=3000)
    st.divider()

    # 2. Contextual Events
    events_df = load_events_for_week(ws, username)
    display_compact_events(events_df)
    st.write("")

    # 3. Editable Table
    st.markdown("##### 📋 Adjust Daily Requirements")
    edited = st.data_editor(wd, use_container_width=True, hide_index=True)
    st.divider()

    # 4. Mathematical Validation
    required_shifts = get_required_shifts(username)
    max_shifts_allowed = int(edited['Maximum Employees'].sum()) if 'Maximum Employees' in edited.columns else 0
    
    st.markdown("### ⚖️ Shift Balance Check")
    sc1, sc2 = st.columns(2)
    sc1.metric("Minimum Shifts Required", required_shifts, help="Based on employees' minimum contractual hours")
    sc2.metric("Max Shifts Allowed", max_shifts_allowed, delta=max_shifts_allowed - required_shifts, help="Total of the 'Maximum Employees' column")
    
    can_save = True
    if max_shifts_allowed < required_shifts:
        st.error(f"⚠️ **Mathematical Impossibility:** You need at least {required_shifts} shifts to fulfill contracts, but your template only allows {max_shifts_allowed}. Please increase the 'Maximum Employees' limits in the table above.")
        can_save = False
    else:
        st.success("✅ Shift balance looks good! The AI solver will be able to process this.")

    # 5. Save/Back Controls
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Changes", type="primary", use_container_width=True, disabled=not can_save):
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

    # 1. Budget
    budget = st.number_input("Weekly Budget (hours)", value=300, min_value=0, max_value=3000)
    st.divider()

    # 2. Event Display (Pulled directly from your cloud database)
    events_df = load_events_for_week(ws, username)
    
    if events_df.empty:
        st.info("✅ No significant events found for this week in the database. (Go to the Events page to run a Live Scan if you need to fetch new ones).")
    else:
        display_compact_events(events_df)
        
    st.write("")

    # 3. Editable Table (With Rule-Based AI)
    st.markdown("##### 📋 Setup Daily Requirements")
    
    # --- Simple AI Logic for Pre-filling ---
    def apply_ai_rules(day_d, ev_df):
        min_s = 4; max_s = 6; min_c = 2
        if ev_df.empty: return min_s, max_s, min_c
        
        # Match events to this specific day
        day_ev = ev_df[ev_df['Date'] == day_d]
        if not day_ev.empty:
            top_impact = int(day_ev['Impact Score'].max())
            
            if 5 <= top_impact < 8: max_s = 8
            if top_impact >= 8: min_s = 6; max_s = 10
            
            # Closing rush logic
            late = day_ev[day_ev['Start Time'].astype(str) >= "18:00"]
            if not late.empty and top_impact >= 5:
                min_c = 3
                if top_impact >= 8: min_c = 4
                
        return min_s, max_s, min_c

    # --- Build the Rows ---
    rows = []
    for i in range(7):
        day_date = ws + timedelta(days=i)
        
        # Ask AI for the numbers based on events
        ai_min, ai_max, ai_close = apply_ai_rules(day_date, events_df)
        
        rows.append({
            "Date": pd.Timestamp(day_date),
            "Start": time(7, 0),
            "End": time(00, 0),
            "Minimum Staff": ai_min,
            "Maximum Employees": ai_max,
            "Minimum closing staff": ai_close
        })

    base = pd.DataFrame(rows)
    
    if not events_df.empty:
        st.info("💡 AI has pre-filled the table below based on the Event Impact Scores.")
        
    edited = st.data_editor(base, use_container_width=True, hide_index=True)
    st.divider()

    # 4. Mathematical Validation
    required_shifts = get_required_shifts(username)
    max_shifts_allowed = int(edited['Maximum Employees'].sum()) if 'Maximum Employees' in edited.columns else 0
    
    st.markdown("### ⚖️ Shift Balance Check")
    sc1, sc2 = st.columns(2)
    sc1.metric("Minimum Shifts Required", required_shifts, help="Based on employees' minimum contractual hours")
    sc2.metric("Max Shifts Allowed", max_shifts_allowed, delta=max_shifts_allowed - required_shifts, help="Total of the 'Maximum Employees' column")
    
    can_save = True
    if max_shifts_allowed < required_shifts:
        st.error(f"⚠️ **Mathematical Impossibility:** You need at least {required_shifts} shifts to fulfill contracts, but your template only allows {max_shifts_allowed}. Please increase the 'Maximum Employees' limits in the table above.")
        can_save = False
    else:
        st.success("✅ Shift balance looks good! The AI solver will be able to process this.")

    # 5. Save/Back Controls
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save New Week", type="primary", use_container_width=True, disabled=not can_save):
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
