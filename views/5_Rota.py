# views/5_Rota.py
import streamlit as st
import pandas as pd
import os
import time
import io
import calendar
from datetime import datetime, date, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# =====================================================
# CLOUD READY PATHS
# =====================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EMPLOYEE_FILE = os.path.join(BASE_DIR, "Book(Employees)_01.xlsx")
HOLIDAY_FILE  = os.path.join(BASE_DIR, "Holidaydata.xlsx")
OUTPUT_FILE   = os.path.join(BASE_DIR, "Final_Rota_MultiSheet.xlsx")

# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Rota Dashboard",
    layout="wide"
)

# =====================================================
# ROLE COLORS
# =====================================================

ROLE_COLORS = {
    "Manager": {
        "bg": "#DBEAFE",
        "text": "#1D4ED8",
        "bar": "#2563EB"
    },
    "Shift Leader": {
        "bg": "#EDE9FE",
        "text": "#6D28D9",
        "bar": "#7C3AED"
    },
    "Team Leader": {
        "bg": "#CFFAFE",
        "text": "#0E7490",
        "bar": "#0891B2"
    },
    "Associate": {
        "bg": "#F1F5F9",
        "text": "#374151",
        "bar": "#64748B"
    }
}

DEFAULT_ROLE = {
    "bg": "#F1F5F9",
    "text": "#374151",
    "bar": "#94A3B8"
}

# =====================================================
# CSS
# =====================================================

