import streamlit as st
import pandas as pd
import os
import io
import time
import calendar
from datetime import datetime, timedelta, date
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# ======================================================
# PAGE CONFIG
# ======================================================

st.set_page_config(
    page_title="Rota Dashboard",
    layout="wide"
)

# ======================================================
# PATHS (CLOUD SAFE)
# ======================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EMPLOYEE_FILE = os.path.join(BASE_DIR, "Book(Employees)_01.xlsx")
HOLIDAY_FILE = os.path.join(BASE_DIR, "Holidaydata.xlsx")
ROTA_FILE = os.path.join(BASE_DIR, "Final_Rota_MultiSheet.xlsx")

# ======================================================
# IMPORT SCHEDULER
# ======================================================

try:
    from scheduler_h_s import solve_rota_final_v14
except:
    solve_rota_final_v14 = None

# ======================================================
# STYLE
# ======================================================

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: Inter, sans-serif;
}

.page-title{
    font-size:2rem;
    font-weight:800;
    color:#111827;
}

.page-sub{
    color:#6B7280;
    margin-bottom:12px;
}

.role-pill{
    display:inline-block;
    padding:4px 10px;
    border-radius:20px;
    font-size:0.72rem;
    font-weight:700;
}

.day-box{
    border:1px solid #E5E7EB;
    border-radius:12px;
    padding:10px;
    background:white;
}

.staff-card{
    border:1px solid #E5E7EB;
    border-radius:12px;
    padding:12px;
    margin-bottom:10px;
    background:white;
}

.timeline{
    height:10px;
    background:#EEF2FF;
    border-radius:30px;
    overflow:hidden;
}

.timeline-bar{
    height:10px;
    border-radius:30px;
}

.metric-box{
    border:1px solid #E5E7EB;
    border-radius:12px;
    padding:12px;
    background:white;
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# ROLE COLORS
# ======================================================

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
    "bar": "#64748B"
}

# ======================================================
# SESSION STATE
# ======================================================

defaults = {
    "view": "calendar",
    "week_start": None,
    "day_col": None,
    "sheet_name": None
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ======================================================
# HELPERS
# ======================================================

def nav_to(view, ws=None, col=None, sheet=None):

    st.session_state.view = view

    if ws is not None:
        st.session_state.week_start = ws

    if col is not None:
        st.session_state.day_col = col

    if sheet is not None:
        st.session_state.sheet_name = sheet

    st.rerun()


@st.cache_data
def load_rota_sheets():

    if not os.path.exists(ROTA_FILE):
        return {}

    try:

        xls = pd.ExcelFile(ROTA_FILE)

        sheets = {}

        for sh in xls.sheet_names:

            df = pd.read_excel(
                ROTA_FILE,
                sheet_name=sh
            )

            sheets[sh] = df

        return sheets

    except:
        return {}


@st.cache_data
def load_employees():

    if not os.path.exists(EMPLOYEE_FILE):
        return pd.DataFrame()

    try:
        return pd.read_excel(
            EMPLOYEE_FILE,
            sheet_name="Employees"
        )
    except:
        return pd.DataFrame()


def get_employee_roles():

    df = load_employees()

    roles = {}

    if df.empty:
        return roles

    for _, row in df.iterrows():

        nm = str(row.get("Name", "")).strip()

        rl = str(
            row.get("Designation", "Associate")
        ).strip()

        roles[nm] = rl

    return roles

# ======================================================
# MORE HELPERS
# ======================================================

def parse_week_start(sheet_name):

    try:
        num = int(
            str(sheet_name).replace("Week ", "").strip()
        )

        year = datetime.today().year

        dt = datetime.fromisocalendar(
            year, num, 1
        )

        return dt.date()

    except:
        return None


def get_all_weeks():

    sheets = load_rota_sheets()

    weeks = []

    for sh in sheets.keys():

        ws = parse_week_start(sh)

        if ws:
            weeks.append((ws, sh))

    weeks = sorted(weeks, key=lambda x: x[0])

    return weeks


def calc_hours(shift):

    try:

        if " - " not in shift:
            return 0

        a, b = shift.split(" - ")

        sh = int(a.split(":")[0])
        eh = int(b.split(":")[0])

        if eh == 0:
            eh = 24

        return eh - sh

    except:
        return 0


def shift_start_time(shift):

    try:

        if " - " in shift:
            return int(
                shift.split(" - ")[0].split(":")[0]
            )

    except:
        pass

    return 99


def make_excel_download():

    if not os.path.exists(ROTA_FILE):
        return None

    with open(ROTA_FILE, "rb") as f:
        return f.read()


def build_pdf(df, title):

    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter)
    )

    styles = getSampleStyleSheet()

    story = []

    story.append(
        Paragraph(title, styles["Title"])
    )

    story.append(Spacer(1, 12))

    data = [list(df.columns)]

    for _, row in df.iterrows():
        data.append(list(row.values))

    table = Table(data)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2563EB")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 8),
    ]))

    story.append(table)

    doc.build(story)

    pdf = buf.getvalue()
    buf.close()

    return pdf

