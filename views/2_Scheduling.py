import streamlit as st
import pandas as pd
import os, calendar
from datetime import datetime, date, time, timedelta

FILE_PATH = 'Book(Employees)_01.xlsx'
SHEET     = 'Shift Templates'

SHARED_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.cal-cell{border-radius:14px;padding:14px 6px 8px;text-align:center;min-height:125px;
  margin-bottom:2px;border:1.5px solid transparent;box-shadow:0 1px 4px rgba(0,0,0,0.06);}
.cell-sched{background:#EFF6FF;border-color:#BFDBFE;}
.cell-empty{background:#F8FAFC;border-color:#E2E8F0;}
.cell-today{outline:2.5px solid #2563EB;outline-offset:2px;border-radius:14px;}
.day-num{font-size:2.6em;font-weight:900;line-height:1;margin-bottom:6px;
  color:#1E293B;letter-spacing:-0.03em;}
.cell-empty .day-num{color:#CBD5E1;}
.day-badge{display:inline-block;font-size:0.84em;font-weight:700;padding:3px 10px;
  border-radius:20px;letter-spacing:0.06em;text-transform:uppercase;}
.badge-sched{background:#2563EB;color:#fff;}
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
.constraint-card{background:#F0F7FF;border:1px solid #BFDBFE;border-radius:12px;
  padding:18px 20px;margin-bottom:14px;}
section[data-testid="stSidebar"]{background:#F0F7FF;}
.page-title{font-size:2em;font-weight:900;color:#1E293B;letter-spacing:-0.03em;margin-bottom:2px;}
.page-sub{font-size:0.88em;color:#64748B;margin-bottom:14px;}
</style>
"""
st.markdown(SHARED_CSS, unsafe_allow_html=True)

for k,v in {'sched_view':'calendar','sched_yr':datetime.today().year,
             'sched_mo':datetime.today().month,'sched_ws':None}.items():
    if k not in st.session_state: st.session_state[k]=v

def get_week_start(d):
    if isinstance(d,datetime): d=d.date()
    return d-timedelta(days=d.weekday())

@st.cache_data(ttl=10)
def load_all():
    if not os.path.exists(FILE_PATH): return pd.DataFrame()
    try:
        df=pd.read_excel(FILE_PATH,sheet_name=SHEET)
        df.columns=df.columns.str.strip()
        df['Date']=pd.to_datetime(df['Date'])
        for col in['Start','End']:
            try: df[col]=pd.to_datetime(df[col].astype(str)).dt.time
            except: pass
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=10)
def get_sched_weeks():
    df=load_all()
    if df.empty: return set()
    return {(d-timedelta(days=d.weekday())).date() for d in df['Date']}

def save_all(df):
    with pd.ExcelWriter(FILE_PATH,engine='openpyxl',mode='a',if_sheet_exists='replace') as w:
        df.to_excel(w,sheet_name=SHEET,index=False)
    load_all.clear(); get_sched_weeks.clear()

def nav_to(view,ws=None):
    st.session_state.sched_view=view
    if ws is not None: st.session_state.sched_ws=ws
    st.rerun()

def week_label(ws):
    we=ws+timedelta(days=6)
    wn=(ws+timedelta(days=3)).isocalendar()[1]
    return f"Week {wn} · {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}"

# ── SIDEBAR ──────────────────────────────────────────────────────
def render_sidebar():
    view=st.session_state.sched_view; ws=st.session_state.sched_ws
    sw=get_sched_weeks()
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📊 Scheduling")
        st.metric("Weeks Configured", len(sw))
        if view in('week','add') and ws:
            we=ws+timedelta(days=6)
            st.markdown("---")
            st.markdown(
                f"<div style='background:#EFF6FF;border-radius:10px;padding:10px 12px;"
                f"border:1px solid #BFDBFE;margin-bottom:8px'>"
                f"<b style='color:#1D4ED8'>📅 {ws.strftime('%d %b')} – {we.strftime('%d %b')}</b></div>",
                unsafe_allow_html=True)
            df=load_all()
            if not df.empty:
                df['_ws']=df['Date'].apply(lambda x:(x.date()-timedelta(days=x.weekday())))
                wd=df[df['_ws']==ws]
                if not wd.empty:
                    bgt=int(wd['Budget'].max()) if 'Budget' in wd.columns else 0
                    mn=int(wd['Minimum Staff'].max())
                    mx=int(wd['Maximum Employees'].max())
                    cl=int(wd['Minimum closing staff'].max())
                    st.metric("💰 Budget",f"{bgt}h")
                    st.metric("👥 Min Staff",mn)
                    st.metric("👥 Max Staff",mx)
                    st.metric("🔒 Min Closers",cl)
                    try:
                        op=wd['Start'].iloc[0]; cl2=wd['End'].iloc[0]
                        st.markdown(f"**🕐 Hours:** {str(op)[:5]} – {str(cl2)[:5]}")
                    except: pass

render_sidebar()

# ── VIEW 1: CALENDAR ─────────────────────────────────────────────
def show_calendar():
    sw=get_sched_weeks()
    df_all=load_all()

    # Build budget map: ws → budget
    bgt_map={}
    if not df_all.empty and 'Budget' in df_all.columns:
        df_all['_ws']=df_all['Date'].apply(lambda x:(x.date()-timedelta(days=x.weekday())))
        for ws2,grp in df_all.groupby('_ws'):
            bgt_map[ws2]=int(grp['Budget'].max())

    st.markdown("<div class='page-title'>📅 Scheduling</div>",unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Click any day to edit that week's schedule, or add a new one</div>",unsafe_allow_html=True)
    lc=st.columns([1.3,1.2,5])
    lc[0].markdown("🔵 **Schedule set**"); lc[1].markdown("⬜ **No data**")
    st.write("")
    yr=st.session_state.sched_yr; mo=st.session_state.sched_mo
    c1,c2,c3=st.columns([1,6,1])
    with c1:
        if st.button("◀",use_container_width=True,key="sp"):
            st.session_state.sched_mo=12 if mo==1 else mo-1
            if mo==1: st.session_state.sched_yr=yr-1
            st.rerun()
    with c2:
        st.markdown(f"<h2 style='text-align:center;margin:0;color:#1E293B;font-weight:900;"
                    f"letter-spacing:-0.03em'>{datetime(yr,mo,1).strftime('%B %Y')}</h2>",unsafe_allow_html=True)
    with c3:
        if st.button("▶",use_container_width=True,key="sn"):
            st.session_state.sched_mo=1 if mo==12 else mo+1
            if mo==12: st.session_state.sched_yr=yr+1
            st.rerun()
    st.write("")
    DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    hc=st.columns(7)
    for i,dn in enumerate(DAYS):
        bg="#FEE2E2" if i>=5 else "#EFF6FF"
        tc="#DC2626" if i>=5 else "#1D4ED8"
        hc[i].markdown(f"<div class='cal-hdr' style='background:{bg};color:{tc}'>{dn}</div>",unsafe_allow_html=True)
    today=date.today()
    for wr in calendar.monthcalendar(yr,mo):
        cols=st.columns(7)
        for di,dn2 in enumerate(wr):
            with cols[di]:
                if dn2==0:
                    st.markdown("<div style='min-height:128px'></div>",unsafe_allow_html=True); continue
                curr=date(yr,mo,dn2); ws=get_week_start(curr)
                hd=ws in sw; it=curr==today
                cc='cell-sched' if hd else 'cell-empty'
                bc='badge-sched' if hd else 'badge-empty'
                bt2='✓ Set' if hd else '+ Add'
                tc2=' cell-today' if it else ''
                ex=f"<div class='day-info'>💰 {bgt_map[ws]}h</div>" if hd and ws in bgt_map else ''
                st.markdown(
                    f"<div class='cal-cell {cc}{tc2}'>"
                    f"<div class='day-num'>{dn2}</div>"
                    f"<span class='day-badge {bc}'>{bt2}</span>{ex}</div>",
                    unsafe_allow_html=True)
                btyp="primary" if hd else "secondary"
                bl="Edit" if hd else "Add"
                if st.button(bl,key=f"sc_{yr}_{mo}_{dn2}",use_container_width=True,type=btyp):
                    nav_to('week' if hd else 'add',ws=ws)

# ── VIEW 2: EDIT WEEK ─────────────────────────────────────────────
def show_week_view():
    ws=st.session_state.sched_ws; we=ws+timedelta(days=6)
    c1,c2=st.columns([1.2,7])
    with c1:
        st.write("")
        if st.button("◀ Calendar",use_container_width=True,key="wvb"): nav_to('calendar')
    with c2:
        st.markdown(f"<div class='page-title'>✏️ {week_label(ws)}</div>",unsafe_allow_html=True)
    st.divider()
    df_all=load_all()
    if df_all.empty: st.error("No schedule data found."); return
    df_all['_ws']=df_all['Date'].apply(lambda x:(x.date()-timedelta(days=x.weekday())))
    wd=df_all[df_all['_ws']==ws].drop(columns=['_ws']).copy()
    if wd.empty: st.warning("No data for this week."); return

    bgt=int(wd['Budget'].max()) if 'Budget' in wd.columns else 300
    m1,m2,m3,m4=st.columns(4)
    m1.metric("💰 Budget",f"{bgt}h")
    m2.metric("👥 Min Staff (peak)",int(wd['Minimum Staff'].max()))
    m3.metric("👥 Max Staff (peak)",int(wd['Maximum Employees'].max()))
    m4.metric("🔒 Min Closers (peak)",int(wd['Minimum closing staff'].max()))
    st.divider()
    st.markdown("<div class='constraint-card'>",unsafe_allow_html=True)
    st.markdown("#### 💰 Weekly Budget (Hours)")
    st.caption("Applies to every day — the scheduler won't exceed this total across all shifts.")
    new_bgt=st.number_input("Budget",min_value=0,max_value=2000,value=bgt,step=10,label_visibility="collapsed")
    st.markdown("</div>",unsafe_allow_html=True)
    st.markdown("#### 🗓️ Daily Schedule Constraints")
    st.caption("Edit open/close times and staffing levels independently per day.")
    ed=st.data_editor(
        wd.drop(columns=['Budget'] if 'Budget' in wd.columns else []),
        num_rows="fixed",use_container_width=True,hide_index=True,
        column_config={
            "Date":st.column_config.DateColumn("Date",format="ddd DD MMM",disabled=True),
            "Start":st.column_config.TimeColumn("🔓 Open",format="HH:mm"),
            "End":st.column_config.TimeColumn("🔒 Close",format="HH:mm"),
            "Minimum Staff":st.column_config.NumberColumn("Min Staff",min_value=1,max_value=30),
            "Maximum Employees":st.column_config.NumberColumn("Max Staff",min_value=1,max_value=30),
            "Minimum closing staff":st.column_config.NumberColumn("Min Closers",min_value=1,max_value=15),
        })
    st.write("")
    cs,cd=st.columns([4,1])
    with cs:
        if st.button("💾 Save Changes",type="primary",use_container_width=True):
            try:
                ed['Budget']=new_bgt
                other=df_all[df_all['_ws']!=ws].drop(columns=['_ws'],errors='ignore')
                final=pd.concat([other,ed],ignore_index=True).sort_values('Date')
                save_all(final); st.success("✅ Saved!"); st.rerun()
            except Exception as e: st.error(f"Error: {e}")
    with cd:
        if st.button("🗑️ Delete",type="secondary",use_container_width=True):
            remaining=df_all[df_all['_ws']!=ws].drop(columns=['_ws'],errors='ignore')
            save_all(remaining); st.warning(f"Deleted {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}")
            nav_to('calendar')

# ── VIEW 3: ADD WEEK ─────────────────────────────────────────────
def show_add_view():
    ws=st.session_state.sched_ws; we=ws+timedelta(days=6)
    c1,c2=st.columns([1.2,7])
    with c1:
        st.write("")
        if st.button("◀ Calendar",use_container_width=True,key="avb"): nav_to('calendar')
    with c2:
        st.markdown(f"<div class='page-title'>➕ {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}</div>",unsafe_allow_html=True)
    st.divider()
    sw=get_sched_weeks()
    if ws in sw: nav_to('week',ws=ws); return

    df_all=load_all()
    if not df_all.empty:
        df_all['_ws']=df_all['Date'].apply(lambda x:(x.date()-timedelta(days=x.weekday())))
        past=[w for w in df_all['_ws'].unique() if w<ws]
        if past:
            last=sorted(past)[-1]; lw=df_all[df_all['_ws']==last]
            lb=int(lw['Budget'].max()) if 'Budget' in lw.columns else 300
            lmn=int(lw['Minimum Staff'].max()); lmx=int(lw['Maximum Employees'].max())
            lcl=int(lw['Minimum closing staff'].max())
            lst=lw['Start'].iloc[0]; len2=lw['End'].iloc[0]
            st.info(f"💡 Pre-filled from {last.strftime('%d %b %Y')}. Adjust as needed.")
        else:
            lb=300; lmn=4; lmx=6; lcl=2; lst=time(7,0); len2=time(22,0)
    else:
        lb=300; lmn=4; lmx=6; lcl=2; lst=time(7,0); len2=time(22,0)

    st.markdown("<div class='constraint-card'>",unsafe_allow_html=True)
    st.markdown("#### 💰 Weekly Budget (Hours)")
    st.caption("Total hours the scheduler may allocate across all staff this week.")
    new_bgt=st.number_input("Budget",min_value=0,max_value=2000,value=lb,step=10,label_visibility="collapsed")
    st.markdown("</div>",unsafe_allow_html=True)
    st.markdown("#### ⚡ Quick-Set All Days")
    st.caption("Set defaults for all 7 days at once, then fine-tune below.")
    qc=st.columns(5)
    qo=qc[0].time_input("Open",value=lst,key="qo")
    qcl=qc[1].time_input("Close",value=len2,key="qcl")
    qmn=qc[2].number_input("Min Staff",value=lmn,min_value=1,max_value=30,key="qmn")
    qmx=qc[3].number_input("Max Staff",value=lmx,min_value=1,max_value=30,key="qmx")
    qcls=qc[4].number_input("Min Closers",value=lcl,min_value=1,max_value=15,key="qcls")
    st.write("")
    st.markdown("#### 🗓️ Per-Day Constraints")
    rows=[{'Date':pd.Timestamp(ws+timedelta(days=i)),'Start':qo,'End':qcl,
           'Minimum Staff':qmn,'Maximum Employees':qmx,'Minimum closing staff':qcls}
          for i in range(7)]
    base=pd.DataFrame(rows)
    ed=st.data_editor(
        base,num_rows="fixed",use_container_width=True,hide_index=True,key="add_ed",
        column_config={
            "Date":st.column_config.DateColumn("Date",format="ddd DD MMM",disabled=True),
            "Start":st.column_config.TimeColumn("🔓 Open",format="HH:mm"),
            "End":st.column_config.TimeColumn("🔒 Close",format="HH:mm"),
            "Minimum Staff":st.column_config.NumberColumn("Min Staff",min_value=1,max_value=30),
            "Maximum Employees":st.column_config.NumberColumn("Max Staff",min_value=1,max_value=30),
            "Minimum closing staff":st.column_config.NumberColumn("Min Closers",min_value=1,max_value=15),
        })
    st.write("")
    if st.button("💾 Save New Week",type="primary",use_container_width=True):
        try:
            bad=ed[ed['Maximum Employees']<ed['Minimum Staff']]
            if not bad.empty: st.error("❌ Max Staff must be ≥ Min Staff on every day."); return
            ed['Budget']=new_bgt
            if df_all.empty: final=ed.sort_values('Date')
            else:
                dc=df_all.drop(columns=['_ws'],errors='ignore')
                final=pd.concat([dc,ed],ignore_index=True).sort_values('Date')
            save_all(final)
            st.success(f"✅ Week {ws.strftime('%d %b')} – {we.strftime('%d %b %Y')} saved!")
            nav_to('week',ws=ws)
        except Exception as e: st.error(f"Error: {e}")

view=st.session_state.sched_view
if   view=='calendar': show_calendar()
elif view=='week':     show_week_view()
elif view=='add':      show_add_view()