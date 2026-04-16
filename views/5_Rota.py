import streamlit as st
import pandas as pd
import os, time, io, calendar
from datetime import datetime, date, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# Import your new database handler
from gsheets_db import get_sheet_data, write_sheet_data, get_gspread_client

# ======================================================
# AUTH & SETUP
# ======================================================

# Verify user is logged in and has a sheet ID assigned
if 'sheet_id' not in st.session_state:
    st.error("Please log in to access the Rota Dashboard.")
    st.stop()

sheet_id = st.session_state['sheet_id']

SHEET_EMPLOYEES = "Employees"
SHEET_TEMPLATES = "Shift Template"

# ======================================================
# ROLE COLORS
# ======================================================
ROLE_COLORS = {
    'Manager':      {'bg':'#DBEAFE','text':'#1D4ED8','bar':'#2563EB'},
    'Shift Leader': {'bg':'#EDE9FE','text':'#6D28D9','bar':'#7C3AED'},
    'Team Leader':  {'bg':'#CFFAFE','text':'#0E7490','bar':'#0891B2'},
    'Associate':    {'bg':'#F1F5F9','text':'#374151','bar':'#64748B'},
}
DRC = {'bg':'#F1F5F9','text':'#374151','bar':'#94A3B8'}

# ======================================================
# STYLES
# ======================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.cal-cell{border-radius:14px;padding:14px 6px 8px;text-align:center;min-height:125px;
  margin-bottom:2px;border:1.5px solid transparent;box-shadow:0 1px 4px rgba(0,0,0,0.06);}
