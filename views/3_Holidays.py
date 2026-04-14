import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, date, timedelta

current_dir  = os.path.dirname(os.path.abspath(__file__))
parent_dir   = os.path.dirname(current_dir)
HOLIDAY_FILE = os.path.join(parent_dir, 'Holidaydata.xlsx')
EMPLOYEE_FILE= os.path.join(parent_dir, 'Book(Employees)_01.xlsx')

STATUS_COLORS = {
    'Approved': {'bg':'#DCFCE7','text':'#16A34A','dot':'#16A34A'},
    'Pending':  {'bg':'#FEF3C7','text':'#D97706','dot':'#D97706'},
    'Rejected': {'bg':'#FEE2E2','text':'#DC2626','dot':'#DC2626'},
}
DSC = {'bg':'#F1F5F9','text':'#64748B','dot':'#94A3B8'}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.cal-cell{border-radius:12px;padding:10px 5px 6px;text-align:center;
  min-height:110px;margin-bottom:2px;border:1.5px solid transparent;
  box-shadow:0 1px 4px rgba(0,0,0,0.06);}
.cell-approved{background:#F0FDF4;border-color:#86EFAC;}
.cell-pending {background:#FFFBEB;border-color:#FDE68A;}
.cell-mixed   {background:#F5F3FF;border-color:#C4B5FD;}
.cell-empty   {background:#F8FAFC;border-color:#E2E8F0;}
.cell-today   {outline:2.5px solid #2563EB;outline-offset:2px;border-radius:12px;}
.hol-day-num  {font-size:1.6em;font-weight:900;line-height:1;margin-bottom:4px;color:#1E293B;}
.cell-empty .hol-day-num{color:#CBD5E1;}
.hol-name     {font-size:0.84em;font-weight:600;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;padding:0 3px;margin:1px 0;}
.cal-hdr      {text-align:center;font-size:0.78em;font-weight:700;letter-spacing:0.09em;
  text-transform:uppercase;padding:8px 2px;border-radius:8px;margin-bottom:6px;}
div[data-testid="stButton"]>button{border-radius:8px;font-weight:600;
  font-size:0.80em;transition:all 0.15s ease;}
div[data-testid="stButton"]>button:hover{transform:translateY(-1px);
  box-shadow:0 4px 14px rgba(37,99,235,0.20);}
div[data-testid="stMetric"]{background:white;border:1px solid #E2E8F0;
  border-radius:12px;padding:14px 18px;box-shadow:0 1px 4px rgba(0,0,0,0.05);}
div[data-testid="stMetric"] label{color:#64748B;font-size:0.78em;font-weight:600;
  text-transform:uppercase;letter-spacing:0.04em;}
div[data-testid="stMetric"] div[data-testid="stMetricValue"]{color:#1E293B;
  font-size:1.7em;font-weight:800;}
.hol-card{background:white;border:1px solid #E2E8F0;border-radius:12px;
  padding:14px 16px;margin:6px 0;box-shadow:0 1px 4px rgba(0,0,0,0.05);}
.status-pill{display:inline-block;font-size:0.72em;font-weight:700;
  padding:3px 10px;border-radius:20px;letter-spacing:0.04em;}
section[data-testid="stSidebar"]{background:#F0F7FF;}
.page-title{font-size:2em;font-weight:900;color:#1E293B;
  letter-spacing:-0.03em;margin-bottom:2px;}
.page-sub{font-size:0.88em;color:#64748B;margin-bottom:14px;}
</style>
""", unsafe_allow_html=True)

for k,v in {'hol_yr':datetime.today().year,'hol_mo':datetime.today().month,
             'hol_sel':None}.items():
    if k not in st.session_state: st.session_state[k]=v

def load_holidays():
    if not os.path.exists(HOLIDAY_FILE):
        dummy = pd.DataFrame(columns=["Employee ID","Name","Date","Status","Reason"])
        with pd.ExcelWriter(HOLIDAY_FILE, engine='openpyxl') as w:
            dummy.to_excel(w, sheet_name="Data", index=False)
        return dummy

    try:
        df = pd.read_excel(HOLIDAY_FILE, sheet_name="Data")
        df.columns = df.columns.str.strip()

        if 'Employee ID' not in df.columns:
            df['Employee ID'] = ''

        df['Employee ID'] = df['Employee ID'].astype(str).str.strip()
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()

        return df

    except:
        return pd.DataFrame(columns=["Employee ID","Name","Date","Status","Reason"])

def save_holidays(df):
    with pd.ExcelWriter(HOLIDAY_FILE,engine='openpyxl',mode='a',if_sheet_exists='replace') as w:
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        df.to_excel(w,sheet_name="Data",index=False)

def get_employee_lookup():
    if not os.path.exists(EMPLOYEE_FILE): return pd.DataFrame(columns=['ID','Name'])
    try:
        df=pd.read_excel(EMPLOYEE_FILE,sheet_name='Employees')
        df.columns=df.columns.str.strip()
        df['ID']=df['ID'].astype(str).str.strip()
        df['Name']=df['Name'].astype(str).str.strip()
        return df[['ID','Name']]
    except:
        return pd.DataFrame(columns=['ID','Name'])

def group_into_ranges(df):
    """Group consecutive holiday rows per person into date-range dicts."""
    if df.empty: return []
    result=[]
    df=df.sort_values(['Name','Date'])
    for name,emp_df in df.groupby('Name'):
        dates=sorted(emp_df['Date'].dt.date.tolist())
        status=str(emp_df['Status'].iloc[0])
        reason=str(emp_df['Reason'].iloc[0]) if 'Reason' in emp_df.columns else ''
        start=dates[0]; prev=dates[0]
        for d in dates[1:]:
            if (d-prev).days==1: prev=d
            else:
                result.append({'Name':name,'Start':start,'End':prev,
                               'Days':(prev-start).days+1,'Status':status,'Reason':reason})
                start=d; prev=d
        result.append({'Name':name,'Start':start,'End':prev,
                       'Days':(prev-start).days+1,'Status':status,'Reason':reason})
    return result

@st.dialog('✈️ Request Time Off')
def add_holiday_dialog():
    emp_df=get_employee_lookup()
    names=emp_df['Name'].tolist()
    with st.form('hol_form'):
        emp=st.selectbox('Employee', names)
        c1,c2=st.columns(2)
        sd=c1.date_input('Start Date', value=date.today())
        ed=c2.date_input('End Date', value=date.today())
        reason=st.text_area('Reason (optional)', height=80)
        if st.form_submit_button('✅ Submit Request', type='primary', use_container_width=True):
            if ed < sd:
                st.error('End date cannot be before start date.')
                return
            emp_id=str(emp_df.loc[emp_df['Name']==emp,'ID'].iloc[0])
            rows=[]
            for i in range((ed-sd).days+1):
                d=pd.Timestamp(sd+timedelta(days=i)).normalize()
                rows.append({
                    'Employee ID': emp_id,
                    'Name': emp,
                    'Date': d,
                    'Status':'Pending',
                    'Reason':reason
                })
            df=load_holidays()
            final=pd.concat([df,pd.DataFrame(rows)],ignore_index=True) if not df.empty else pd.DataFrame(rows)
            final['Date']=pd.to_datetime(final['Date']).dt.normalize()
            save_holidays(final)
            st.toast(f'✅ Request submitted for {emp}!')
            st.rerun()

# Load holiday data first
df_h = load_holidays()

# ── SIDEBAR ──────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("---")
    st.markdown("### ✈️ Holidays")
    if not df_h.empty:
        pending_n  =len(df_h[df_h['Status'].str.lower()=='pending'])
        approved_n =len(df_h[df_h['Status'].str.lower()=='approved'])
        rejected_n =len(df_h[df_h['Status'].str.lower()=='rejected'])
        st.metric("⏳ Pending Approval",pending_n)
        st.metric("✅ Approved Days",   approved_n)
        st.metric("❌ Rejected",        rejected_n)
        if pending_n:
            st.markdown("---")
            st.markdown("**⏳ Awaiting action:**")
            pen=df_h[df_h['Status'].str.lower()=='pending']
            for nm in pen['Name'].unique():
                cnt=len(pen[pen['Name']==nm])
                st.markdown(
                    f"<div style='background:#FFFBEB;border-radius:8px;padding:6px 10px;"
                    f"margin:3px 0;font-size:0.85em;border:1px solid #FDE68A'>"
                    f"<b>{nm}</b> · {cnt} day{'s' if cnt>1 else ''}</div>",
                    unsafe_allow_html=True)

# ── MAIN ─────────────────────────────────────────────────────────
st.markdown("<div class='page-title'>✈️ Holiday Management</div>",unsafe_allow_html=True)
st.markdown("<div class='page-sub'>See who's off when and manage approval requests</div>",unsafe_allow_html=True)

df_h=load_holidays()

# Metrics
m1,m2,m3,m4=st.columns(4)
pn=len(df_h[df_h['Status'].str.lower()=='pending'])  if not df_h.empty else 0
an=len(df_h[df_h['Status'].str.lower()=='approved']) if not df_h.empty else 0
rn=len(df_h[df_h['Status'].str.lower()=='rejected']) if not df_h.empty else 0
m1.metric("Total Requests", len(df_h) if not df_h.empty else 0)
m2.metric("⏳ Pending",pn)
m3.metric("✅ Approved",an)
m4.metric("❌ Rejected",rn)

st.write("")

# Add button
c_add,c_space=st.columns([1.5,5])
with c_add:
    if st.button("➕ Add Request",type="primary",use_container_width=True):
        add_holiday_dialog()

st.divider()

# ── CALENDAR ─────────────────────────────────────────────────────
st.markdown("### 📅 Who's Off — Calendar View")

yr=st.session_state.hol_yr; mo=st.session_state.hol_mo

c1,c2,c3=st.columns([1,6,1])
with c1:
    if st.button("◀",use_container_width=True,key="hp"):
        st.session_state.hol_mo=12 if mo==1 else mo-1
        if mo==1: st.session_state.hol_yr=yr-1
        st.session_state.hol_sel=None; st.rerun()
with c2:
    st.markdown(f"<h3 style='text-align:center;margin:0;color:#1E293B;font-weight:800'>"
                f"{datetime(yr,mo,1).strftime('%B %Y')}</h3>",unsafe_allow_html=True)
with c3:
    if st.button("▶",use_container_width=True,key="hn"):
        st.session_state.hol_mo=1 if mo==12 else mo+1
        if mo==12: st.session_state.hol_yr=yr+1
        st.session_state.hol_sel=None; st.rerun()

st.write("")

# Build holiday map: date → list of (name, status)
hol_map={}
if not df_h.empty:
    for _,r in df_h.iterrows():
        d=r['Date'].date()
        hol_map.setdefault(d,[]).append((str(r['Name']),str(r['Status'])))

# Day headers
DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
hc=st.columns(7)
for i,dn in enumerate(DAYS):
    bg="#FEE2E2" if i>=5 else "#EFF6FF"; tc="#DC2626" if i>=5 else "#1D4ED8"
    hc[i].markdown(f"<div class='cal-hdr' style='background:{bg};color:{tc}'>{dn}</div>",
                   unsafe_allow_html=True)

today=date.today()
for wr in calendar.monthcalendar(yr,mo):
    cols=st.columns(7)
    for di,dn2 in enumerate(wr):
        with cols[di]:
            if dn2==0:
                st.markdown("<div style='min-height:113px'></div>",unsafe_allow_html=True); continue

            curr=date(yr,mo,dn2)
            day_hols=hol_map.get(curr,[])
            approved_h=[n for n,s in day_hols if s.lower()=='approved']
            pending_h =[n for n,s in day_hols if s.lower()=='pending']
            is_today  =(curr==today)
            is_sel    =(st.session_state.hol_sel==curr)

            if approved_h and pending_h: cc='cell-mixed'
            elif approved_h:             cc='cell-approved'
            elif pending_h:              cc='cell-pending'
            else:                        cc='cell-empty'

            tc2=' cell-today' if is_today else ''
            sel_ring=(' outline:2.5px solid #7C3AED;outline-offset:2px;'
                      'border-radius:12px;' if is_sel else '')

            names_html=''
            for nm,st2 in day_hols[:2]:
                sc=STATUS_COLORS.get(st2.capitalize(),DSC)
                short=nm.split()[0][:7]
                names_html+=(f"<div class='hol-name' style='color:{sc['dot']}'>"
                             f"● {short}</div>")
            if len(day_hols)>2:
                names_html+=f"<div style='font-size:0.76em;color:#94A3B8;padding:0 3px'>+{len(day_hols)-2}</div>"

            st.markdown(
                f"<div class='cal-cell {cc}{tc2}' style='{sel_ring}'>"
                f"<div class='hol-day-num'>{dn2}</div>{names_html}</div>",
                unsafe_allow_html=True)

            btn_lbl="👁" if day_hols else "·"
            btn_typ="secondary"
            if st.button(btn_lbl,key=f"hc_{yr}_{mo}_{dn2}",
                         use_container_width=True,type=btn_typ):
                st.session_state.hol_sel=(None if st.session_state.hol_sel==curr else curr)
                st.rerun()

# Day detail panel
if st.session_state.hol_sel:
    sel=st.session_state.hol_sel
    day_hols=hol_map.get(sel,[])
    st.markdown("---")
    close_c,title_c=st.columns([0.5,6])
    with close_c:
        if st.button("✕",key="hclose"): st.session_state.hol_sel=None; st.rerun()
    with title_c:
        st.markdown(f"**📅 {sel.strftime('%A, %d %B %Y')}**")
    if not day_hols:
        st.info("No one is off on this day.")
    else:
        for nm,stat in day_hols:
            sc=STATUS_COLORS.get(stat.capitalize(),DSC)
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;background:{sc['bg']};"
                f"border-radius:8px;padding:9px 14px;margin:4px 0;border:1px solid {sc['dot']}33'>"
                f"<b style='color:#1E293B'>{nm}</b>"
                f"<span class='status-pill' style='background:{sc['dot']};color:white'>{stat}</span>"
                f"</div>",unsafe_allow_html=True)

st.divider()

# ── APPROVAL TABS ─────────────────────────────────────────────────
st.markdown("### 📋 Request Management")
tab_pend,tab_appr,tab_all=st.tabs([f"⏳ Pending ({pn})","✅ Approved",f"📁 All ({len(df_h) if not df_h.empty else 0})"])

# ── PENDING TAB ───────────────────────────────────────────────────
with tab_pend:
    if df_h.empty or pn==0:
        st.success("✅ No pending requests — all clear!")
    else:
        pending_df=df_h[df_h['Status'].str.lower()=='pending'].copy()
        ranges=group_into_ranges(pending_df)
        for rng in ranges:
            sc=STATUS_COLORS['Pending']
            start_s=rng['Start'].strftime('%a %d %b')
            end_s  =rng['End'].strftime('%a %d %b %Y')
            days   =rng['Days']
            reason =rng.get('Reason','')

            with st.container():
                st.markdown(
                    f"<div class='hol-card' style='border-left:4px solid {sc['dot']}'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                    f"<div>"
                    f"<div style='font-weight:800;font-size:1.05em;color:#1E293B'>{rng['Name']}</div>"
                    f"<div style='color:#374151;margin:4px 0'>📅 {start_s} – {end_s} "
                    f"<span style='background:#EFF6FF;color:#2563EB;border-radius:20px;"
                    f"padding:2px 8px;font-size:0.78em;font-weight:600;margin-left:4px'>"
                    f"{days} day{'s' if days>1 else ''}</span></div>"
                    + (f"<div style='color:#64748B;font-size:0.85em'>💬 {reason}</div>" if reason and reason!='nan' else '')
                    + f"</div>"
                    f"<span class='status-pill' style='background:{sc['dot']};color:white'>⏳ Pending</span>"
                    f"</div></div>",
                    unsafe_allow_html=True)

                ac,rc,_=st.columns([1,1,3])
                if ac.button("✅ Approve",key=f"apr_{rng['Name']}_{rng['Start']}",
                             type="primary",use_container_width=True):
                    mask=((df_h['Name']==rng['Name'])&
                          (df_h['Date']>=pd.Timestamp(rng['Start']))&
                          (df_h['Date']<=pd.Timestamp(rng['End']))&
                          (df_h['Status'].str.lower()=='pending'))
                    df_h.loc[mask,'Status']='Approved'
                    save_holidays(df_h); st.toast(f"✅ Approved for {rng['Name']}!"); st.rerun()
                if rc.button("❌ Reject", key=f"rej_{rng['Name']}_{rng['Start']}",
                             use_container_width=True):
                    mask=((df_h['Name']==rng['Name'])&
                          (df_h['Date']>=pd.Timestamp(rng['Start']))&
                          (df_h['Date']<=pd.Timestamp(rng['End']))&
                          (df_h['Status'].str.lower()=='pending'))
                    df_h.loc[mask,'Status']='Rejected'
                    save_holidays(df_h); st.toast(f"❌ Rejected for {rng['Name']}."); st.rerun()

# ── APPROVED TAB ──────────────────────────────────────────────────
with tab_appr:
    if df_h.empty:
        st.info("No holiday data yet.")
    else:
        appr_df=df_h[df_h['Status'].str.lower()=='approved'].copy()
        if appr_df.empty:
            st.info("No approved holidays yet.")
        else:
            ranges_a=group_into_ranges(appr_df)
            for rng in sorted(ranges_a,key=lambda x:x['Start']):
                sc=STATUS_COLORS['Approved']
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;align-items:center;"
                    f"background:{sc['bg']};border-radius:10px;padding:10px 14px;margin:4px 0;"
                    f"border:1px solid {sc['dot']}44'>"
                    f"<div><b style='color:#1E293B'>{rng['Name']}</b>"
                    f"<span style='color:#64748B;margin-left:8px;font-size:0.87em'>"
                    f"{rng['Start'].strftime('%d %b')} – {rng['End'].strftime('%d %b %Y')}</span></div>"
                    f"<span style='color:{sc['text']};font-weight:700;font-size:0.88em'>"
                    f"{rng['Days']} day{'s' if rng['Days']>1 else ''}</span></div>",
                    unsafe_allow_html=True)

# ── ALL TAB ───────────────────────────────────────────────────────
with tab_all:
    if df_h.empty:
        st.info("No holiday data yet.")
    else:
        st.dataframe(
            df_h.sort_values('Date',ascending=False).assign(
                Date=df_h['Date'].dt.strftime('%d %b %Y')),
            use_container_width=True, hide_index=True,
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status",options=["Pending","Approved","Rejected"]),
                "Date": st.column_config.TextColumn("Date")
            })