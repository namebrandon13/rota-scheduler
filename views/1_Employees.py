import streamlit as st
import pandas as pd
import os
from datetime import time

# ======================================================
# CONFIG
# ======================================================

FILE_PATH = "Book(Employees)_01.xlsx"

ROLE_ORDER = [
    "Manager",
    "Shift Leader",
    "Team Leader",
    "Associate"
]

ROLE_COLORS = {
    "Manager": {"bg": "#DBEAFE", "text": "#1D4ED8", "border": "#93C5FD"},
    "Shift Leader": {"bg": "#EDE9FE", "text": "#6D28D9", "border": "#C4B5FD"},
    "Team Leader": {"bg": "#CFFAFE", "text": "#0E7490", "border": "#67E8F9"},
    "Associate": {"bg": "#F1F5F9", "text": "#374151", "border": "#CBD5E1"},
}

DEFAULT_ROLE = {"bg": "#F1F5F9", "text": "#374151", "border": "#CBD5E1"}

DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
]

DAY_FIXES = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Thurday": "Thursday",
    "Thrusday": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday"
}

# ======================================================
# STYLE
# ======================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

div[data-testid="stButton"] > button {
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.82em;
}

div[data-testid="stMetric"] {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 14px;
}

.page-title {
    font-size: 2em;
    font-weight: 900;
    color: #1E293B;
}

.page-sub {
    color: #64748B;
    margin-bottom: 12px;
}

