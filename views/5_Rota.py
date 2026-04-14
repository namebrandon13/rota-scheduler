import streamlit as st
import pandas as pd
import os, time, io, calendar
from datetime import datetime, date, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# ======================================================
# PATHS (CLOUD SAFE - relative to script location)
# ======================================================
current_dir   = os.path.dirname(os.path.abspath(__file__))
parent_dir    = os.path.dirname(current_dir)
EMPLOYEE_FILE = os.path.join(parent_dir, 'Book(Employees)_01.xlsx')
HOLIDAY_FILE  = os.path.join(parent_dir, 'Holidaydata.xlsx')
OUTPUT_FILE   = os.path.join(parent_dir, 'Final_Rota_MultiSheet.xlsx')

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
    if isinstance(d,datetime): d=d.date()
    return d-timedelta(days=d.weekday())

def nav_to(view, sel_date=None, week_start=None):
    st.session_state.view = view
    if sel_date is not None:
        st.session_state.selected_date = sel_date
    if week_start is not None:
        st.session_state.week_start = week_start
    st.rerun()

@st.cache_data(ttl=30)
def get_scheduling_weeks():
    if not os.path.exists(EMPLOYEE_FILE): return set()
    try:
        df=pd.read_excel(EMPLOYEE_FILE,sheet_name="Shift Templates")
        df['Date']=pd.to_datetime(df['Date'])
        return {(d-timedelta(days=d.weekday())).date() for d in df['Date']}
    except: return set()

@st.cache_data(ttl=10)
def get_generated_weeks():
    r={}
    if not os.path.exists(OUTPUT_FILE): return r
    try:
        xls=pd.ExcelFile(OUTPUT_FILE)
        for sheet in xls.sheet_names:
            df=pd.read_excel(OUTPUT_FILE,sheet_name=sheet,nrows=1)
            dc=[c for c in df.columns if c not in('Name','Employee ID','Total Weekly Hours')]
            if dc:
                try:
                    d=datetime.strptime(dc[0].split(' ')[0],'%Y-%m-%d').date()
                    r[get_week_start(d)]=sheet
                except: pass
    except: pass
    return r

@st.cache_data(ttl=10)
def get_week_total_hours():
    r={}
    if not os.path.exists(OUTPUT_FILE): return r
    try:
        xls=pd.ExcelFile(OUTPUT_FILE)
        for sheet in xls.sheet_names:
            df=pd.read_excel(OUTPUT_FILE,sheet_name=sheet)
            if 'Total Weekly Hours' not in df.columns: continue
            dc=[c for c in df.columns if c not in('Name','Employee ID','Total Weekly Hours')]
            if not dc: continue
            try:
                d=datetime.strptime(dc[0].split(' ')[0],'%Y-%m-%d').date()
                r[get_week_start(d)]=int(df['Total Weekly Hours'].sum())
            except: pass
    except: pass
    return r

@st.cache_data(ttl=30)
def get_schedule_budget(ws):
    if not os.path.exists(EMPLOYEE_FILE): return None
    try:
        df=pd.read_excel(EMPLOYEE_FILE,sheet_name="Shift Templates")
        df.columns=df.columns.str.strip()
        df['Date']=pd.to_datetime(df['Date'])
        df['_ws']=df['Date'].apply(lambda x:(x.date()-timedelta(days=x.weekday())))
        w=df[df['_ws']==ws]
        return int(w['Budget'].max()) if not w.empty and 'Budget' in w.columns else None
    except: return None

@st.cache_data(ttl=60)
def get_employee_roles():
    if not os.path.exists(EMPLOYEE_FILE): return {}
    try:
        df=pd.read_excel(EMPLOYEE_FILE,sheet_name="Employees")
        df.columns=df.columns.str.strip()
        return {str(n).strip():str(r).strip() for n,r in zip(df['Name'],df['Designation'])}
    except: return {}

def load_week_rota(sn):
    try: return pd.read_excel(OUTPUT_FILE,sheet_name=sn)
    except: return None

def calc_hours(s):
    if not isinstance(s,str) or ' - ' not in s: return 0.0
    try:
        a,b=s.split(' - ')
        sh,sm=map(int,a.split(':'))
        eh,em=map(int,b.split(':'))
        if eh==0: eh=24
        return (eh*60+em-sh*60-sm)/60
    except: return 0.0