# ======================================================
# SIDEBAR
# ======================================================

def render_sidebar():

    weeks = get_all_weeks()

    with st.sidebar:

        st.markdown("## 📅 Rota Navigation")

        if st.button(
            "🏠 Dashboard",
            use_container_width=True
        ):
            nav_to("calendar")

        st.divider()

        if weeks:

            for ws, sh in weeks:

                txt = ws.strftime(
                    "%d %b %Y"
                )

                if st.button(
                    f"🗓 {txt}",
                    key=f"wk_{sh}",
                    use_container_width=True
                ):
                    nav_to(
                        "week",
                        ws=ws,
                        sheet=sh
                    )

        else:
            st.info("No rota weeks found.")

        st.divider()

        raw = make_excel_download()

        if raw:

            st.download_button(
                "⬇ Download Excel",
                data=raw,
                file_name="Final_Rota_MultiSheet.xlsx",
                use_container_width=True
            )

render_sidebar()

# ======================================================
# PAGE HEADER
# ======================================================

st.markdown(
    "<div class='page-title'>🚀 Rota Dashboard</div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div class='page-sub'>Manage weekly rota, generate schedules and review staffing</div>",
    unsafe_allow_html=True
)

st.divider()

# ======================================================
# CALENDAR VIEW
# ======================================================

def show_calendar():

    weeks = get_all_weeks()

    c1, c2 = st.columns([3,1])

    with c1:
        st.subheader("Available Weeks")

    with c2:

        if st.button(
            "🚀 Generate Rota",
            use_container_width=True,
            type="primary"
        ):

            if solve_rota_final_v14:

                with st.spinner("Generating rota..."):

                    solve_rota_final_v14(
                        EMPLOYEE_FILE,
                        HOLIDAY_FILE
                    )

                st.cache_data.clear()
                st.success("Rota Generated")
                time.sleep(1)
                st.rerun()

            else:
                st.error("Scheduler not found.")

    st.write("")

    if not weeks:
        st.info("No rota weeks available.")
        return

    cols = st.columns(3)

    for i, (ws, sh) in enumerate(weeks):

        we = ws + timedelta(days=6)

        with cols[i % 3]:

            with st.container(border=True):

                st.markdown(
                    f"### Week {ws.isocalendar()[1]}"
                )

                st.caption(
                    f"{ws.strftime('%d %b')} - "
                    f"{we.strftime('%d %b %Y')}"
                )

                if st.button(
                    "Open Week",
                    key=f"open_{sh}",
                    use_container_width=True
                ):
                    nav_to(
                        "week",
                        ws=ws,
                        sheet=sh
                    )


# ======================================================
# WEEK VIEW
# ======================================================

def show_week():

    sheets = load_rota_sheets()

    sh = st.session_state.sheet_name

    if sh not in sheets:
        st.warning("Week not found.")
        return

    df = sheets[sh]

    ws = st.session_state.week_start
    we = ws + timedelta(days=6)

    top1, top2 = st.columns([4,1])

    with top1:
        st.subheader(
            f"Week {ws.isocalendar()[1]} | "
            f"{ws.strftime('%d %b')} - "
            f"{we.strftime('%d %b %Y')}"
        )

    with top2:
        if st.button(
            "⬅ Back",
            use_container_width=True
        ):
            nav_to("calendar")

    st.write("")

    day_cols = [
        c for c in df.columns
        if "(" in str(c) and ")" in str(c)
    ]

    cols = st.columns(len(day_cols))

    for i, col in enumerate(day_cols):

        label = col.split("(")[1].replace(")", "")

        workers = 0

        for _, row in df.iterrows():

            val = str(row.get(col, "OFF"))

            if val.upper() not in [
                "OFF", "HOLIDAY", ""
            ]:
                workers += 1

        with cols[i]:

            with st.container(border=True):

                st.markdown(f"### {label}")
                st.metric("Staff", workers)

                if st.button(
                    "View",
                    key=f"day_{col}",
                    use_container_width=True
                ):
                    nav_to(
                        "day",
                        ws=ws,
                        sheet=sh,
                        col=col
                    )