st.markdown("""
<style>
html, body, [class*="css"]{
    font-family: Inter, sans-serif;
}

.page-title{
    font-size:2rem;
    font-weight:800;
    color:#111827;
}

.page-sub{
    color:#6B7280;
    margin-bottom:18px;
}

.cal-cell{
    border-radius:14px;
    padding:14px 6px 8px;
    text-align:center;
    min-height:125px;
    border:1px solid #E5E7EB;
    background:white;
}

.cell-rota{
    background:#ECFDF5;
}

.cell-sched{
    background:#FFFBEB;
}

.cell-empty{
    background:#F9FAFB;
}

.cell-today{
    outline:2px solid #2563EB;
}

.day-num{
    font-size:2.2rem;
    font-weight:800;
}

.day-badge{
    display:inline-block;
    padding:4px 10px;
    border-radius:20px;
    font-size:0.75rem;
    font-weight:700;
}

.badge-rota{
    background:#16A34A;
    color:white;
}

.badge-sched{
    background:#D97706;
    color:white;
}

.badge-empty{
    background:#E5E7EB;
    color:#6B7280;
}

.timeline{
    background:#EFF6FF;
    border-radius:8px;
    height:28px;
    position:relative;
    overflow:hidden;
}

.timeline-bar{
    position:absolute;
    top:0;
    height:100%;
    border-radius:8px;
    color:white;
    font-size:0.75rem;
    font-weight:700;
    display:flex;
    align-items:center;
    justify-content:center;
}

.staff-card{
    border:1px solid #E5E7EB;
    border-radius:14px;
    padding:12px;
    background:white;
    margin-bottom:10px;
}

.role-pill{
    display:inline-block;
    padding:2px 8px;
    border-radius:20px;
    font-size:0.7rem;
    font-weight:700;
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# SESSION
# =====================================================

defaults = {
    "view": "calendar",
    "cal_year": datetime.today().year,
    "cal_month": datetime.today().month,
    "selected_date": None,
    "week_start": None
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =====================================================
# HELPERS
# =====================================================

def get_week_start(d):

    if isinstance(d, datetime):
        d = d.date()

    return d - timedelta(days=d.weekday())


def nav(view, selected_date=None, week_start=None):

    st.session_state.view = view

    if selected_date is not None:
        st.session_state.selected_date = selected_date

    if week_start is not None:
        st.session_state.week_start = week_start

    st.rerun()


def calc_hours(val):

    if not isinstance(val, str):
        return 0

    if " - " not in val:
        return 0

    try:
        a, b = val.split(" - ")

        sh = int(a.split(":")[0])
        eh = int(b.split(":")[0])

        if eh == 0:
            eh = 24

        return eh - sh

    except:
        return 0


# =====================================================
# DATA LOADERS
# =====================================================

@st.cache_data(ttl=15)
def get_generated_weeks():

    result = {}

    if not os.path.exists(OUTPUT_FILE):
        return result

    try:

        xls = pd.ExcelFile(OUTPUT_FILE)

        for sheet in xls.sheet_names:

            df = pd.read_excel(
                OUTPUT_FILE,
                sheet_name=sheet,
                nrows=1
            )

            cols = [
                c for c in df.columns
                if c not in [
                    "Name",
                    "Employee ID",
                    "Total Weekly Hours"
                ]
            ]

            if cols:

                d = datetime.strptime(
                    cols[0].split(" ")[0],
                    "%Y-%m-%d"
                ).date()

                result[get_week_start(d)] = sheet

    except:
        pass

    return result


@st.cache_data(ttl=15)
def get_scheduling_weeks():

    if not os.path.exists(EMPLOYEE_FILE):
        return set()

    try:

        df = pd.read_excel(
            EMPLOYEE_FILE,
            sheet_name="Shift Templates"
        )

        df["Date"] = pd.to_datetime(df["Date"])

        return {
            get_week_start(x.date())
            for x in df["Date"]
        }

    except:
        return set()


@st.cache_data(ttl=30)
def get_employee_roles():

    if not os.path.exists(EMPLOYEE_FILE):
        return {}

    try:

        df = pd.read_excel(
            EMPLOYEE_FILE,
            sheet_name="Employees"
        )

        df.columns = df.columns.str.strip()

        return {
            str(n).strip(): str(r).strip()
            for n, r in zip(
                df["Name"],
                df["Designation"]
            )
        }

    except:
        return {}


def load_week(sheet_name):

    try:
        return pd.read_excel(
            OUTPUT_FILE,
            sheet_name=sheet_name
        )
    except:
        return pd.DataFrame()


def create_pdf(df, title):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter)
    )

    styles = getSampleStyleSheet()

    items = [
        Paragraph(
            f"<b>{title}</b>",
            styles["Title"]
        )
    ]

    data = [df.columns.tolist()]

    for _, row in df.iterrows():
        data.append(
            [str(x) for x in row.tolist()]
        )

    table = Table(data)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))

    items.append(table)

    doc.build(items)

    buffer.seek(0)

    return buffer

def clear_caches():
    for fn in [get_generated_weeks,get_week_total_hours,
               get_scheduling_weeks,get_schedule_budget]: fn.clear()

def nav_to(view,sel_date=None,week_start=None):
    st.session_state.view=view
    if sel_date   is not None: st.session_state.selected_date=sel_date
    if week_start is not None: st.session_state.week_start=week_start
    clear_caches(); st.rerun()

# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:

    gen = get_generated_weeks()
    sched = get_scheduling_weeks()

    st.markdown("### 📊 Overview", unsafe_allow_html=True)

    st.metric(
        "Rotas Ready",
        len(gen)
    )

    st.metric(
        "Weeks Planned",
        len(sched)
    )

    if st.session_state.week_start:

        ws = st.session_state.week_start
        we = ws + timedelta(days=6)

        st.markdown("---", unsafe_allow_html=True)

        st.markdown(
            f"**📅 {ws.strftime('%d %b')} - {we.strftime('%d %b %Y')}**"
        , unsafe_allow_html=True)

# =====================================================
# VIEW 1 : CALENDAR
# =====================================================

def show_calendar():

    yr = st.session_state.cal_year
    mo = st.session_state.cal_month

    generated = get_generated_weeks()
    planned = get_scheduling_weeks()

    st.markdown(
        "<div class='page-title'>🚀 Rota Dashboard</div>",
        unsafe_allow_html=True
    )

    st.markdown(
        "<div class='page-sub'>Open any generated rota week</div>",
        unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns([1, 5, 1])

    with c1:

        if st.button("◀"):

            if mo == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1

            st.rerun()

    with c2:

        st.markdown(
            f"## {datetime(yr, mo, 1).strftime('%B %Y')}"
        , unsafe_allow_html=True)

    with c3:

        if st.button("▶"):

            if mo == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1

            st.rerun()

    st.write("")

    headers = st.columns(7)

    for i, d in enumerate(
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    ):
        headers[i].markdown(f"**{d}**")

    for week in calendar.monthcalendar(yr, mo):

        cols = st.columns(7)

        for i, day_num in enumerate(week):

            with cols[i]:

                if day_num == 0:
                    st.write("")
                    continue

                curr = date(yr, mo, day_num)

                ws = get_week_start(curr)

                today = curr == date.today()

                if ws in generated:
                    css = "cell-rota"
                    badge = "badge-rota"
                    label = "Rota Ready"

                elif ws in planned:
                    css = "cell-sched"
                    badge = "badge-sched"
                    label = "Planned"

                else:
                    css = "cell-empty"
                    badge = "badge-empty"
                    label = "None"

                extra = " cell-today" if today else ""

                st.markdown(
                    f"""
                    <div class='cal-cell {css}{extra}'>
                        <div class='day-num'>{day_num}</div>
                        <span class='day-badge {badge}'>
                            {label}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if ws in generated:

                    if st.button(
                        "View",
                        key=f"v_{yr}_{mo}_{day_num}"
                    ):
                        nav(
                            "week",
                            week_start=ws
                        )

# =====================================================
# VIEW 2 : WEEK VIEW
# =====================================================

def show_week():

    ws = st.session_state.week_start

    generated = get_generated_weeks()

    sheet = generated.get(ws)

    if not sheet:
        st.error("No rota found.")
        return

    df = load_week(sheet)

    we = ws + timedelta(days=6)

    st.markdown(
        f"<div class='page-title'>📅 {ws.strftime('%d %b')} - {we.strftime('%d %b %Y')}</div>",
        unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns([1, 1, 4])

    with c1:

        if st.button("◀ Back"):
            nav("calendar")

    with c2:

        if st.button("📆 Day View"):

            first_day = ws
            nav(
                "day",
                selected_date=first_day,
                week_start=ws
            )

    st.write("")

    # Metrics

    total_hours = 0

    if "Total Weekly Hours" in df.columns:
        total_hours = df["Total Weekly Hours"].sum()

    m1, m2, m3 = st.columns(3)

    m1.metric("Staff", len(df))
    m2.metric("Hours", int(total_hours))
    m3.metric("Week", ws.isocalendar()[1])

    st.divider()

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    d1, d2 = st.columns(2)

    with d1:

        excel_buffer = io.BytesIO()

        with pd.ExcelWriter(
            excel_buffer,
            engine="openpyxl"
        ) as writer:

            df.to_excel(
                writer,
                sheet_name="Rota",
                index=False
            )

        st.download_button(
            "⬇ Download Excel",
            excel_buffer.getvalue(),
            file_name=f"Rota_Week_{ws.isocalendar()[1]}.xlsx"
        )

    with d2:

        pdf = create_pdf(
            df,
            f"Rota Week {ws.isocalendar()[1]}"
        )

        st.download_button(
            "⬇ Download PDF",
            pdf,
            file_name=f"Rota_Week_{ws.isocalendar()[1]}.pdf",
            mime="application/pdf"
        )

# =====================================================
# VIEW 3 : DAY VIEW
# =====================================================

def show_day():

    ws = st.session_state.week_start
    selected = st.session_state.selected_date

    generated = get_generated_weeks()
    sheet = generated.get(ws)

    if not sheet:
        st.error("No rota found.")
        return

    df = load_week(sheet)

    if df.empty:
        st.error("No rota data.")
        return

    # Build date columns
    date_cols = [
        c for c in df.columns
        if c not in [
            "Name",
            "Employee ID",
            "Total Weekly Hours"
        ]
    ]

    if not selected:
        selected = ws

    selected_key = selected.strftime("%Y-%m-%d")

    active_col = None

    for c in date_cols:
        if c.startswith(selected_key):
            active_col = c
            break

    if not active_col:
        st.warning("No rota for selected day.")
        return

    st.markdown(
        f"<div class='page-title'>📍 {selected.strftime('%A %d %B %Y')}</div>",
        unsafe_allow_html=True
    )

    c1, c2, c3, c4 = st.columns([1,1,1,4])

    with c1:
        if st.button("◀ Week"):
            nav(
                "week",
                week_start=ws
            )

    with c2:
        prev_day = selected - timedelta(days=1)

        if prev_day >= ws:
            if st.button("⬅ Prev"):
                nav(
                    "day",
                    selected_date=prev_day,
                    week_start=ws
                )

    with c3:
        next_day = selected + timedelta(days=1)

        if next_day <= ws + timedelta(days=6):
            if st.button("Next ➡"):
                nav(
                    "day",
                    selected_date=next_day,
                    week_start=ws
                )

    st.write("")

    # =================================================
    # DAY DATA
    # =================================================

    workers = []
    off_staff = []

    roles = get_employee_roles()

    for _, row in df.iterrows():

        name = str(row.get("Name", ""))
        shift = str(row.get(active_col, "OFF"))

        role = roles.get(name, "Associate")

        if shift.upper() in ["OFF", "HOLIDAY", ""]:
            off_staff.append({
                "Name": name,
                "Role": role,
                "Shift": shift
            })
        else:
            workers.append({
                "Name": name,
                "Role": role,
                "Shift": shift
            })

    # =================================================
    # METRICS
    # =================================================

    total_hours = 0

    for x in workers:
        total_hours += calc_hours(x["Shift"])

    m1, m2, m3 = st.columns(3)

    m1.metric("Working", len(workers))
    m2.metric("Off", len(off_staff))
    m3.metric("Hours", total_hours)

    st.divider()

    # =================================================
    # WORKING STAFF
    # =================================================

    st.markdown("### 👷 Working Staff", unsafe_allow_html=True)

    if not workers:
        st.info("Nobody working.")
    else:

        for person in workers:

            role = person["Role"]
            clr = ROLE_COLORS.get(role, DEFAULT_ROLE)

            shift = person["Shift"]

            try:
                a, b = shift.split(" - ")

                sh = int(a.split(":")[0])
                eh = int(b.split(":")[0])

                if eh == 0:
                    eh = 24

                left = (sh / 24) * 100
                width = ((eh - sh) / 24) * 100

            except:
                left = 0
                width = 0

            st.markdown(
                f"""
                <div class='staff-card'>

                    <div style='display:flex;justify-content:space-between'>
                        <div>
                            <b>{person["Name"]}</b>
                            <span class='role-pill'
                            style='background:{clr["bg"]};color:{clr["text"]};margin-left:8px'>
                            {role}
                            </span>
                        </div>

                        <div style='font-weight:700'>
                            {shift}
                        </div>
                    </div>

                    <div style='margin-top:10px' class='timeline'>
                        <div class='timeline-bar'
                        style='left:{left}%;width:{width}%;background:{clr["bar"]}'>
                        </div>
                    </div>

                </div>
                """,
                unsafe_allow_html=True
            )

    # =================================================
    # OFF STAFF
    # =================================================

    st.markdown("### 💤 Off / Holiday", unsafe_allow_html=True)

    if not off_staff:
        st.success("Everyone scheduled.")
    else:

        for person in off_staff:

            role = person["Role"]
            clr = ROLE_COLORS.get(role, DEFAULT_ROLE)

            label = person["Shift"]

            if label == "HOLIDAY":
                badge = "🏖 Holiday"
            else:
                badge = "❌ Off"

            st.markdown(
                f"""
                <div class='staff-card'>
                    <div style='display:flex;justify-content:space-between'>
                        <div>
                            <b>{person["Name"]}</b>
                            <span class='role-pill'
                            style='background:{clr["bg"]};color:{clr["text"]};margin-left:8px'>
                            {role}
                            </span>
                        </div>

                        <div style='font-weight:700;color:#6B7280'>
                            {badge}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

# =====================================================
# MAIN ROUTER
# =====================================================

if st.session_state.view == "calendar":
    show_calendar()

elif st.session_state.view == "week":
    show_week()

elif st.session_state.view == "day":
    show_day()