.role-badge {
    display:inline-block;
    padding:4px 10px;
    border-radius:20px;
    font-size:0.75em;
    font-weight:700;
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# HELPERS
# ======================================================

def clean_days(raw):
    vals = str(raw).split(",")
    cleaned = []

    for v in vals:
        d = v.strip()

        if not d:
            continue

        d = DAY_FIXES.get(d, d)

        if d in DAYS:
            cleaned.append(d)

    return cleaned


def ensure_columns(df):
    needed = [
        "ID",
        "Name",
        "Designation",
        "Minimum Contractual Hours",
        "Max Weekly Hours",
        "Opening Trained",
        "Preferred Day",
        "Unavailable Days",
        "Fixed Shift Enabled",
        "Fixed Weekly Shift"
    ]

    for c in needed:
        if c not in df.columns:
            df[c] = ""

    return df


def load_data():
    if not os.path.exists(FILE_PATH):
        return ensure_columns(pd.DataFrame())

    try:
        df = pd.read_excel(FILE_PATH, sheet_name="Employees")
        df.columns = df.columns.str.strip()
        return ensure_columns(df)

    except:
        return ensure_columns(pd.DataFrame())


def save_data(df):
    df = ensure_columns(df.copy())

    with pd.ExcelWriter(
        FILE_PATH,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace"
    ) as writer:

        df.to_excel(
            writer,
            sheet_name="Employees",
            index=False
        )


def is_opening_trained(v):
    return str(v).strip().lower() in ["yes", "true", "1"]


# ======================================================
# EMPLOYEE FORM
# ======================================================

@st.dialog("Employee Details", width="large")
def employee_form(row_data=None, index=None):

    is_edit = row_data is not None

    def gv(key, default=""):
        if is_edit and key in row_data:
            val = row_data[key]
            if pd.notna(val):
                return val
        return default

    emp_ref = str(gv("ID", "new"))

    saved_unavailable = clean_days(
        gv("Unavailable Days", "")
    )

    saved_preferred = clean_days(
        gv("Preferred Day", "")
    )

    fixed_enabled_saved = (
        str(gv("Fixed Shift Enabled", "No")) == "Yes"
    )

    raw_fixed = str(
        gv("Fixed Weekly Shift", "")
    )

    fixed_map = {}

    if raw_fixed and raw_fixed != "nan":
        for item in raw_fixed.split(";"):
            parts = item.split("|")
            if len(parts) == 3:
                fixed_map[parts[0]] = (
                    parts[1],
                    parts[2]
                )

    # -----------------------------------
    # HEADER
    # -----------------------------------

    if is_edit:
        st.markdown("### ✏️ Edit Employee")
    else:
        st.markdown("### ➕ Add Employee")

    # -----------------------------------
    # LIVE TOGGLE OUTSIDE FORM
    # -----------------------------------

    fixed_enabled = st.checkbox(
        "Enable Fixed Shifts",
        value=fixed_enabled_saved,
        key=f"fixedshift_{emp_ref}"
    )

    st.divider()

    # -----------------------------------
    # FORM
    # -----------------------------------

    with st.form(f"employee_form_{emp_ref}"):

        tabs = st.tabs([
            "👤 Basic Info",
            "📅 Availability",
            "🔒 Fixed Shifts"
        ])

        # =====================================
        # TAB 1 BASIC INFO
        # =====================================

        with tabs[0]:

            c1, c2 = st.columns(2)

            with c1:
                name = st.text_input(
                    "Full Name",
                    value=str(gv("Name", ""))
                )

                emp_id = st.text_input(
                    "Staff ID",
                    value=str(gv("ID", "")),
                    disabled=is_edit
                )

                current_role = str(
                    gv("Designation", "Associate")
                )

                role = st.selectbox(
                    "Role",
                    ROLE_ORDER,
                    index=ROLE_ORDER.index(current_role)
                    if current_role in ROLE_ORDER else 3
                )

            with c2:
                min_h = st.number_input(
                    "Min Contract Hours",
                    0, 60,
                    value=int(float(
                        gv("Minimum Contractual Hours", 0)
                    ))
                )

                max_h = st.number_input(
                    "Max Weekly Hours",
                    0, 70,
                    value=int(float(
                        gv("Max Weekly Hours", 40)
                    ))
                )

                trained = st.checkbox(
                    "Opening Trained?",
                    value=is_opening_trained(
                        gv("Opening Trained", "No")
                    )
                )

        # =====================================
        # TAB 2 AVAILABILITY
        # =====================================

        with tabs[1]:

            st.caption("Tick days employee CAN work")

            cols = st.columns(7)

            availability = {}

            for i, day in enumerate(DAYS):
                with cols[i]:
                    availability[day] = st.checkbox(
                        day[:3],
                        value=(day not in saved_unavailable),
                        key=f"av_{day}_{emp_ref}"
                    )

            unavailable_days = [
                d for d, ok in availability.items()
                if not ok
            ]

            preferred = st.multiselect(
                "Preferred Days",
                DAYS,
                default=saved_preferred
            )

        # =====================================
        # TAB 3 FIXED SHIFTS
        # =====================================

        with tabs[2]:

            fixed_rows = []

            if not fixed_enabled:
                st.info(
                    "Enable Fixed Shifts above to use this section."
                )

            else:

                st.caption(
                    "Weekly repeating shifts that auto-assign."
                )

                for day in DAYS:

                    has_saved = day in fixed_map

                    ds = time(9, 0)
                    de = time(17, 0)

                    if has_saved:
                        try:
                            s = fixed_map[day][0]
                            e = fixed_map[day][1]

                            ds = time(
                                int(s[:2]),
                                int(s[3:5])
                            )

                            de = time(
                                int(e[:2]),
                                int(e[3:5])
                            )
                        except:
                            pass

                    st.markdown(f"**{day}**")

                    a, b, c = st.columns([1.2, 1, 1])

                    with a:
                        enabled = st.checkbox(
                            "Work",
                            value=has_saved,
                            key=f"fx_{day}_{emp_ref}"
                        )

                    with b:
                        start_t = st.time_input(
                            "Start",
                            value=ds,
                            key=f"st_{day}_{emp_ref}"
                        )

                    with c:
                        end_t = st.time_input(
                            "End",
                            value=de,
                            key=f"en_{day}_{emp_ref}"
                        )

                    if enabled:
                        fixed_rows.append(
                            f"{day}|"
                            f"{start_t.strftime('%H:%M')}|"
                            f"{end_t.strftime('%H:%M')}"
                        )

        # =====================================
        # SAVE BUTTON
        # =====================================

        submitted = st.form_submit_button(
            "💾 Save Changes",
            type="primary",
            use_container_width=True
        )

        if submitted:

            if not name.strip():
                st.error("Name required.")
                st.stop()

            if not str(emp_id).strip():
                st.error("Staff ID required.")
                st.stop()

            df = load_data()

            if not is_edit:
                if str(emp_id) in df["ID"].astype(str).tolist():
                    st.error("Staff ID already exists.")
                    st.stop()

            new_row = {
                "ID": str(emp_id).strip(),
                "Name": name.strip(),
                "Designation": role,
                "Minimum Contractual Hours": min_h,
                "Max Weekly Hours": max_h,
                "Opening Trained":
                    "Yes" if trained else "No",
                "Preferred Day":
                    ", ".join(preferred),
                "Unavailable Days":
                    ", ".join(unavailable_days),
                "Fixed Shift Enabled":
                    "Yes" if fixed_enabled else "No",
                "Fixed Weekly Shift":
                    ";".join(fixed_rows) if fixed_enabled else ""
            }

            if is_edit:
                for k, v in new_row.items():
                    df.at[index, k] = v
            else:
                df = pd.concat(
                    [df, pd.DataFrame([new_row])],
                    ignore_index=True
                )

            save_data(df)

            st.toast("Saved successfully")
            st.rerun()


# ======================================================
# PAGE
# ======================================================

st.markdown(
    "<div class='page-title'>👥 Team Management</div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div class='page-sub'>Manage your staff roster, roles and weekly patterns</div>",
    unsafe_allow_html=True
)

df = load_data()

# -----------------------------------
# CONTROLS
# -----------------------------------

c1, c2, c3 = st.columns([1.3, 2.2, 1.5])

with c1:
    if st.button(
        "➕ Add Employee",
        type="primary",
        use_container_width=True
    ):
        employee_form()

with c2:
    search = st.text_input(
        "Search",
        placeholder="Name or ID"
    )

with c3:
    role_filter = st.selectbox(
        "Role",
        ["All"] + ROLE_ORDER
    )

# -----------------------------------
# FILTERING
# -----------------------------------

df_show = df.copy()

if search:
    s = search.lower()

    df_show = df_show[
        df_show.apply(
            lambda r:
            s in str(r["Name"]).lower()
            or
            s in str(r["ID"]).lower(),
            axis=1
        )
    ]

if role_filter != "All":
    df_show = df_show[
        df_show["Designation"] == role_filter
    ]

# -----------------------------------
# METRICS
# -----------------------------------

m1, m2, m3 = st.columns(3)

m1.metric("Total Staff", len(df))

m2.metric(
    "Opening Trained",
    len(df[
        df["Opening Trained"]
        .astype(str)
        .str.lower()
        .isin(["yes", "true", "1"])
    ])
)

m3.metric(
    "Fixed Shift Staff",
    len(df[
        df["Fixed Shift Enabled"]
        .astype(str)
        .eq("Yes")
    ])
)

st.divider()

# -----------------------------------
# TABLE
# -----------------------------------

if df_show.empty:
    st.info("No employees found.")

else:

    for idx, row in df_show.iterrows():

        role = str(
            row.get(
                "Designation",
                "Associate"
            )
        )

        clr = ROLE_COLORS.get(
            role,
            DEFAULT_ROLE
        )

        with st.container(border=True):

            a, b, c, d, e = st.columns(
                [2.1, 1.4, 1.2, 2.7, 0.6]
            )

            with a:
                st.markdown(
                    f"**{row['Name']}**  \n"
                    f"ID: {row['ID']}"
                )

            with b:
                st.markdown(
                    f"""
                    <span class='role-badge'
                    style='background:{clr["bg"]};
                    color:{clr["text"]};
                    border:1px solid {clr["border"]}'>
                    {role}
                    </span>
                    """,
                    unsafe_allow_html=True
                )

            with c:
                st.write(
                    f"{row['Minimum Contractual Hours']} - "
                    f"{row['Max Weekly Hours']}h"
                )

            with d:
                if str(
                    row["Fixed Shift Enabled"]
                ) == "Yes":
                    st.caption(
                        row["Fixed Weekly Shift"]
                    )
                else:
                    st.caption("No fixed shifts")

            with e:
                if st.button(
                    "✏️",
                    key=f"edit_{idx}"
                ):
                    employee_form(row, idx)

st.divider()

st.caption(
    f"Showing {len(df_show)} of {len(df)} employees"
)