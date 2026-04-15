import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, date, time, timedelta

# ======================================================
# CLOUD READY PATHS
# ======================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE_PATH = os.path.join(BASE_DIR, "Book(Employees)_01.xlsx")
EVENTS_FILE = os.path.join(BASE_DIR, "EventsData.xlsx")
SHEET = "Shift Templates"

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
    """Convert any date/datetime to the Monday of that week as a date object."""
    if isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, pd.Timestamp):
        d = d.date()
    return d - timedelta(days=d.weekday())


@st.cache_data(ttl=10)
def load_all():
    if not os.path.exists(FILE_PATH):
        return pd.DataFrame()
    try:
        df = pd.read_excel(FILE_PATH, sheet_name=SHEET)
        df.columns = df.columns.str.strip()
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Start", "End"]:
            try:
                df[col] = pd.to_datetime(df[col].astype(str)).dt.time
            except:
                pass
        return df
    except:
        return pd.DataFrame()


def load_events_for_week(ws):
    """Load events from EventsData.xlsx for a specific week"""
    if not os.path.exists(EVENTS_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_excel(EVENTS_FILE)
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        we = ws + timedelta(days=6)
        # Filter to this week only
        df = df[(df['Date'] >= ws) & (df['Date'] <= we)]
        return df.sort_values('Date')
    except:
        return pd.DataFrame()


def save_all(df):
    with pd.ExcelWriter(
        FILE_PATH,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace"
    ) as writer:
        df.to_excel(writer, sheet_name="Shift Templates", index=False)
    st.cache_data.clear()


def nav_to(view, ws=None):
    st.session_state.sched_view = view
    if ws is not None:
        st.session_state.sched_ws = ws
    # Reset event scan state when navigating
    if view != "add":
        st.session_state.week_events = None
        st.session_state.events_scanned = False
    st.rerun()


def week_label(ws):
    we = ws + timedelta(days=6)
    wn = (ws + timedelta(days=3)).isocalendar()[1]
    return f"Week {wn} · {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}"


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

# ======================================================
# SIDEBAR
# ======================================================

def get_sched_weeks():
    df = load_all()
    if df.empty:
        return set()
    return {get_week_start(d) for d in df["Date"]}


def render_sidebar():
    sw = get_sched_weeks()
    with st.sidebar:
        st.markdown("### 📊 Scheduling")
        st.metric("Weeks Configured", len(sw))

render_sidebar()

# ======================================================
# CALENDAR VIEW
# ======================================================

def show_calendar():
    sw = get_sched_weeks()

    st.markdown(
        "<div class='page-title'>📅 Scheduling</div>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<div class='page-sub'>Manage weekly templates</div>",
        unsafe_allow_html=True
    )

    yr = st.session_state.sched_yr
    mo = st.session_state.sched_mo

    c1, c2, c3 = st.columns([1, 6, 1])

    with c1:
        if st.button("◀", key="prev_cal"):
            st.session_state.sched_mo = 12 if mo == 1 else mo - 1
            if mo == 1:
                st.session_state.sched_yr = yr - 1
            st.rerun()

    with c2:
        st.markdown(f"## {datetime(yr, mo, 1).strftime('%B %Y')}")

    with c3:
        if st.button("▶", key="next_cal"):
            st.session_state.sched_mo = 1 if mo == 12 else mo + 1
            if mo == 12:
                st.session_state.sched_yr = yr + 1
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

                if st.button(
                    "Edit" if has_data else "Add",
                    key=f"day_{yr}_{mo}_{dn}"
                ):
                    nav_to("week" if has_data else "add", ws=ws)

# ======================================================
# EDIT WEEK
# ======================================================

def show_week_view():
    ws = st.session_state.sched_ws

    if ws is None:
        nav_to("calendar")
        return

    df_all = load_all()

    if df_all.empty:
        st.warning("No data found.")
        return

    df_all["_ws"] = df_all["Date"].apply(lambda x: get_week_start(x))
    wd = df_all[df_all["_ws"] == ws].copy()

    st.markdown(
        f"<div class='page-title'>✏️ {week_label(ws)}</div>",
        unsafe_allow_html=True
    )

    if wd.empty:
        st.warning("No schedule found.")
        return

    wd = wd.drop(columns=["_ws"])

    budget = int(wd["Budget"].max()) if "Budget" in wd.columns else 300

    new_budget = st.number_input(
        "Weekly Budget",
        value=budget,
        min_value=0,
        max_value=3000
    )

    edited = st.data_editor(
        wd,
        use_container_width=True,
        hide_index=True
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("💾 Save", type="primary", use_container_width=True):
            edited["Budget"] = new_budget
            others = df_all[df_all["_ws"] != ws].drop(columns=["_ws"])
            final = pd.concat([others, edited], ignore_index=True)
            save_all(final)
            st.success("Saved.")
            st.rerun()

    with c2:
        if st.button("◀ Back", use_container_width=True):
            nav_to("calendar")

# ======================================================
# ADD WEEK (with Event Scanning)
# ======================================================

def show_add_view():
    ws = st.session_state.sched_ws

    if ws is None:
        nav_to("calendar")
        return

    we = ws + timedelta(days=6)
    today = date.today()

    st.markdown(
        f"<div class='page-title'>➕ {ws.strftime('%d %b')} – {we.strftime('%d %b')}</div>",
        unsafe_allow_html=True
    )

    # ======================================================
    # EVENT SCANNING SECTION
    # ======================================================
    
    # Only scan future weeks
    if ws >= today:
        st.subheader("🎫 Events This Week")
        
        # Auto-scan on first load or manual rescan
        col_scan1, col_scan2 = st.columns([3, 1])
        
        with col_scan2:
            if st.button("🔄 Scan Events", use_container_width=True):
                st.session_state.events_scanned = False
                st.session_state.week_events = None
                st.rerun()
        
        # Perform scan if not done yet
        if not st.session_state.events_scanned:
            with st.spinner("🔍 Scanning for events..."):
                if scan_week:
                    try:
                        # Scan this week's events
                        scanned_df = scan_week(ws)
                        st.session_state.week_events = scanned_df
                        st.session_state.events_scanned = True
                    except Exception as e:
                        st.error(f"Event scan error: {e}")
                        st.session_state.week_events = pd.DataFrame()
                        st.session_state.events_scanned = True
                else:
                    # Fallback: load from existing file
                    st.session_state.week_events = load_events_for_week(ws)
                    st.session_state.events_scanned = True
                st.rerun()
        
        # Display events
        events_df = st.session_state.week_events
        
        if events_df is not None and not events_df.empty:
            st.success(f"Found **{len(events_df)} event(s)** this week!")
            
            for _, ev in events_df.iterrows():
                score = int(ev.get('Impact Score', 0))
                color = impact_color(score)
                label = impact_label(score)
                ev_date = ev['Date']
                if isinstance(ev_date, date):
                    ev_date_str = ev_date.strftime('%a %d %b')
                else:
                    ev_date_str = str(ev_date)[:10]
                
                alert_class = "event-alert event-high" if score >= 8 else "event-alert"
                
                st.markdown(
                    f"""
                    <div class='{alert_class}'>
                        <div style='display:flex;justify-content:space-between;align-items:center'>
                            <div>
                                <strong>{ev.get('Event Name', 'Unknown')}</strong><br>
                                <span style='color:#6B7280;font-size:0.9em'>
                                    📅 {ev_date_str} · 🕐 {ev.get('Start Time', '')} · 📍 {ev.get('Venue', '')}
                                </span>
                            </div>
                            <div style='background:{color};color:white;padding:4px 12px;border-radius:20px;font-weight:700;font-size:0.8em'>
                                {label} ({score}/10)
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            if any(events_df['Impact Score'] >= 8):
                st.warning("⚠️ **High-impact events detected!** Consider adjusting staffing levels for these days.")
        else:
            st.info("✅ No significant events found for this week.")
        
        st.divider()
    
    # ======================================================
    # SCHEDULE TEMPLATE SECTION
    # ======================================================
    
    st.subheader("📋 Weekly Schedule Template")

    budget = st.number_input(
        "Weekly Budget (hours)",
        value=300,
        min_value=0,
        max_value=3000
    )

    # Create default rows for each day of the week
    rows = []
    for i in range(7):
        day_date = ws + timedelta(days=i)
        
        # Check if there's a high-impact event on this day
        event_note = ""
        if st.session_state.week_events is not None and not st.session_state.week_events.empty:
            day_events = st.session_state.week_events[
                st.session_state.week_events['Date'] == day_date
            ]
            if not day_events.empty:
                max_score = day_events['Impact Score'].max()
                if max_score >= 8:
                    event_note = " ⚠️"
        
        rows.append({
            "Date": pd.Timestamp(day_date),
            "Start": time(7, 0),
            "End": time(22, 0),
            "Minimum Staff": 4,
            "Maximum Employees": 6,
            "Minimum closing staff": 2
        })

    base = pd.DataFrame(rows)

    edited = st.data_editor(
        base,
        use_container_width=True,
        hide_index=True
    )

    # ======================================================
    # SAVE BUTTON
    # ======================================================
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 Save New Week", type="primary", use_container_width=True):
            edited["Budget"] = budget
            df_all = load_all()

            if df_all.empty:
                final = edited
            else:
                final = pd.concat([df_all, edited], ignore_index=True)

            save_all(final)
            st.success("Week saved!")
            nav_to("calendar")
    
    with col2:
        if st.button("◀ Back", use_container_width=True):
            nav_to("calendar")

# ======================================================
# ROUTER
# ======================================================

view = st.session_state.sched_view

if view == "calendar":
    show_calendar()
elif view == "week":
    show_week_view()
elif view == "add":
    show_add_view()