def recalc(df):
    dc=[c for c in df.columns if c not in('Name','Employee ID','Total Weekly Hours')]
    for i,row in df.iterrows():
        df.at[i,'Total Weekly Hours']=sum(calc_hours(str(row[c])) for c in dc)
    return df

def create_pdf(df, title):
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=landscape(letter))
    sty=getSampleStyleSheet()
    story=[Paragraph(title,sty['Title'])]
    data=[list(df.columns)]+[list(r) for _,r in df.iterrows()]
    t=Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#2563EB')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),7),
        ('GRID',(0,0),(-1,-1),0.5,colors.grey),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    story.append(t)
    doc.build(story)
    return buf.getvalue()

# ======================================================
# VIEW 1: CALENDAR
# ======================================================
def show_calendar():
    gw = get_generated_weeks()
    sw = get_scheduling_weeks()
    wh = get_week_total_hours()
    
    st.markdown("<div class='page-title'>📅 Rota Calendar</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>View generated rotas and scheduling data by month</div>", unsafe_allow_html=True)
    
    # Month navigation
    c1,c2,c3,c4 = st.columns([1,1,2,1])
    with c1:
        if st.button("◀ Prev", use_container_width=True):
            if st.session_state.cal_month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1
            st.rerun()
    with c2:
        if st.button("Today", use_container_width=True):
            st.session_state.cal_year = datetime.today().year
            st.session_state.cal_month = datetime.today().month
            st.rerun()
    with c3:
        st.markdown(f"<h2 style='text-align:center;margin:0;color:#1E293B'>{calendar.month_name[st.session_state.cal_month]} {st.session_state.cal_year}</h2>", unsafe_allow_html=True)
    with c4:
        if st.button("Next ▶", use_container_width=True):
            if st.session_state.cal_month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1
            st.rerun()
    
    st.write("")
    
    # Calendar header
    hdr = st.columns(7)
    for i, d in enumerate(['Mon','Tue','Wed','Thu','Fri','Sat','Sun']):
        bg = '#EFF6FF' if i < 5 else '#FEF2F2'
        hdr[i].markdown(f"<div class='cal-hdr' style='background:{bg}'>{d}</div>", unsafe_allow_html=True)
    
    # Calendar grid
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(st.session_state.cal_year, st.session_state.cal_month)
    today = date.today()
    
    for week in weeks:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    st.markdown("<div class='cal-cell cell-empty' style='min-height:80px'></div>", unsafe_allow_html=True)
                else:
                    d = date(st.session_state.cal_year, st.session_state.cal_month, day)
                    ws = get_week_start(d)
                    is_today = (d == today)
                    has_rota = ws in gw
                    has_sched = ws in sw
                    
                    if has_rota:
                        cell_class = 'cell-rota'
                        badge = "<span class='day-badge badge-rota'>Rota</span>"
                        hrs = wh.get(ws, 0)
                        info = f"<div class='day-info'>👥 {hrs}h</div>" if hrs else ""
                    elif has_sched:
                        cell_class = 'cell-sched'
                        badge = "<span class='day-badge badge-sched'>Sched</span>"
                        info = ""
                    else:
                        cell_class = 'cell-empty'
                        badge = "<span class='day-badge badge-empty'>—</span>"
                        info = ""
                    
                    today_class = ' cell-today' if is_today else ''
                    
                    st.markdown(f"""
                        <div class='cal-cell {cell_class}{today_class}'>
                            <div class='day-num'>{day}</div>
                            {badge}
                            {info}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if has_rota:
                        if st.button("👁", key=f"view_{d}", use_container_width=True):
                            nav_to('week', week_start=ws)
    
    # Legend
    st.write("")
    l1,l2,l3 = st.columns(3)
    l1.markdown("🟢 **Rota Generated** — Click 👁 to view")
    l2.markdown("🟡 **Schedule Data** — Ready to generate")
    l3.markdown("⚪ **No Data** — No schedule entered")

# ======================================================
# VIEW 2: WEEK
# ======================================================
def show_week_view():
    gw = get_generated_weeks()
    ws = st.session_state.week_start
    sn = gw.get(ws)
    roles = get_employee_roles()
    
    if not sn:
        st.error("No rota found for this week.")
        if st.button("◀ Back to Calendar"):
            nav_to('calendar')
        return
    
    we = ws + timedelta(days=6)
    
    c1,c2 = st.columns([1.2,7])
    with c1:
        st.write("")
        if st.button("◀ Calendar", use_container_width=True):
            nav_to('calendar')
    with c2:
        st.markdown(f"<div class='page-title'>📋 Week {ws.isocalendar()[1]} Rota</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='page-sub'>{ws.strftime('%d %B')} – {we.strftime('%d %B %Y')}</div>", unsafe_allow_html=True)
    
    st.divider()
    
    df = load_week_rota(sn)
    if df is None:
        st.error("Could not load rota.")
        return
    
    dc = [c for c in df.columns if c not in ('Name','Employee ID','Total Weekly Hours')]
    
    st.markdown("**Click a day for the detailed breakdown:**")
    dbc = st.columns(len(dc))
    for i, ch in enumerate(dc):
        with dbc[i]:
            try:
                d = datetime.strptime(ch.split(' ')[0], '%Y-%m-%d').date()
                wk = int((df[ch] != 'OFF').sum() - df[ch].isna().sum())
                ev = '[Event' in ch
                tod = (d == date.today())
                lb = (f"{'🎫 ' if ev else ''}**{d.strftime('%a')}**  \n{d.strftime('%d %b')}  \n👥 {wk}")
                bt = "primary" if tod else "secondary"
            except:
                lb = ch[:8]
                d = None
                bt = "secondary"
            if st.button(lb, key=f"wd_{ch}", use_container_width=True, type=bt):
                if d:
                    nav_to('day', sel_date=d, week_start=ws)
    
    st.write("")
    th = df['Total Weekly Hours'].sum() if 'Total Weekly Hours' in df.columns else 0
    bgt = get_schedule_budget(ws) or 0
    
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("⏱️ Total Hours", f"{th:.0f}h")
    m2.metric("💰 Budget", f"{bgt}h" if bgt else "—")
    m3.metric("👥 Staff on Rota", len(df))
    m4.metric("📊 Avg / Person", f"{th/len(df):.1f}h" if len(df) else "—")
    
    if bgt and th > 0:
        pct = min(th/bgt, 1.0)
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
        st.rerun()
    
    st.divider()
    with st.expander("📥 Download Options"):
        dc2a,dc2b,dc2c = st.columns(3)
        with dc2a:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w:
                ed.to_excel(w, index=False, sheet_name=sn)
            st.download_button("⬇️ Excel", buf.getvalue(), f"Rota_{sn.replace(' ','_')}.xlsx")
        with dc2b:
            pb = create_pdf(ed, sn)
            st.download_button("⬇️ PDF", pb, f"Rota_{sn.replace(' ','_')}.pdf", mime="application/pdf")
        with dc2c:
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, 'rb') as f:
                    st.download_button("⬇️ Full Workbook", f.read(), "Final_Rota_Full.xlsx")

# ======================================================
# VIEW 3: DAY
# ======================================================
def show_day_view():
    gw = get_generated_weeks()
    sd = st.session_state.selected_date
    ws = st.session_state.week_start
    sn = gw.get(ws)
    roles = get_employee_roles()
    
    c1,c2 = st.columns([1.2,7])
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
    
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("👥 Working", len(wk))
    m2.metric("🔴 Off", len(off))
    m3.metric("⏱️ Hours", f"{wk['Hours'].sum():.0f}h")
    m4.metric("🎫 Event", "Yes" if is_ev else "No")
    
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
        
        _,_,cb0 = st.columns([2.5, 1.6, 5])
        tks = range(ws2, we2+1, 2)
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
            
            cn,cs,cb2 = st.columns([2.5, 1.6, 5])
            cn.markdown(f"<div style='display:flex;align-items:center;gap:5px;padding:2px 0'>"
                        f"<b style='color:#1E293B'>{row['Employee']}</b>"
                        f"<span class='role-badge' style='background:{clr['bg']};color:{clr['text']}'>{role}</span></div>", unsafe_allow_html=True)
            cs.markdown(f"<code style='background:#EFF6FF;color:#1D4ED8;padding:3px 7px;border-radius:5px;font-size:0.83em'>{sh2}</code>", unsafe_allow_html=True)
            cb2.markdown(f"<div class='tl-track'><div class='tl-bar' style='left:{lp:.1f}%;width:{wp:.1f}%;background:{clr['bar']}'>{hrs2}h</div></div>", unsafe_allow_html=True)
    
    st.divider()
    cw,co = st.columns(2)
    
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
    pc,nc = st.columns(2)
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