.cell-rota {background:#EFF6FF;border-color:#BFDBFE;}
.cell-sched{background:#FFFBEB;border-color:#FDE68A;}
.cell-empty{background:#F8FAFC;border-color:#E2E8F0;}
.cell-today{outline:2.5px solid #2563EB;outline-offset:2px;border-radius:14px;}
.day-num{font-size:2.6em;font-weight:900;line-height:1;margin-bottom:6px;
  color:#1E293B;letter-spacing:-0.03em;}
.cell-empty .day-num{color:#CBD5E1;}
.day-badge{display:inline-block;font-size:0.84em;font-weight:700;padding:3px 10px;
  border-radius:20px;letter-spacing:0.06em;text-transform:uppercase;}
.badge-rota {background:#16A34A;color:#fff;}
.badge-sched{background:#D97706;color:#fff;}
.badge-empty{background:#E2E8F0;color:#64748B;}
.day-info{font-size:0.88em;color:#2563EB;font-weight:600;margin-top:4px;}
.cal-hdr{text-align:center;font-size:0.78em;font-weight:700;letter-spacing:0.09em;
  text-transform:uppercase;padding:8px 2px;border-radius:8px;margin-bottom:6px;}
div[data-testid="stButton"]>button{border-radius:8px;font-weight:600;
  font-size:0.80em;letter-spacing:0.02em;transition:all 0.15s ease;}
div[data-testid="stButton"]>button:hover{transform:translateY(-1px);
  box-shadow:0 4px 14px rgba(37,99,235,0.20);}
div[data-testid="stMetric"]{background:white;border:1px solid #E2E8F0;
  border-radius:12px;padding:14px 18px;box-shadow:0 1px 4px rgba(0,0,0,0.05);}
div[data-testid="stMetric"] label{color:#64748B;font-size:0.78em;font-weight:600;
  text-transform:uppercase;letter-spacing:0.04em;}
div[data-testid="stMetric"] div[data-testid="stMetricValue"]{color:#1E293B;
  font-size:1.7em;font-weight:800;}
.tl-track{background:#EFF6FF;border-radius:8px;height:30px;position:relative;
  overflow:hidden;border:1px solid #DBEAFE;}
.tl-bar{position:absolute;top:0;height:100%;border-radius:7px;
  display:flex;align-items:center;justify-content:center;
  color:white;font-size:0.75em;font-weight:700;min-width:28px;}
.role-badge{display:inline-block;font-size:0.68em;font-weight:600;padding:2px 8px;
  border-radius:20px;margin-left:5px;vertical-align:middle;}
.emp-row{display:flex;justify-content:space-between;align-items:center;
  background:white;border-radius:10px;padding:10px 14px;margin:5px 0;
  border:1px solid #E2E8F0;box-shadow:0 1px 3px rgba(0,0,0,0.04);}
section[data-testid="stSidebar"]{background:#F0F7FF;}
.page-title{font-size:2em;font-weight:900;color:#1E293B;
  letter-spacing:-0.03em;margin-bottom:2px;}
.page-sub{font-size:0.88em;color:#64748B;margin-bottom:14px;}
</style>
""", unsafe_allow_html=True)

# ======================================================
# SESSION STATE
# ======================================================
for k,v in {'view':'calendar','cal_year':datetime.today().year,
             'cal_month':datetime.today().month,
             'selected_date':None,'week_start':None}.items():
    if k not in st.session_state: st.session_state[k]=v

# ======================================================
# HELPER FUNCTIONS
# ======================================================
def get_week_start(d):
    if isinstance(d, datetime): d = d.date()
    return d - timedelta(days=d.weekday())

def get_all_sheet_names():
    try:
        client = get_gspread_client()
        sh = client.open_by_key(sheet_id)
        return [ws.title for ws in sh.worksheets()]
    except Exception as e:
        st.error(f"Error fetching sheets: {e}")
        return []

@st.cache_data(ttl=30)
def get_scheduling_weeks():
    try:
        df = get_sheet_data(sheet_id, SHEET_TEMPLATES)
        if df.empty: return set()
        df['Date'] = pd.to_datetime(df['Date'])
        return {(d - timedelta(days=d.weekday())).date() for d in df['Date']}
    except: return set()

@st.cache_data(ttl=10)
def get_generated_weeks():
    r = {}
    sheet_names = get_all_sheet_names()
    for sheet in sheet_names:
        # Optimization: Only process sheets that look like Rotas (e.g., "Week X")
        if sheet in ["Employees", "Shift Templates", "Events", "Holidays", "Data"]: continue
        if "Week" not in sheet: continue
        
        try:
            df = get_sheet_data(sheet_id, sheet)
            if df.empty: continue
            
            dc = [c for c in df.columns if c not in ('Name','Employee ID','Total Weekly Hours')]
            if dc:
                try:
                    d = datetime.strptime(dc[0].split(' ')[0], '%Y-%m-%d').date()
                    r[get_week_start(d)] = sheet
                except: pass
        except: pass
    return r

@st.cache_data(ttl=10)
def get_week_total_hours():
    r = {}
    gen_weeks = get_generated_weeks()
    for ws, sheet in gen_weeks.items():
        try:
            df = get_sheet_data(sheet_id, sheet)
            if 'Total Weekly Hours' in df.columns:
                r[ws] = int(pd.to_numeric(df['Total Weekly Hours'], errors='coerce').sum())
        except: pass
    return r

@st.cache_data(ttl=30)
def get_schedule_budget(ws):
    try:
        df = get_sheet_data(sheet_id, SHEET_TEMPLATES)
        if df.empty: return None
        df.columns = df.columns.str.strip()
        df['Date'] = pd.to_datetime(df['Date'])
        df['_ws'] = df['Date'].apply(lambda x: (x.date() - timedelta(days=x.weekday())))
        w = df[df['_ws'] == ws]
        return int(w['Budget'].max()) if not w.empty and 'Budget' in w.columns else None
    except: return None

@st.cache_data(ttl=60)
def get_employee_roles():
    try:
        df = get_sheet_data(sheet_id, SHEET_EMPLOYEES)
        if df.empty: return {}
        df.columns = df.columns.str.strip()
        return {str(n).strip(): str(r).strip() for n, r in zip(df['Name'], df['Designation'])}
    except: return {}

def load_week_rota(sn):
    try: return get_sheet_data(sheet_id, sn)
    except: return None

def calc_hours(s):
    if pd.isna(s) or not isinstance(s, str) or ' - ' not in s: return 0.0
    try:
        a, b = s.split(' - ')
        sh, sm = map(int, a.split(':'))
        eh, em = map(int, b.split(':'))
        if eh == 0: eh = 24
        return max(0, (eh + em/60) - (sh + sm/60))
    except: return 0.0

def recalc(df):
    dc = [c for c in df.columns if c not in ('Name','Employee ID','Total Weekly Hours')]
    for i, row in df.iterrows():
        df.at[i, 'Total Weekly Hours'] = sum(calc_hours(row[c]) for c in dc)
    return df

def create_pdf(df, wn):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter))
    styles = getSampleStyleSheet()
    el = [Paragraph(f"<b>Rota: {wn}</b>", styles['Title'])]
    data = [df.columns.tolist()] + [[str(v) if pd.notna(v) else '' for v in r] for _, r in df.iterrows()]
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2563EB')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 10),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#EFF6FF'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#BFDBFE')),
        ('FONTSIZE', (0,1), (-1,-1), 8),
    ]))
    el.append(t)
    doc.build(el)
    buf.seek(0)
    return buf

def clear_caches():
    for fn in [get_generated_weeks, get_week_total_hours,
               get_scheduling_weeks, get_schedule_budget, get_employee_roles]:
        fn.clear()

def nav_to(view, sel_date=None, week_start=None):
    st.session_state.view = view
    if sel_date is not None: st.session_state.selected_date = sel_date
    if week_start is not None: st.session_state.week_start = week_start
    clear_caches()
    st.rerun()

# ======================================================
# SIDEBAR
# ======================================================
def render_sidebar():
    view = st.session_state.view
    ws = st.session_state.week_start
    gen = get_generated_weeks()
    sched = get_scheduling_weeks()
    hrs_map = get_week_total_hours()
    
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📊 Overview")
        s1, s2 = st.columns(2)
        s1.metric("Rotas Ready", len(gen))
        s2.metric("Weeks Planned", len(sched))
        
        if view in ('week', 'day') and ws:
            we = ws + timedelta(days=6)
            st.markdown("---")
            st.markdown(
                f"<div style='background:#EFF6FF;border-radius:10px;padding:10px 12px;"
                f"border:1px solid #BFDBFE;margin-bottom:8px'>"
                f"<b style='color:#1D4ED8'>📅 {ws.strftime('%d %b')} – {we.strftime('%d %b')}</b></div>",
                unsafe_allow_html=True)
            
            budget = get_schedule_budget(ws)
            total_h = hrs_map.get(ws, 0)
            
            if budget:
                pct = min(total_h / budget, 1.0)
                st.markdown(f"**💰 Budget:** {total_h}h / {budget}h")
                st.progress(pct)
                if pct >= 0.95:
                    st.warning("⚠️ Near budget limit")
            else:
                st.markdown(f"**⏱️ Hours Used:** {total_h}h")
            
            sheet = gen.get(ws)
            if sheet:
                df = load_week_rota(sheet)
                if df is not None:
                    dc = [c for c in df.columns if c not in ('Name','Employee ID','Total Weekly Hours')]
                    st.markdown("**👥 Daily Staffing**")
                    for col in dc:
                        try:
                            d = datetime.strptime(col.split(' ')[0], '%Y-%m-%d').date()
                            w2 = int((df[col] != 'OFF').sum() - df[col].isna().sum())
                            is_sel = (view == 'day' and st.session_state.selected_date == d)
                            bg = "#2563EB" if is_sel else "white"
                            tc = "white" if is_sel else "#374151"
                            ev = "🎫 " if '[Event' in col else ""
                            st.markdown(
                                f"<div style='display:flex;justify-content:space-between;"
                                f"background:{bg};color:{tc};border-radius:8px;"
                                f"padding:6px 10px;margin:3px 0;font-size:0.85em;"
                                f"border:1px solid #E2E8F0'>"
                                f"<span>{ev}{d.strftime('%a %d %b')}</span>"
                                f"<b>{w2} staff</b></div>",
                                unsafe_allow_html=True)
                        except: pass

render_sidebar()

# ======================================================
# VIEW 1: CALENDAR
# ======================================================
def show_calendar():
    sw = get_scheduling_weeks()
    gw = get_generated_weeks()
    hm = get_week_total_hours()
    
    st.markdown("<div class='page-title'>🚀 Rota Dashboard</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Click any day to view its rota or generate one</div>", unsafe_allow_html=True)
    
    lc = st.columns([1.1, 1.3, 1.1, 5])
    lc[0].markdown("🟢 **Rota ready**")
    lc[1].markdown("🟡 **Schedulable**")
    lc[2].markdown("⬜ **No template**")
    st.write("")
    
    yr = st.session_state.cal_year
    mo = st.session_state.cal_month
    
    c1, c2, c3 = st.columns([1, 6, 1])
    with c1:
        if st.button("◀", use_container_width=True, key="cp"):
            st.session_state.cal_month = 12 if mo == 1 else mo - 1
            if mo == 1: st.session_state.cal_year = yr - 1
            st.rerun()
    with c2:
        st.markdown(f"<h2 style='text-align:center;margin:0;color:#1E293B;font-weight:900;"
                    f"letter-spacing:-0.03em'>{datetime(yr, mo, 1).strftime('%B %Y')}</h2>",
                    unsafe_allow_html=True)
    with c3:
        if st.button("▶", use_container_width=True, key="cn"):
            st.session_state.cal_month = 1 if mo == 12 else mo + 1
            if mo == 12: st.session_state.cal_year = yr + 1
            st.rerun()
    
    st.write("")
    DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    hc = st.columns(7)
    for i, dn in enumerate(DAYS):
        bg = "#FEE2E2" if i >= 5 else "#EFF6FF"
        tc = "#DC2626" if i >= 5 else "#1D4ED8"
        hc[i].markdown(f"<div class='cal-hdr' style='background:{bg};color:{tc}'>{dn}</div>", unsafe_allow_html=True)
    
    today = date.today()
    for wr in calendar.monthcalendar(yr, mo):
        cols = st.columns(7)
        for di, dn2 in enumerate(wr):
            with cols[di]:
                if dn2 == 0:
                    st.markdown("<div style='min-height:128px'></div>", unsafe_allow_html=True)
                    continue
                
                curr = date(yr, mo, dn2)
                ws = get_week_start(curr)
                hr = ws in gw
                sc = ws in sw
                it = curr == today
                
                if hr:
                    cc, bc, bt = 'cell-rota', 'badge-rota', '✓ Rota'
                elif sc:
                    cc, bc, bt = 'cell-sched', 'badge-sched', '+ Setup'
                else:
                    cc, bc, bt = 'cell-empty', 'badge-empty', '—'
                
                tc2 = ' cell-today' if it else ''
                ex = f"<div class='day-info'>⏱ {hm[ws]}h</div>" if hr and ws in hm else ''
                
                st.markdown(
                    f"<div class='cal-cell {cc}{tc2}'>"
                    f"<div class='day-num'>{dn2}</div>"
                    f"<span class='day-badge {bc}'>{bt}</span>{ex}</div>",
                    unsafe_allow_html=True)
                
                dis = not hr and not sc
                btyp = "primary" if hr else "secondary"
                bl = "View" if hr else "Set up" if sc else "—"
                
                if st.button(bl, key=f"d_{yr}_{mo}_{dn2}", use_container_width=True, type=btyp, disabled=dis):
                    if hr:
                        nav_to('week', sel_date=curr, week_start=ws)
                    else:
                        nav_to('generate', sel_date=curr, week_start=ws)
    
    # Show generate panel if in generate mode
    if st.session_state.view == 'generate' and st.session_state.week_start:
        _gen_panel(sw)

def _gen_panel(sw):
    ws = st.session_state.week_start
    we = ws + timedelta(days=6)
    st.divider()
    
    if ws not in sw:
        st.warning("⚠️ No shift template for this week. Add one in the Scheduling page first.")
        return
    
    budget = get_schedule_budget(ws)
    c1, c2 = st.columns([3, 1])
    c1.subheader(f"📅 {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}")
    c1.info(f"Shift template found{f' · Budget: **{budget}h**' if budget else ''}. Ready to generate.")
    
    with c2:
        st.write("")
        if st.button("🚀 Generate Rota", type="primary", use_container_width=True):
            with st.spinner("⏳ Optimising via Cloud…"):
                try:
                    from scheduler_h_s import solve_rota_final_v14
                    # Call updated scheduler which now accepts sheet_id instead of local files
                    solve_rota_final_v14(sheet_id=sheet_id, target_weeks=[ws])
                    st.success("✅ Done!")
                    time.sleep(0.8)
                    nav_to('calendar')
                except Exception as e:
                    st.error(f"Error: {e}")

# ======================================================
# VIEW 2: WEEK
# ======================================================
def show_week_view():
    gw = get_generated_weeks()
    ws = st.session_state.week_start
    we = ws + timedelta(days=6)
    sn = gw.get(ws)
    roles = get_employee_roles()
    
    c1, c2, c3 = st.columns([1.2, 6, 1.5])
    with c1:
        st.write("")
        if st.button("◀ Calendar", use_container_width=True):
            nav_to('calendar')
    with c2:
        st.markdown(f"<div class='page-title'>📅 {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}</div>", unsafe_allow_html=True)
    with c3:
        st.write("")
        if st.button("🔄 Re-generate", use_container_width=True):
            with st.spinner("Regenerating…"):
                try:
                    from scheduler_h_s import solve_rota_final_v14
                    solve_rota_final_v14(sheet_id=sheet_id, target_weeks=[ws])
                    if f"df_{sn}" in st.session_state:
                        del st.session_state[f"df_{sn}"]
                    st.success("Done!")
                    time.sleep(0.8)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
    
    st.divider()
    
    if not sn:
        st.error("No rota found.")
        return
    
    df = load_week_rota(sn)
    if df is None:
        st.error("Could not load rota.")
        return
    
    dc = [c for c in df.columns if c not in ('Name', 'Employee ID', 'Total Weekly Hours')]
    
    st.markdown("**Click a day for the detailed breakdown:**")
    dbc = st.columns(len(dc))
    for i, ch in enumerate(dc):
        with dbc[i]:
            try:
                d = datetime.strptime(ch.split(' ')[0], '%Y-%m-%d').date()
                wk = int((df[ch] != 'OFF').sum() - df[ch].isna().sum())
                ev = '[Event' in ch
                tod = (d == date.today())
                lb = (f"{'🎫 ' if ev else ''}**{d.strftime('%a')}** \n{d.strftime('%d %b')}  \n👥 {wk}")
                bt = "primary" if tod else "secondary"
            except:
                lb = ch[:8]
                d = None
                bt = "secondary"
            if st.button(lb, key=f"wd_{ch}", use_container_width=True, type=bt):
                if d:
                    nav_to('day', sel_date=d, week_start=ws)
    
    st.write("")
    th = pd.to_numeric(df['Total Weekly Hours'], errors='coerce').sum() if 'Total Weekly Hours' in df.columns else 0
    bgt = get_schedule_budget(ws) or 0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("⏱️ TOTAL HOURS", f"{th:.0f}h")
    m2.metric("💰 BUDGET", f"{bgt}h" if bgt else "—")
    m3.metric("👥 STAFF ON ROTA", len(df))
    m4.metric("📊 AVG / PERSON", f"{th/len(df):.1f}h" if len(df) else "—")
    
    if bgt and th > 0:
        pct = min(th / bgt, 1.0)
        st.progress(pct, text=f"Budget: {th:.0f}h of {bgt}h ({pct*100:.0f}%)")
    
    st.divider()
    st.markdown("**Staff roles:**")
    rlc = st.columns(len(ROLE_COLORS))
    for i, (role, clr) in enumerate(ROLE_COLORS.items()):
        rlc[i].markdown(f"<span class='role-badge' style='background:{clr['bg']};color:{clr['text']}'>● {role}</span>", unsafe_allow_html=True)
    
    nt = st.columns(len(df))
    for i, (_, row) in enumerate(df.iterrows()):
        role = roles.get(str(row['Name']), 'Associate')
        clr = ROLE_COLORS.get(role, DRC)
        nt[i].markdown(
            f"<div style='background:{clr['bg']};color:{clr['text']};border-radius:8px;"
            f"padding:5px 6px;font-size:0.72em;font-weight:700;text-align:center;margin:4px 0'>"
            f"{row['Name']}<br><span style='font-weight:400;font-size:0.88em;opacity:0.85'>{role}</span></div>",
            unsafe_allow_html=True)
    
    sk = f"df_{sn}"
    if sk not in st.session_state:
        st.session_state[sk] = df.copy()
    
    ed = st.data_editor(st.session_state[sk], use_container_width=True, hide_index=True,
        num_rows="fixed", key=f"editor_{sn}",
        column_config={"Total Weekly Hours": st.column_config.NumberColumn("Total Hrs", disabled=True, format="%.1f")})
    
    if not ed.equals(st.session_state[sk]):
        ed = recalc(ed)
        st.session_state[sk] = ed
        # Save edits straight back to the cloud
        write_sheet_data(sheet_id, sn, ed)
        st.rerun()
    
    st.divider()
    with st.expander("📥 Download Options"):
        dc2a, dc2b, dc2c = st.columns(3)
        with dc2a:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w:
                ed.to_excel(w, index=False, sheet_name=sn)
            st.download_button("⬇️ Excel", buf.getvalue(), f"Rota_{sn.replace(' ','_')}.xlsx")
        with dc2b:
            pb = create_pdf(ed, sn)
            st.download_button("⬇️ PDF", pb, f"Rota_{sn.replace(' ','_')}.pdf", mime="application/pdf")
        with dc2c:
            # Create a full workbook on the fly from all generated weeks
            full_buf = io.BytesIO()
            with pd.ExcelWriter(full_buf, engine='openpyxl') as writer:
                for week_name in gw.values():
                    sheet_df = get_sheet_data(sheet_id, week_name)
                    sheet_df.to_excel(writer, index=False, sheet_name=week_name)
            st.download_button("⬇️ Full Workbook", full_buf.getvalue(), "Final_Rota_Full.xlsx")

# ======================================================
# VIEW 3: DAY
# ======================================================
def show_day_view():
    gw = get_generated_weeks()
    sd = st.session_state.selected_date
    ws = st.session_state.week_start
    sn = gw.get(ws)
    roles = get_employee_roles()
    
    c1, c2 = st.columns([1.2, 7])
    with c1:
        st.write("")
        if st.button("◀ Week View", use_container_width=True):
            nav_to('week')
    with c2:
        st.markdown(f"<div class='page-title'>📋 {sd.strftime('%A, %d %B %Y')}</div>", unsafe_allow_html=True)
    
    st.divider()
    
    if not sn:
        st.error("No rota found.")
        return
    
    df = load_week_rota(sn)
    if df is None:
        st.error("Could not load rota.")
        return
    
    ds = sd.strftime('%Y-%m-%d')
    dc = next((c for c in df.columns if c.startswith(ds)), None)
    
    if not dc:
        st.warning("No data for this day.")
        return
    
    is_ev = '[Event' in dc
    wk = df[df[dc].notna() & (df[dc] != 'OFF')][['Name', dc]].copy()
    wk.columns = ['Employee', 'Shift']
    wk['Hours'] = wk['Shift'].apply(calc_hours)
    wk['Role'] = wk['Employee'].map(lambda n: roles.get(str(n), 'Associate'))
    wk = wk.sort_values('Shift').reset_index(drop=True)
    off = df[df[dc] == 'OFF']['Name'].tolist()
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("👥 WORKING", len(wk))
    m2.metric("🔴 OFF", len(off))
    m3.metric("⏱️ HOURS", f"{wk['Hours'].sum():.0f}h")
    m4.metric("🎫 EVENT", "Yes" if is_ev else "No")
    
    if is_ev:
        evt = dc.split('[Event: ')[-1].rstrip(']')
        st.info(f"🎫 **Event at {evt}** — consider extra evening cover.")
    
    st.divider()
    st.markdown("### 🕐 Shift Timeline")
    
    if wk.empty:
        st.warning("No staff working.")
    else:
        sts = [int(r.split(' - ')[0].split(':')[0]) for r in wk['Shift'] if ' - ' in str(r)]
        ens = [24 if int(r.split(' - ')[1].split(':')[0]) == 0 else int(r.split(' - ')[1].split(':')[0]) for r in wk['Shift'] if ' - ' in str(r)]
        ws2 = min(sts) if sts else 7
        we2 = max(ens) if ens else 22
        win = max(we2 - ws2, 1)
        
        _, _, cb0 = st.columns([2.5, 1.6, 5])
        tks = range(ws2, we2 + 1, 2)
        cb0.markdown("<div style='display:flex;justify-content:space-between;color:#94A3B8;"
                     "font-size:0.70em;padding:0 3px;margin-bottom:6px'>"
                     + "".join(f"<span>{h:02d}:00</span>" for h in tks) + "</div>", unsafe_allow_html=True)
        
        for _, row in wk.iterrows():
            sh2 = str(row['Shift'])
            if ' - ' not in sh2:
                continue
            ss, es = sh2.split(' - ')
            sh3 = int(ss.split(':')[0])
            eh3 = int(es.split(':')[0])
            if eh3 == 0:
                eh3 = 24
            hrs2 = eh3 - sh3
            lp = (sh3 - ws2) / win * 100
            wp = hrs2 / win * 100
            role = row['Role']
            clr = ROLE_COLORS.get(role, DRC)
            
            cn, cs, cb2 = st.columns([2.5, 1.6, 5])
            cn.markdown(f"<div style='display:flex;align-items:center;gap:5px;padding:2px 0'>"
                        f"<b style='color:#1E293B'>{row['Employee']}</b>"
                        f"<span class='role-badge' style='background:{clr['bg']};color:{clr['text']}'>{role}</span></div>", unsafe_allow_html=True)
            cs.markdown(f"<code style='background:#EFF6FF;color:#1D4ED8;padding:3px 7px;border-radius:5px;font-size:0.83em'>{sh2}</code>", unsafe_allow_html=True)
            cb2.markdown(f"<div class='tl-track'><div class='tl-bar' style='left:{lp:.1f}%;width:{wp:.1f}%;background:{clr['bar']}'>{hrs2}h</div></div>", unsafe_allow_html=True)
    
    st.divider()
    cw, co = st.columns(2)
    
    with cw:
        st.markdown("### ✅ Working Today")
        for _, r in wk.iterrows():
            role = r['Role']
            clr = ROLE_COLORS.get(role, DRC)
            st.markdown(f"<div class='emp-row' style='border-left:4px solid {clr['bar']}'>"
                        f"<div><b style='color:#1E293B'>{r['Employee']}</b>"
                        f"<span class='role-badge' style='background:{clr['bg']};color:{clr['text']}'>{role}</span></div>"
                        f"<div style='font-weight:600;color:#2563EB'>{r['Shift']}&nbsp;"
                        f"<span style='color:#64748B;font-weight:400'>({r['Hours']:.0f}h)</span></div></div>", unsafe_allow_html=True)
    
    with co:
        st.markdown("### 🔴 Off Today")
        if not off:
            st.success("All staff working!")
        else:
            for nm in off:
                role = roles.get(str(nm), 'Associate')
                clr = ROLE_COLORS.get(role, DRC)
                st.markdown(f"<div style='background:#FFF5F5;border-radius:10px;padding:10px 14px;"
                            f"margin:5px 0;border:1px solid #FEE2E2;display:flex;align-items:center;gap:8px'>"
                            f"<span style='color:#DC2626;font-size:1.1em'>●</span>"
                            f"<b style='color:#1E293B'>{nm}</b>"
                            f"<span class='role-badge' style='background:{clr['bg']};color:{clr['text']}'>{role}</span></div>", unsafe_allow_html=True)
    
    st.divider()
    pc, nc = st.columns(2)
    pd2 = sd - timedelta(days=1)
    nd = sd + timedelta(days=1)
    
    with pc:
        if get_week_start(pd2) in gw:
            if st.button(f"◀ {pd2.strftime('%A %d %b')}", use_container_width=True):
                nav_to('day', sel_date=pd2, week_start=get_week_start(pd2))
    
    with nc:
        if get_week_start(nd) in gw:
            if st.button(f"{nd.strftime('%A %d %b')} ▶", use_container_width=True):
                nav_to('day', sel_date=nd, week_start=get_week_start(nd))

# ======================================================
# ROUTER
# ======================================================
view = st.session_state.view
if view in ('calendar', 'generate'):
    show_calendar()
elif view == 'week':
    show_week_view()
elif view == 'day':
    show_day_view()
