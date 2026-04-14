import streamlit as st
import pandas as pd
import os, subprocess, sys, calendar
from datetime import datetime, date, timedelta
import pydeck as pdk

current_dir  = os.path.dirname(os.path.abspath(__file__))
parent_dir   = os.path.dirname(current_dir)
EVENTS_FILE  = os.path.join(parent_dir, 'EventsData.xlsx')

def impact_color(score):
    if score >= 8:   return '#DC2626'
    elif score >= 5: return '#D97706'
    else:            return '#16A34A'

def impact_label(score):
    if score >= 8:   return 'HIGH'
    elif score >= 5: return 'MED'
    else:            return 'LOW'

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
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
/* ── Event cards ── */
.event-card{background:white;border:1px solid #E2E8F0;border-radius:14px;
  overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);margin-bottom:12px;}
.card-header{padding:12px 14px 10px;}
.card-body{padding:0 14px 12px;}
.impact-track{background:#E2E8F0;border-radius:99px;height:7px;overflow:hidden;margin:5px 0;}
.impact-fill{height:100%;border-radius:99px;
  background:linear-gradient(90deg,#16A34A 0%,#EAB308 50%,#DC2626 100%);}
.impact-badge{display:inline-block;font-size:0.68em;font-weight:800;
  padding:3px 9px;border-radius:20px;letter-spacing:0.07em;margin-left:5px;}
.info-chip{display:inline-block;background:#EFF6FF;color:#2563EB;border-radius:20px;
  font-size:0.72em;font-weight:600;padding:3px 9px;margin:2px 2px;}
/* ── Upcoming banner cards ── */
.upcoming-card{border-radius:12px;padding:14px 16px;border:1px solid;margin-bottom:4px;}
/* ── Calendar ── */
.ev-cal-cell{border-radius:12px;padding:10px 5px 6px;text-align:center;
  min-height:120px;margin-bottom:2px;border:1.5px solid transparent;
  box-shadow:0 1px 4px rgba(0,0,0,0.06);}
.evcell-high  {background:#FFF5F5;border-color:#FECACA;}
.evcell-med   {background:#FFFBEB;border-color:#FDE68A;}
.evcell-low   {background:#F0FDF4;border-color:#86EFAC;}
.evcell-empty {background:#F8FAFC;border-color:#E2E8F0;}
.evcell-today {outline:2.5px solid #2563EB;outline-offset:2px;border-radius:12px;}
.evcell-sel   {outline:2.5px solid #7C3AED;outline-offset:2px;border-radius:12px;}
.ev-day-num{font-size:1.65em;font-weight:900;line-height:1;
  margin-bottom:4px;color:#1E293B;letter-spacing:-0.02em;}
.evcell-empty .ev-day-num{color:#CBD5E1;}
.ev-chip{font-size:0.84em;font-weight:700;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;padding:1px 4px;border-radius:4px;margin:1px 2px;
  display:block;text-align:left;}
.cal-hdr{text-align:center;font-size:0.78em;font-weight:700;letter-spacing:0.09em;
  text-transform:uppercase;padding:8px 2px;border-radius:8px;margin-bottom:6px;}
/* ── Filter bar ── */
.filter-bar{background:white;border:1px solid #E2E8F0;border-radius:12px;
  padding:14px 18px;margin:12px 0 8px;box-shadow:0 1px 4px rgba(0,0,0,0.04);}
/* ── Sidebar ── */
section[data-testid="stSidebar"]{background:#F0F7FF;}
.page-title{font-size:2em;font-weight:900;color:#1E293B;
  letter-spacing:-0.03em;margin-bottom:2px;}
.page-sub{font-size:0.88em;color:#64748B;margin-bottom:14px;}
</style>
""", unsafe_allow_html=True)

# Session state
for k,v in {'ev_yr':datetime.today().year,'ev_mo':datetime.today().month,
             'ev_sel':None}.items():
    if k not in st.session_state: st.session_state[k]=v

def load_data():
    if not os.path.exists(EVENTS_FILE): return pd.DataFrame()
    try:
        df=pd.read_excel(EVENTS_FILE)
        df['Date']=pd.to_datetime(df['Date'])
        return df
    except: return pd.DataFrame()

def run_scan():
    try:
        subprocess.run([sys.executable,"eventapicall.py"],cwd=parent_dir,check=True)
        return True,"Scan complete!"
    except Exception as e: return False,str(e)

df=load_data()
today=pd.Timestamp(date.today())

# ── SIDEBAR ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🎫 Events Intel")
    if not df.empty:
        upcoming=df[df['Date']>=today].sort_values('Date')
        past    =df[df['Date']< today]
        st.metric("Upcoming Events",len(upcoming))
        st.metric("Past Events",    len(past))
        if 'Impact Score' in df.columns:
            st.metric("🔴 High Impact",len(df[df['Impact Score']>=8]))
        if not upcoming.empty:
            nev=upcoming.iloc[0]
            days_away=(nev['Date'].date()-date.today()).days
            st.markdown("---")
            st.markdown("**⚡ Next Event**")
            st.markdown(
                f"<div style='background:#FEF3C7;border-radius:10px;padding:10px 12px;"
                f"border:1px solid #FDE68A;font-size:0.84em'>"
                f"<b>{str(nev['Event Name'])[:35]}…</b><br>"
                f"<span style='color:#D97706'>{nev['Date'].strftime('%d %b %Y')}</span>"
                f" · {'Today!' if days_away==0 else f'in {days_away}d'}</div>",
                unsafe_allow_html=True)

# ── MAIN ─────────────────────────────────────────────────────────
st.markdown("<div class='page-title'>🎫 Event Intelligence</div>",unsafe_allow_html=True)
st.markdown("<div class='page-sub'>Live events near your store that may impact footfall and staffing</div>",unsafe_allow_html=True)

c_scan,_=st.columns([1.5,5])
with c_scan:
    if st.button("🔄 Run Live Scan",type="primary",use_container_width=True):
        with st.spinner("Scanning Ticketmaster, Eventbrite & Calendars…"):
            ok,msg=run_scan()
            if ok: st.success(msg); st.rerun()
            else:  st.error(msg)

if df.empty:
    st.info("No events found. Click **Run Live Scan** to search."); st.stop()

# ── UPCOMING BANNER ───────────────────────────────────────────────
upcoming_all=df[df['Date']>=today].sort_values('Date')
banner_evs  =upcoming_all.head(3) if not upcoming_all.empty else df.sort_values('Date',ascending=False).head(3)
banner_label="🚀 Upcoming Events" if not upcoming_all.empty else "📅 Recent Events"

st.markdown(f"### {banner_label}")
bcols=st.columns(max(len(banner_evs),1))
for i,(_,ev) in enumerate(banner_evs.iterrows()):
    score=int(ev.get('Impact Score',0)); ic=impact_color(score)
    days_away=(ev['Date'].date()-date.today()).days
    if   days_away==0:  cdown="🔴 Today!"
    elif days_away<0:   cdown=f"{abs(days_away)}d ago"
    elif days_away<=7:  cdown=f"⚡ In {days_away}d"
    else:               cdown=ev['Date'].strftime('%d %b %Y')
    with bcols[i]:
        st.markdown(
            f"<div class='upcoming-card' style='background:{ic}11;border-color:{ic}55'>"
            f"<div style='font-weight:800;color:#1E293B;font-size:0.93em;line-height:1.3;"
            f"margin-bottom:4px'>{str(ev['Event Name'])}</div>"
            f"<div style='color:#64748B;font-size:0.79em;margin-bottom:6px'>"
            f"📍 {str(ev['Venue'])[:30]}</div>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<span style='color:{ic};font-weight:700;font-size:0.84em'>{cdown}</span>"
            f"<span class='impact-badge' style='background:{ic}22;color:{ic}'>⚡{score}/10</span></div>"
            f"<div class='impact-track'><div class='impact-fill' style='width:{score*10}%'></div></div>"
            f"</div>",unsafe_allow_html=True)

st.divider()

# ── ALWAYS-VISIBLE FILTER BAR ─────────────────────────────────────
st.markdown("### 🔍 Filters")
st.markdown("<div class='filter-bar'>",unsafe_allow_html=True)

fc1,fc2,fc3,fc4=st.columns([2.5,2.5,1.5,1])

with fc1:
    score_min=int(df['Impact Score'].min()) if 'Impact Score' in df.columns else 0
    score_max=int(df['Impact Score'].max()) if 'Impact Score' in df.columns else 10
    impact_range=st.slider(
        "⚡ Impact Score Range",
        min_value=0, max_value=10,
        value=(score_min, score_max),
        help="Drag both handles to set min and max impact score"
    )
    lo,hi=impact_range
    if lo==hi:     range_lbl=f"Exactly {lo}/10"
    elif lo==0:    range_lbl=f"Up to {hi}/10"
    elif hi==10:   range_lbl=f"At least {lo}/10"
    else:          range_lbl=f"{lo}–{hi} / 10"
    st.caption(f"Showing impact: **{range_lbl}**")

with fc2:
    if 'Distance (Miles)' in df.columns and df['Distance (Miles)'].notna().any():
        d_min=float(df['Distance (Miles)'].min())
        d_max=float(df['Distance (Miles)'].max())
        # Round sensibly
        d_min_r=round(d_min,1); d_max_r=min(round(d_max+0.5,1),20.0)
        dist_range=st.slider(
            "📏 Distance Range (miles)",
            min_value=0.0, max_value=20.0,
            value=(d_min_r, d_max_r),
            step=0.1,
            help="Drag both handles to set min and max distance from your store"
        )
        dl,dh=dist_range
        if dl==0 and dh>=20:  dist_lbl="Any distance"
        elif dl==0:           dist_lbl=f"Within {dh:.1f} mi"
        elif dh>=20:          dist_lbl=f"At least {dl:.1f} mi away"
        else:                 dist_lbl=f"{dl:.1f} – {dh:.1f} mi"
        st.caption(f"Showing distance: **{dist_lbl}**")
    else:
        dist_range=(0.0,20.0); dl,dh=0.0,20.0

with fc3:
    show_past=st.checkbox("Show past events",value=True)

with fc4:
    st.write("")
    if st.button("↺ Reset",use_container_width=True):
        st.rerun()

st.markdown("</div>",unsafe_allow_html=True)

# Apply filters
lo_i,hi_i=impact_range
filt=df[(df['Impact Score']>=lo_i)&(df['Impact Score']<=hi_i)].copy()
if 'Distance (Miles)' in filt.columns:
    dl,dh=dist_range
    filt=filt[(filt['Distance (Miles)']>=dl)&(filt['Distance (Miles)']<=dh)]
if not show_past:
    filt=filt[filt['Date']>=today]
filt=filt.sort_values('Date')

total_f=len(filt)
st.markdown(
    f"<div style='color:#64748B;font-size:0.86em;margin:4px 0 10px'>"
    f"<b style='color:#1E293B'>{total_f}</b> event{'s' if total_f!=1 else ''} match your filters"
    f"</div>",unsafe_allow_html=True)

# Build date→events map (for calendar)
ev_by_date={}
for _,row in filt.iterrows():
    d=row['Date'].date()
    ev_by_date.setdefault(d,[]).append(row)

# ── TABS: CARDS | CALENDAR | MAP ─────────────────────────────────
tab_cards,tab_cal,tab_map=st.tabs(["🃏 Event Cards","📅 Calendar View","🗺️ Map View"])

# ═══════════════════════════════════════════════════════════════
# CARDS TAB
# ═══════════════════════════════════════════════════════════════
with tab_cards:
    if filt.empty:
        st.info("No events match your filters.")
    else:
        cols=st.columns(3)
        for i,(_,ev) in enumerate(filt.iterrows()):
            score =int(ev.get('Impact Score',0)); ic=impact_color(score); il=impact_label(score)
            footfall=int(ev.get('Est. Footfall',0)); dist=ev.get('Distance (Miles)',None)
            is_past=(ev['Date']<today)
            maps_url=(f"https://www.google.com/maps/search/?api=1&query="
                      f"{ev.get('Lat','')},{ev.get('Lon','')}"
                      if pd.notna(ev.get('Lat')) else None)
            with cols[i%3]:
                op='opacity:0.60;' if is_past else ''
                st.markdown(
                    f"<div class='event-card' style='{op}'>"
                    f"<div class='card-header' style='background:{ic}11;border-bottom:3px solid {ic}'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                    f"<div style='font-weight:800;color:#1E293B;font-size:0.92em;line-height:1.3;flex:1'>"
                    f"{str(ev['Event Name'])}</div>"
                    f"<span class='impact-badge' style='background:{ic};color:white;flex-shrink:0;margin-left:8px'>"
                    f"{il}</span></div>"
                    f"<div style='color:#64748B;font-size:0.79em;margin-top:5px'>"
                    f"{'🕰' if is_past else '📅'} {ev['Date'].strftime('%a %d %b %Y')} · "
                    f"{str(ev.get('Start Time',''))[:5]}</div></div>"
                    f"<div class='card-body'>"
                    f"<div style='color:#374151;font-size:0.84em;margin:8px 0 4px'>"
                    f"📍 {str(ev['Venue'])}</div>"
                    f"<div style='margin:5px 0'>"
                    +(f"<span class='info-chip'>📏 {dist:.1f} mi</span>" if dist and pd.notna(dist) else '')
                    +f"<span class='info-chip'>👥 {footfall:,}</span>"
                    f"<span class='info-chip'>⚡ {score}/10</span></div>"
                    f"<div style='font-size:0.73em;color:#94A3B8;margin-top:3px'>Impact score</div>"
                    f"<div class='impact-track'><div class='impact-fill' style='width:{score*10}%'></div></div>"
                    f"</div></div>",unsafe_allow_html=True)
                if maps_url:
                    st.markdown(
                        f"<div style='padding:0 14px 10px;margin-top:-8px'>"
                        f"<a href='{maps_url}' target='_blank' "
                        f"style='font-size:0.78em;color:#2563EB;text-decoration:none;font-weight:600'>"
                        f"🗺 Open in Maps →</a></div>",unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# CALENDAR TAB
# ═══════════════════════════════════════════════════════════════
with tab_cal:
    yr=st.session_state.ev_yr; mo=st.session_state.ev_mo

    # Month nav
    cn1,cn2,cn3=st.columns([1,6,1])
    with cn1:
        if st.button("◀",use_container_width=True,key="ecp"):
            st.session_state.ev_mo=12 if mo==1 else mo-1
            if mo==1: st.session_state.ev_yr=yr-1
            st.session_state.ev_sel=None; st.rerun()
    with cn2:
        st.markdown(
            f"<h3 style='text-align:center;margin:0;color:#1E293B;font-weight:800'>"
            f"{datetime(yr,mo,1).strftime('%B %Y')}</h3>",unsafe_allow_html=True)
    with cn3:
        if st.button("▶",use_container_width=True,key="ecn"):
            st.session_state.ev_mo=1 if mo==12 else mo+1
            if mo==12: st.session_state.ev_yr=yr+1
            st.session_state.ev_sel=None; st.rerun()

    # Legend
    lleg=st.columns([1,1,1,4])
    lleg[0].markdown("<span style='color:#DC2626;font-weight:700'>🔴 High (8–10)</span>",unsafe_allow_html=True)
    lleg[1].markdown("<span style='color:#D97706;font-weight:700'>🟡 Med (5–7)</span>", unsafe_allow_html=True)
    lleg[2].markdown("<span style='color:#16A34A;font-weight:700'>🟢 Low (0–4)</span>", unsafe_allow_html=True)
    st.write("")

    # Day headers
    DAYS=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    hc=st.columns(7)
    for i,dn in enumerate(DAYS):
        bg="#FEE2E2" if i>=5 else "#EFF6FF"; tc="#DC2626" if i>=5 else "#1D4ED8"
        hc[i].markdown(f"<div class='cal-hdr' style='background:{bg};color:{tc}'>{dn}</div>",
                       unsafe_allow_html=True)

    today_d=date.today()
    sel_d  =st.session_state.ev_sel

    for wr in calendar.monthcalendar(yr,mo):
        cols=st.columns(7)
        for di,dn2 in enumerate(wr):
            with cols[di]:
                if dn2==0:
                    st.markdown("<div style='min-height:123px'></div>",unsafe_allow_html=True)
                    continue

                curr    =date(yr,mo,dn2)
                day_evs =ev_by_date.get(curr,[])
                is_today=(curr==today_d)
                is_sel  =(sel_d==curr)

                # Cell background from highest impact on that day
                if day_evs:
                    max_sc=max(int(e.get('Impact Score',0)) for e in day_evs)
                    if   max_sc>=8: cc='evcell-high'
                    elif max_sc>=5: cc='evcell-med'
                    else:           cc='evcell-low'
                else:
                    cc='evcell-empty'

                rings=[]
                if is_today: rings.append('evcell-today')
                if is_sel:   rings.append('evcell-sel')
                ring_style=' '.join(rings)

                # Event chips (up to 2)
                chips_html=''
                for ev_row in day_evs[:2]:
                    sc =int(ev_row.get('Impact Score',0))
                    ic =impact_color(sc)
                    nm =str(ev_row['Event Name'])
                    # Extract team names (before bracket/dash separators)
                    short=nm.split('(')[0].split('[')[0].strip()[:22]
                    tm  =str(ev_row.get('Start Time',''))[:5]
                    chips_html+=(
                        f"<div class='ev-chip' "
                        f"style='background:{ic}18;color:{ic};border-left:3px solid {ic}'>"
                        f"{short}</div>"
                        f"<div style='font-size:0.76em;color:#94A3B8;padding:0 4px;"
                        f"margin-bottom:2px'>{tm}</div>"
                    )
                if len(day_evs)>2:
                    chips_html+=(f"<div style='font-size:0.76em;color:#64748B;font-weight:600;"
                                 f"padding:0 4px'>+{len(day_evs)-2} more</div>")

                st.markdown(
                    f"<div class='ev-cal-cell {cc} {ring_style}'>"
                    f"<div class='ev-day-num'>{dn2}</div>"
                    f"{chips_html}</div>",
                    unsafe_allow_html=True)

                # Button: show/hide day detail
                btn_lbl ="👁" if day_evs else "·"
                btn_type="secondary"
                if st.button(btn_lbl,key=f"ec_{yr}_{mo}_{dn2}",
                             use_container_width=True,type=btn_type):
                    st.session_state.ev_sel=(None if sel_d==curr else curr)
                    st.rerun()

    # ── Day detail panel ─────────────────────────────────────────
    if sel_d:
        day_evs=ev_by_date.get(sel_d,[])
        st.markdown("---")
        cl,ct=st.columns([0.4,7])
        with cl:
            if st.button("✕",key="ecclose"): st.session_state.ev_sel=None; st.rerun()
        with ct:
            st.markdown(f"**📅 {sel_d.strftime('%A, %d %B %Y')}**")

        if not day_evs:
            st.info("No events on this day match your current filters.")
        else:
            for ev_row in day_evs:
                sc   =int(ev_row.get('Impact Score',0)); ic=impact_color(sc); il=impact_label(sc)
                dist =ev_row.get('Distance (Miles)',None)
                foot =int(ev_row.get('Est. Footfall',0))
                tm   =str(ev_row.get('Start Time',''))[:5]
                etime=str(ev_row.get('End Time',''))[:5]
                maps_url=(f"https://www.google.com/maps/search/?api=1&query="
                          f"{ev_row.get('Lat','')},{ev_row.get('Lon','')}"
                          if pd.notna(ev_row.get('Lat')) else None)
                mc1,mc2=st.columns([5,1])
                with mc1:
                    st.markdown(
                        f"<div style='background:{ic}0D;border:1px solid {ic}44;"
                        f"border-left:5px solid {ic};border-radius:10px;padding:12px 16px;"
                        f"margin:6px 0'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                        f"<b style='color:#1E293B;font-size:1.0em'>{str(ev_row['Event Name'])}</b>"
                        f"<span class='impact-badge' style='background:{ic};color:white'>{il} {sc}/10</span>"
                        f"</div>"
                        f"<div style='color:#64748B;margin:5px 0;font-size:0.86em'>"
                        f"📍 {str(ev_row['Venue'])} &nbsp;·&nbsp; ⏰ {tm}–{etime}</div>"
                        f"<div>"
                        +(f"<span class='info-chip'>📏 {dist:.2f} mi</span>" if dist and pd.notna(dist) else '')
                        +f"<span class='info-chip'>👥 {foot:,} footfall</span>"
                        f"</div>"
                        f"<div style='margin-top:8px'>"
                        f"<div style='font-size:0.73em;color:#94A3B8;margin-bottom:3px'>Impact</div>"
                        f"<div class='impact-track' style='height:9px'>"
                        f"<div class='impact-fill' style='width:{sc*10}%'></div></div>"
                        f"</div></div>",
                        unsafe_allow_html=True)
                with mc2:
                    if maps_url:
                        st.write("")
                        st.link_button("🗺 Map",maps_url,use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# MAP TAB
# ═══════════════════════════════════════════════════════════════
with tab_map:
    map_data=filt.copy()
    if 'Lat' in map_data.columns:
        map_data=map_data[map_data['Lat'].notna()&(map_data['Lat']!=0)]

    if map_data.empty:
        st.warning("No valid location data for the filtered events.")
    else:
        map_data['Display_Date']=map_data['Date'].dt.strftime('%d %b %Y')
        map_data['Display_Time']=map_data['Start Time'].astype(str).str[:5]
        # Dot colour by impact
        def dot_rgb(s):
            if s>=8:   return [220,38,38]
            elif s>=5: return [217,119,6]
            else:      return [22,163,74]
        map_data[['cr','cg','cb']]=pd.DataFrame(
            map_data['Impact Score'].apply(dot_rgb).tolist(), index=map_data.index)

        layer=pdk.Layer(
            "ScatterplotLayer",map_data,
            get_position=["Lon","Lat"],
            get_color=["cr","cg","cb",210],
            get_radius=14,radius_units="pixels",
            radius_min_pixels=10,radius_max_pixels=28,
            pickable=True)

        view=pdk.ViewState(
            latitude=map_data['Lat'].mean(),
            longitude=map_data['Lon'].mean(),
            zoom=12,pitch=0)

        tt=("<b>📅 {Display_Date} · ⏰ {Display_Time}</b><br/>"
            "<b>{Event Name}</b><br/>"
            "📍 {Venue}<br/>"
            "⚡ Impact: {Impact Score}/10 · 👥 {Est. Footfall}")

        st.pydeck_chart(
            pdk.Deck(
                api_keys={"mapbox":"pk.eyJ1IjoibmFtZWJyYW5kb24iLCJhIjoiY21qZDU5bW9wMDNrdTNlczhrbGc3bDF4YyJ9.TfxRdjiYH-L5GQWpW1bSkA"},
                map_style='mapbox://styles/mapbox/light-v10',
                initial_view_state=view, layers=[layer],
                tooltip={"html":tt,"style":{"color":"white","background-color":"#1E293B",
                                            "border-radius":"8px","padding":"8px 12px"}}
            ),
            use_container_width=True, height=620)

        # Map legend
        lc=st.columns(3)
        for col,lbl,clr in [(lc[0],"Low Impact (0–4)","#16A34A"),
                            (lc[1],"Medium Impact (5–7)","#D97706"),
                            (lc[2],"High Impact (8–10)","#DC2626")]:
            col.markdown(
                f"<div style='display:flex;align-items:center;gap:7px;font-size:0.83em;"
                f"padding:4px 0'><span style='width:13px;height:13px;border-radius:50%;"
                f"background:{clr};display:inline-block;flex-shrink:0'></span>{lbl}</div>",
                unsafe_allow_html=True)