# ======================================================
# DAY VIEW
# ======================================================

def show_day():

    sheets = load_rota_sheets()

    sh = st.session_state.sheet_name
    col = st.session_state.day_col

    if sh not in sheets:
        st.warning("Week missing.")
        return

    df = sheets[sh]

    if col not in df.columns:
        st.warning("Day missing.")
        return

    roles = get_employee_roles()

    workers = []
    off_staff = []

    for _, row in df.iterrows():

        name = str(row.get("Name", ""))
        shift = str(row.get(col, "OFF")).strip()

        role = roles.get(name, "Associate")

        item = {
            "Name": name,
            "Role": role,
            "Shift": shift
        }

        if shift.upper() in [
            "OFF", "", "HOLIDAY"
        ]:
            off_staff.append(item)
        else:
            workers.append(item)

    workers = sorted(
        workers,
        key=lambda x: (
            shift_start_time(x["Shift"]),
            x["Name"]
        )
    )

    off_staff = sorted(
        off_staff,
        key=lambda x: x["Name"]
    )

    # HEADER

    c1, c2 = st.columns([4,1])

    with c1:
        st.subheader(col)

    with c2:
        if st.button(
            "⬅ Back",
            use_container_width=True
        ):
            nav_to(
                "week",
                ws=st.session_state.week_start,
                sheet=sh
            )

    # METRICS

    total_hours = sum(
        calc_hours(x["Shift"])
        for x in workers
    )

    m1, m2, m3 = st.columns(3)

    m1.metric("Working", len(workers))
    m2.metric("Off", len(off_staff))
    m3.metric("Hours", total_hours)

    st.divider()

    # WORKING STAFF

    st.markdown("### 👷 Working Staff")

    if not workers:
        st.info("No staff working.")
    else:

        for p in workers:

            role = p["Role"]
            clr = ROLE_COLORS.get(
                role,
                DEFAULT_ROLE
            )

            shift = p["Shift"]

            left = 0
            width = 0

            try:
                a, b = shift.split(" - ")

                sh1 = int(a[:2])
                eh1 = int(b[:2])

                if eh1 == 0:
                    eh1 = 24

                left = (sh1 / 24) * 100
                width = ((eh1 - sh1) / 24) * 100

            except:
                pass

            st.markdown(
                f"""
                <div class='staff-card'>

                    <div style='display:flex;
                                justify-content:space-between'>

                        <div>
                            <b>{p["Name"]}</b>

                            <span class='role-pill'
                            style='background:{clr["bg"]};
                            color:{clr["text"]};
                            margin-left:8px'>
                            {role}
                            </span>
                        </div>

                        <div style='font-weight:700'>
                            {shift}
                        </div>

                    </div>

                    <div style='margin-top:10px'
                         class='timeline'>

                        <div class='timeline-bar'
                        style='left:{left}%;
                               width:{width}%;
                               background:{clr["bar"]}'></div>

                    </div>

                </div>
                """,
                unsafe_allow_html=True
            )

    st.divider()

    # OFF STAFF

    st.markdown("### 💤 Off Staff")

    if not off_staff:
        st.success("Everyone working.")
    else:

        for p in off_staff:

            badge = (
                "🏖 Holiday"
                if p["Shift"].upper() == "HOLIDAY"
                else "❌ Off"
            )

            st.markdown(
                f"""
                <div class='staff-card'>
                    <b>{p["Name"]}</b>
                    <br>
                    <span style='color:#6B7280'>
                    {p["Role"]}
                    </span>
                    <br><br>
                    {badge}
                </div>
                """,
                unsafe_allow_html=True
            )

# ======================================================
# ROUTER
# ======================================================

view = st.session_state.view

if view == "calendar":
    show_calendar()

elif view == "week":
    show_week()

elif view == "day":
    show_day()
