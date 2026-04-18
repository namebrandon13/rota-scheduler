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

# ==============================================================
#              SMART SUGGESTION ENGINE
# ==============================================================

# Day-of-week retail traffic weights (normalized so sum ≈ 7.0)
# Derived from typical UK high-street footfall patterns
_RAW_DOW = {
    0: 0.80,   # Monday     — quiet recovery day
    1: 0.80,   # Tuesday    — still slow
    2: 0.85,   # Wednesday  — midweek uptick
    3: 0.90,   # Thursday   — late-night shopping in some areas
    4: 1.10,   # Friday     — pre-weekend rush
    5: 1.30,   # Saturday   — peak retail day
    6: 1.00,   # Sunday     — moderate (shorter hours too)
}
_DOW_SUM = sum(_RAW_DOW.values())
DOW_WEIGHTS = {k: v * 7.0 / _DOW_SUM for k, v in _RAW_DOW.items()}

AVG_SHIFT_LENGTH = 7.5   # midpoint of 6-9 hour shifts
MIN_SHIFT_LENGTH = 6
MAX_SHIFT_LENGTH = 9

def build_smart_suggestions(ws, user, target_budget=None):
    """
    Analyses the full workforce picture and returns intelligent per-day
    staffing suggestions plus a recommended weekly budget.
    
    When target_budget is provided, recalculates everything under budget
    pressure — fewer shifts on quiet days, dampened event response, but
    still prioritises high-impact events.
    
    HARD RULES (never broken):
      1. Store opens at 07:00, closes at 00:00
      2. Minimum 2 closing staff every day
      3. Second employee starts at 09:00 or 10:00 (enforced by solver)
    """

    # ── 1. LOAD ALL DATA ──────────────────────────────────
    emp_df = get_user_data(sheet_id, SHEET_EMPLOYEES, user)
    if emp_df.empty:
        return None
    emp_df.columns = emp_df.columns.str.strip()
    
    total_staff = len(emp_df)
    
    # Contractual totals
    emp_df['_min_hrs'] = pd.to_numeric(emp_df.get('Minimum Contractual Hours', 0), errors='coerce').fillna(0)
    emp_df['_max_hrs'] = pd.to_numeric(emp_df.get('Max Weekly Hours', 40), errors='coerce').fillna(40)
    total_min_hours = float(emp_df['_min_hrs'].sum())
    total_max_hours = float(emp_df['_max_hrs'].sum())
    
    # Full-time vs part-time split (heuristic: ≥ 30h = full-time)
    ft_count = int((emp_df['_min_hrs'] >= 30).sum())
    pt_count = total_staff - ft_count
    
    # Openers
    opener_count = 0
    if 'Opening Trained' in emp_df.columns:
        opener_count = int(emp_df['Opening Trained'].eq('Yes').sum())
    
    # ── 2. LOAD HOLIDAYS FOR THIS WEEK ────────────────────
    hol_df = get_user_data(sheet_id, "Holiday", user)
    holidays_by_date = {}   # date -> set of names/IDs on holiday
    if not hol_df.empty:
        try:
            hol_df.columns = hol_df.columns.str.strip()
            hol_df['Date'] = pd.to_datetime(hol_df['Date']).dt.date
            if 'Status' in hol_df.columns:
                approved = hol_df[hol_df['Status'].astype(str).str.lower() == 'approved']
                for _, row in approved.iterrows():
                    d = row['Date']
                    name = str(row.get('Name', row.get('Employee ID', '')))
                    holidays_by_date.setdefault(d, set()).add(name)
        except:
            pass
    
    # ── 3. LOAD EVENTS ────────────────────────────────────
    events_df = load_events_for_week(ws, user)
    
    # ── 4. NATURAL BUDGET (always computed for reference) ─
    contract_daily_base = total_min_hours / 7.0 / AVG_SHIFT_LENGTH
    natural_staffing = sum(
        max(2, math.ceil(contract_daily_base * DOW_WEIGHTS[dow]))
        for dow in range(7)
    ) * AVG_SHIFT_LENGTH
    natural_recommended = math.ceil(natural_staffing * 1.12)
    natural_recommended = max(natural_recommended, math.ceil(total_min_hours * 1.12))
    budget_floor = math.ceil(total_min_hours)
    budget_ceiling = math.ceil(total_max_hours)
    
    # ── 5. BUDGET PRESSURE ────────────────────────────────
    # pressure < 1.0 = tight budget → reduce shifts, dampen events
    # pressure = 1.0 = recommended → normal behaviour
    # pressure > 1.0 = generous → can staff up
    if target_budget is not None and natural_recommended > 0:
        pressure = target_budget / natural_recommended
        pressure = max(0.3, min(pressure, 2.0))
    else:
        pressure = 1.0
    
    # ── 6. PER-DAY ANALYSIS ───────────────────────────────
    day_suggestions = []
    total_event_padding_hours = 0
    total_dow_weight = sum(DOW_WEIGHTS[d] for d in range(7))
    
    for i in range(7):
        day_date = ws + timedelta(days=i)
        day_name = day_date.strftime('%A')
        dow = day_date.weekday()
        
        # ── Who is available this day? ──
        available_names = []
        fixed_working_count = 0
        
        for _, emp in emp_df.iterrows():
            emp_name = str(emp.get('Name', '')).strip()
            emp_id = str(emp.get('ID', '')).strip()
            
            # Unavailable day?
            unavail = str(emp.get('Unavailable Days', ''))
            if unavail not in ['nan', '', 'None'] and day_name in unavail:
                continue
            
            # Approved holiday?
            if day_date in holidays_by_date:
                if emp_name in holidays_by_date[day_date] or emp_id in holidays_by_date[day_date]:
                    continue
            
            available_names.append(emp_name)
            
            # Count fixed-shift employees (guaranteed to work this day)
            if str(emp.get('Fixed Shift Enabled', '')) == 'Yes':
                fixed_raw = str(emp.get('Fixed Weekly Shift', ''))
                if fixed_raw not in ['', 'nan', 'None'] and day_name in fixed_raw:
                    fixed_working_count += 1
        
        avail_count = len(available_names)
        
        # ── Event data for this day ──
        day_event_impact = 0
        day_event_name = ''
        day_event_is_evening = False
        if not events_df.empty:
            day_ev = events_df[events_df['Date'] == day_date]
            if not day_ev.empty:
                day_event_impact = int(day_ev['Impact Score'].max())
                day_event_name = str(day_ev.iloc[0].get('Event Name', ''))
                if 'Start Time' in day_ev.columns:
                    late = day_ev[day_ev['Start Time'].astype(str) >= "17:00"]
                    day_event_is_evening = not late.empty
        
        # ══════════════════════════════════════════════════
        # MINIMUM STAFF CALCULATION
        # ══════════════════════════════════════════════════
        
        if target_budget is not None:
            # BUDGET-DRIVEN: distribute target hours across days using DOW weights
            day_budget_hours = (target_budget / total_dow_weight) * DOW_WEIGHTS[dow]
            suggested_min = max(2, math.ceil(day_budget_hours / AVG_SHIFT_LENGTH))
        else:
            # NATURAL: contract-driven with DOW weighting
            weighted_base = contract_daily_base * DOW_WEIGHTS[dow]
            suggested_min = max(2, math.ceil(weighted_base))
        
        # Floor at fixed-shift employees (they're guaranteed in)
        suggested_min = max(suggested_min, fixed_working_count)
        
        # ── Event boost (scaled by budget pressure) ──
        event_bump = 0
        if day_event_impact >= 8:
            # HIGH IMPACT: always boost, even under tight budget
            if pressure >= 0.7:
                event_floor = max(suggested_min + 2, math.ceil(avail_count * 0.50 * min(1.0, pressure)))
                event_bump = max(1, event_floor - suggested_min)
            else:
                # Very tight: still give +1 for major events
                event_bump = 1
            suggested_min += event_bump
        elif day_event_impact >= 5 and pressure >= 0.85:
            # MEDIUM IMPACT: only boost if budget isn't too tight
            event_bump = 1
            suggested_min += 1
        elif day_event_impact >= 1 and pressure >= 1.0:
            # LOW IMPACT: only boost under comfortable budget
            event_bump = 1
            suggested_min += 1
        
        # HARD FLOOR: never below 2 (can't run a shop solo)
        if avail_count >= 2:
            suggested_min = max(2, suggested_min)
        
        # Cap at available staff
        suggested_min = min(suggested_min, avail_count)
        
        # ══════════════════════════════════════════════════
        # MAXIMUM STAFF CALCULATION
        # ══════════════════════════════════════════════════
        
        # Headroom scales with budget pressure
        if pressure >= 1.0:
            headroom = 2
        else:
            headroom = 1   # tight budget = less solver wiggle room
        
        # High-impact events always get extra headroom
        if day_event_impact >= 8:
            headroom += 1
        
        suggested_max = min(avail_count, suggested_min + headroom)
        suggested_max = max(suggested_max, suggested_min)
        
        # ══════════════════════════════════════════════════
        # CLOSING STAFF — HARD RULE: ALWAYS >= 2
        # ══════════════════════════════════════════════════
        
        suggested_closing = 2   # ABSOLUTE FLOOR — never broken
        
        # Only boost closers if budget allows AND evening event
        if day_event_is_evening and day_event_impact >= 8 and pressure >= 0.7:
            suggested_closing = 3
        elif day_event_is_evening and day_event_impact >= 5 and pressure >= 0.9:
            suggested_closing = 3
        
        # Closers can't exceed total staff on shift
        suggested_closing = min(suggested_closing, suggested_min)
        # Re-enforce the hard floor after the min() above
        suggested_closing = max(suggested_closing, 2)
        # If only 1 person available, that's the absolute physical limit
        if avail_count < 2:
            suggested_closing = min(suggested_closing, avail_count)
        
        # ── Track event padding for budget display ──
        event_padding_hours = event_bump * AVG_SHIFT_LENGTH
        total_event_padding_hours += event_padding_hours
        
        # ── Reasoning text ──
        reasons = []
        if target_budget is not None:
            day_hrs = (target_budget / total_dow_weight) * DOW_WEIGHTS[dow]
            reasons.append(f"Budget share: {day_hrs:.0f}h")
        else:
            reasons.append(f"Contract base: {contract_daily_base * DOW_WEIGHTS[dow]:.1f} shifts")
        reasons.append(f"Available: {avail_count}/{total_staff} staff")
        if fixed_working_count:
            reasons.append(f"Fixed shifts: {fixed_working_count}")
        if avail_count < total_staff:
            absent = total_staff - avail_count
            reasons.append(f"Absent: {absent} (holiday/unavailable)")
        if day_event_impact:
            dampened = " [dampened]" if pressure < 0.85 and day_event_impact < 8 else ""
            reasons.append(f"Event: {day_event_name[:25]} ({day_event_impact}/10){dampened}")
        if target_budget is not None and pressure < 1.0:
            reasons.append(f"Budget pressure: {pressure:.0%}")
        
        day_suggestions.append({
            'date': day_date,
            'day_name': day_name,
            'dow': dow,
            'available_count': avail_count,
            'fixed_working': fixed_working_count,
            'event_impact': day_event_impact,
            'event_name': day_event_name,
            'event_is_evening': day_event_is_evening,
            'suggested_min': suggested_min,
            'suggested_max': suggested_max,
            'suggested_closing': suggested_closing,
            'reasons': reasons,
        })
    
    # ── 7. BUDGET SUMMARY ─────────────────────────────────
    staffing_hours = sum(d['suggested_min'] * AVG_SHIFT_LENGTH for d in day_suggestions)
    solver_buffer = math.ceil(staffing_hours * 0.12)
    event_pad = math.ceil(total_event_padding_hours)
    budget_suggested = math.ceil(staffing_hours + solver_buffer + event_pad)
    budget_suggested = max(budget_suggested, budget_floor + solver_buffer)
    
    # ── 8. SHIFT BALANCE ──────────────────────────────────
    total_max_slots = sum(d['suggested_max'] for d in day_suggestions)
    min_shifts_required = sum(math.ceil(h / MAX_SHIFT_LENGTH) for h in emp_df['_min_hrs'] if h > 0)
    
    return {
        'days': day_suggestions,
        'total_staff': total_staff,
        'ft_count': ft_count,
        'pt_count': pt_count,
        'total_min_hours': total_min_hours,
        'total_max_hours': total_max_hours,
        'opener_count': opener_count,
        'budget_floor': budget_floor,
        'budget_suggested': budget_suggested,
        'budget_ceiling': budget_ceiling,
        'staffing_hours': staffing_hours,
        'solver_buffer': solver_buffer,
        'event_padding': event_pad,
        'min_shifts_required': min_shifts_required,
        'total_max_slots': total_max_slots,
        'pressure': pressure,
    }

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
    
    # Smart suggestion for budget comparison
    suggestions = build_smart_suggestions(ws, username)
    
    # 1. Budget Suggestion Panel
    if suggestions:
        st.markdown("##### 💰 Suggested Weekly Budget")
        
        bc1, bc2, bc3 = st.columns(3)
        bc1.metric("Floor", f"{suggestions['budget_floor']}h",
                   help="Contractual minimum — you must pay at least this")
        bc2.metric("Recommended", f"{suggestions['budget_suggested']}h",
                   help="Gives the solver enough room to build an optimal rota")
        bc3.metric("Ceiling", f"{suggestions['budget_ceiling']}h",
                   help="Theoretical max if every employee worked maximum hours")
        
        if budget < suggestions['budget_floor']:
            st.warning(f"⚠️ Current budget ({budget}h) is below the contractual floor ({suggestions['budget_floor']}h).")
        
        new_budget = st.number_input(
            "Weekly Budget (hours)",
            value=budget,
            min_value=0,
            max_value=3000,
            help=f"💡 Recommended: {suggestions['budget_suggested']}h"
        )
    else:
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
    if suggestions:
        required_shifts = suggestions['min_shifts_required']
    else:
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
    budget_key = f'budget_override_{ws}'

    st.markdown(f"<div class='page-title'>➕ {ws.strftime('%d %b')} – {we.strftime('%d %b')}</div>", unsafe_allow_html=True)

    # ── 1. GENERATE SMART SUGGESTIONS ─────────────────────
    # If manager has set a custom budget, recalculate with pressure
    budget_override = st.session_state.get(budget_key, None)
    suggestions = build_smart_suggestions(ws, username, target_budget=budget_override)
    
    if suggestions is None:
        st.error("No employees found. Please add employees first.")
        if st.button("◀ Back", use_container_width=True):
            nav_to("calendar")
        return
    
    # ── 2. WORKFORCE OVERVIEW PANEL ───────────────────────
    st.markdown("##### 📊 Workforce Analysis")
    
    ov1, ov2, ov3, ov4 = st.columns(4)
    ov1.metric("Total Staff", suggestions['total_staff'],
               help=f"{suggestions['ft_count']} full-time, {suggestions['pt_count']} part-time")
    ov2.metric("Contract Hours", f"{suggestions['total_min_hours']:.0f}h",
               help="Sum of all employees' minimum contractual hours")
    ov3.metric("Max Capacity", f"{suggestions['total_max_hours']:.0f}h",
               help="Sum of all employees' maximum weekly hours")
    ov4.metric("Openers Trained", suggestions['opener_count'])
    
    st.write("")
    
    # ── 3. EVENTS CONTEXT ─────────────────────────────────
    events_df = load_events_for_week(ws, username)
    display_compact_events(events_df)
    st.write("")
    
    # ── 4. BUDGET SUGGESTION ──────────────────────────────
    st.markdown("##### 💰 Suggested Weekly Budget")
    
    bc1, bc2, bc3 = st.columns(3)
    bc1.metric("Floor", f"{suggestions['budget_floor']}h",
               help="Contractual minimum — you must pay at least this")
    bc2.metric("Recommended", f"{suggestions['budget_suggested']}h",
               help="Gives the solver enough room to build an optimal rota")
    bc3.metric("Ceiling", f"{suggestions['budget_ceiling']}h",
               help="Theoretical max if every employee worked maximum hours")
    
    with st.expander("📐 Budget Breakdown"):
        st.markdown(f"""
        **How the recommended budget was calculated:**
        
        | Component | Hours |
        |-----------|-------|
        | Staffing base (min staff × {AVG_SHIFT_LENGTH}h avg shift) | {suggestions['staffing_hours']:.0f}h |
        | Solver flexibility buffer (12%) | +{suggestions['solver_buffer']}h |
        | Event staffing padding | +{suggestions['event_padding']}h |
        | **Recommended total** | **{suggestions['budget_suggested']}h** |
        
        *The floor of {suggestions['budget_floor']}h is the absolute contractual minimum. 
        The recommended budget adds flexibility so the solver can optimize shift lengths 
        and handle edge cases without hitting a hard wall.*
        """)
    
    # ── Budget input with REFRESH button ──
    in1, in2, in3 = st.columns([3, 1, 1])
    with in1:
        budget = st.number_input(
            "Weekly Budget (hours)",
            value=budget_override if budget_override is not None else suggestions['budget_suggested'],
            min_value=0,
            max_value=3000,
            help="Set your budget, then click Recalculate to adjust all staffing suggestions."
        )
    with in2:
        st.write("")  # vertical alignment
        if st.button("🔄 Recalculate", use_container_width=True,
                      help="Recalculates min/max/closing for every day based on your budget"):
            st.session_state[budget_key] = budget
            st.rerun()
    with in3:
        st.write("")
        if budget_override is not None:
            if st.button("↩️ Reset", use_container_width=True,
                          help="Reset to recommended budget"):
                if budget_key in st.session_state:
                    del st.session_state[budget_key]
                st.rerun()
    
    # ── Budget pressure feedback ──
    if budget < suggestions['budget_floor']:
        st.warning(f"⚠️ Budget ({budget}h) is below the contractual floor ({suggestions['budget_floor']}h). The solver may fail to meet minimum hours.")
    
    pressure = suggestions.get('pressure', 1.0)
    if budget_override is not None:
        if pressure < 0.75:
            st.error(f"🔴 **Very tight budget** ({pressure:.0%} of recommended). "
                     f"Staffing heavily reduced. Medium/low event impact ignored. Only high-impact events get a boost.")
        elif pressure < 0.90:
            st.warning(f"🟡 **Tight budget** ({pressure:.0%} of recommended). "
                       f"Staffing reduced on quiet days. Low-impact events ignored.")
        elif pressure < 1.05:
            st.success(f"🟢 **Comfortable budget** ({pressure:.0%} of recommended). "
                       f"All event impacts factored in.")
        else:
            st.success(f"🟢 **Generous budget** ({pressure:.0%} of recommended). "
                       f"Full staffing with extra headroom.")
    
    st.divider()
    
    # ── 5. PER-DAY SUGGESTIONS TABLE ──────────────────────
    st.markdown("##### 📋 Daily Staffing Suggestions")
    if budget_override is not None:
        st.caption(f"Recalculated for {budget}h budget (pressure: {pressure:.0%}). "
                   f"Hard rules enforced: Start 07:00 · End 00:00 · Min 2 closers.")
    else:
        st.caption("Pre-filled using workforce analysis, contracts, availability, holidays and events.")
    
    rows = []
    for day in suggestions['days']:
        rows.append({
            "Date": pd.Timestamp(day['date']),
            "Start": time(7, 0),
            "End": time(0, 0),
            "Minimum Staff": day['suggested_min'],
            "Maximum Employees": day['suggested_max'],
            "Minimum closing staff": day['suggested_closing'],
        })
    
    base = pd.DataFrame(rows)
    edited = st.data_editor(base, use_container_width=True, hide_index=True)
    
    # ── 6. PER-DAY REASONING ──────────────────────────────
    with st.expander("🧠 Why these numbers?"):
        for day in suggestions['days']:
            d = day['date']
            impact = day['event_impact']
            
            if impact >= 8:
                border_color = "#DC2626"
            elif impact >= 5:
                border_color = "#D97706"
            elif impact >= 1:
                border_color = "#16A34A"
            else:
                border_color = "#E2E8F0"
            
            reason_text = " · ".join(day['reasons'])
            
            st.markdown(f"""
            <div style='border-left: 4px solid {border_color}; padding: 6px 12px; margin-bottom: 4px;
                         background: #F8FAFC; border-radius: 4px; font-size: 0.85em;'>
                <strong>{day['day_name']} {d.strftime('%d %b')}</strong> — 
                Min: {day['suggested_min']} · Max: {day['suggested_max']} · Close: {day['suggested_closing']}
                <br><span style='color: #64748B;'>{reason_text}</span>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    
    # ── 7. SHIFT BALANCE CHECK ────────────────────────────
    required_shifts = suggestions['min_shifts_required']
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

    # ── 8. SAVE / BACK ────────────────────────────────────
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
            # Clean up the override
            if budget_key in st.session_state:
                del st.session_state[budget_key]
            nav_to("calendar")
    
    with col2:
        if st.button("◀ Back", use_container_width=True):
            if budget_key in st.session_state:
                del st.session_state[budget_key]
            nav_to("calendar")

# ======================================================
# ROUTER
# ======================================================
view = st.session_state.sched_view
if view == "calendar": show_calendar()
elif view == "week": show_week_view()
elif view == "add": show_add_view()
