import streamlit as st
import pandas as pd
import os
import calendar
from datetime import datetime, date, timedelta

# Import your new database handler
from gsheets_db import get_user_data, write_user_data

# ======================================================
# AUTH & SETUP
# ======================================================

# Verify user is logged in and has a sheet ID AND username assigned
if 'sheet_id' not in st.session_state or 'username' not in st.session_state:
    st.error("Please log in to access Holiday Management.")
    st.stop()

sheet_id = st.session_state['sheet_id']
username = st.session_state['username']

SHEET_HOLIDAYS = "Holiday" # Changed from "Holidays" to match your DB creation script
SHEET_EMPLOYEES = "Employees"

# ======================================================
# CONFIG
# ======================================================

STATUS_COLORS = {
    "Approved": {"bg": "#DCFCE7", "text": "#16A34A", "dot": "#16A34A"},
    "Pending": {"bg": "#FEF3C7", "text": "#D97706", "dot": "#D97706"},
    "Rejected": {"bg": "#FEE2E2", "text": "#DC2626", "dot": "#DC2626"},
}

DSC = {"bg": "#F1F5F9", "text": "#64748B", "dot": "#94A3B8"}

# ======================================================
# STYLE
# ======================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.page-title{font-size:2em;font-weight:900;color:#1E293B;}
.page-sub{color:#64748B;margin-bottom:12px;}
.cal-cell{
border-radius:12px;
padding:8px;
min-height:105px;
text-align:center;
border:1px solid #E2E8F0;
background:white;
}
.cell-approved{background:#F0FDF4;}
.cell-pending{background:#FFFBEB;}
.cell-empty{background:#F8FAFC;}
.day-num{font-size:1.6em;font-weight:900;}
</style>
""", unsafe_allow_html=True)

# ======================================================
# SESSION
# ======================================================

defaults = {
    "hol_yr": datetime.today().year,
    "hol_mo": datetime.today().month,
    "hol_sel": None
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ======================================================
# HELPERS
# ======================================================

def load_holidays(user):
    cols = [
        "Employee ID",
        "Name",
        "Date",
        "Status",
        "Reason"
    ]

    try:
        df = get_user_data(sheet_id, SHEET_HOLIDAYS, user)
        
        if df.empty:
            return pd.DataFrame(columns=cols)

        df.columns = df.columns.str.strip()

        for c in cols:
            if c not in df.columns:
                df[c] = ""

        df["Employee ID"] = (
            df["Employee ID"]
            .astype(str)
            .str.strip()
        )

        df["Date"] = pd.to_datetime(
            df["Date"]
        ).dt.normalize()

        return df

    except Exception as e:
        st.error(f"Error loading holidays: {e}")
        return pd.DataFrame(columns=cols)


def save_holidays(df, user):
    try:
        # Create a copy so we don't convert dates to strings in the live app UI
        df_upload = df.copy()
        df_upload["Date"] = pd.to_datetime(df_upload["Date"]).dt.strftime('%Y-%m-%d')
        
        write_user_data(sheet_id, SHEET_HOLIDAYS, user, df_upload)
    except Exception as e:
        st.error(f"Error saving holidays to Google Sheets: {e}")


def get_employee_lookup(user):
    try:
        df = get_user_data(sheet_id, SHEET_EMPLOYEES, user)
        
        if df.empty:
            return pd.DataFrame(columns=["ID", "Name"])

        df.columns = df.columns.str.strip()
        df["ID"] = df["ID"].astype(str).str.strip()
        df["Name"] = df["Name"].astype(str).str.strip()

        return df[["ID", "Name"]]

    except Exception as e:
        st.error(f"Error loading employees: {e}")
        return pd.DataFrame(columns=["ID", "Name"])


def group_into_ranges(df):
    if df.empty:
        return []

    out = []
    df = df.sort_values(["Name", "Date"])

    for name, grp in df.groupby("Name"):
        dates = sorted(
            grp["Date"].dt.date.tolist()
        )

        status = str(grp["Status"].iloc[0])
        reason = str(grp["Reason"].iloc[0])

        start = dates[0]
        prev = dates[0]

        for d in dates[1:]:
            if (d - prev).days == 1:
                prev = d
            else:
                out.append({
                    "Name": name,
                    "Start": start,
                    "End": prev,
                    "Days": (prev - start).days + 1,
                    "Status": status,
                    "Reason": reason
                })
                start = d
                prev = d

        out.append({
            "Name": name,
            "Start": start,
            "End": prev,
            "Days": (prev - start).days + 1,
            "Status": status,
            "Reason": reason
        })

    return out

# ======================================================
# DIALOG
# ======================================================

@st.dialog("✈️ Request Holiday", width="large")
def add_holiday_dialog():
    emp_df = get_employee_lookup(username)

    if emp_df.empty:
        st.warning("No employees found. Please add employees first.")
        return

    with st.form("holiday_form"):
        emp = st.selectbox(
            "Employee",
            emp_df["Name"].tolist()
        )

        c1, c2 = st.columns(2)

        sd = c1.date_input(
            "Start Date",
            value=date.today()
        )

        ed = c2.date_input(
            "End Date",
            value=date.today()
        )

        reason = st.text_area("Reason")

        submitted = st.form_submit_button(
            "Submit Request",
            type="primary",
            use_container_width=True
        )

        if submitted:
            if ed < sd:
                st.error("End before start.")
                st.stop()

            emp_id = str(
                emp_df.loc[
                    emp_df["Name"] == emp,
                    "ID"
                ].iloc[0]
            )

            rows = []
            for i in range((ed - sd).days + 1):
                rows.append({
                    "Employee ID": emp_id,
                    "Name": emp,
                    "Date": pd.Timestamp(
                        sd + timedelta(days=i)
                    ),
                    "Status": "Pending",
                    "Reason": reason
                })

            df = load_holidays(username)
            if df.empty:
                df = pd.DataFrame(rows)
            else:
                df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)

            save_holidays(df, username)

            st.success("Submitted.")
            st.rerun()

# ======================================================
# PAGE
# ======================================================

df_h = load_holidays(username)

st.markdown(
    "<div class='page-title'>✈️ Holiday Management</div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div class='page-sub'>Manage leave requests and approvals</div>",
    unsafe_allow_html=True
)

# ======================================================
# METRICS
# ======================================================

if not df_h.empty:
    pn = len(df_h[df_h["Status"].astype(str).str.lower().eq("pending")])
    an = len(df_h[df_h["Status"].astype(str).str.lower().eq("approved")])
    rn = len(df_h[df_h["Status"].astype(str).str.lower().eq("rejected")])
else:
    pn = an = rn = 0

m1, m2, m3, m4 = st.columns(4)

m1.metric("Total", len(df_h))
m2.metric("Pending", pn)
m3.metric("Approved", an)
m4.metric("Rejected", rn)

st.write("")

if st.button("➕ Add Request", type="primary"):
    add_holiday_dialog()

st.divider()

# ======================================================
# CALENDAR
# ======================================================

yr = st.session_state.hol_yr
mo = st.session_state.hol_mo

c1, c2, c3 = st.columns([1, 6, 1])

with c1:
    if st.button("◀"):
        st.session_state.hol_mo = 12 if mo == 1 else mo - 1
        if mo == 1:
            st.session_state.hol_yr = yr - 1
        st.rerun()

with c2:
    st.markdown(
        f"## {datetime(yr, mo, 1).strftime('%B %Y')}"
    )

with c3:
    if st.button("▶"):
        st.session_state.hol_mo = 1 if mo == 12 else mo + 1
        if mo == 12:
            st.session_state.hol_yr = yr + 1
        st.rerun()

hol_map = {}

if not df_h.empty:
    for _, r in df_h.iterrows():
        d = r["Date"].date()
        hol_map.setdefault(d, []).append(
            (
                r["Name"],
                r["Status"]
            )
        )

for week in calendar.monthcalendar(yr, mo):
    cols = st.columns(7)

    for i, dn in enumerate(week):
        with cols[i]:
            if dn == 0:
                st.write("")
                continue

            curr = date(yr, mo, dn)
            vals = hol_map.get(curr, [])

            approved = any(
                s.lower() == "approved"
                for _, s in vals
            )

            pending = any(
                s.lower() == "pending"
                for _, s in vals
            )

            css = "cell-empty"

            if approved:
                css = "cell-approved"
            elif pending:
                css = "cell-pending"

            names = "<br>".join(
                [x[0].split()[0] for x in vals[:2]]
            )

            st.markdown(
                f"""
                <div class='cal-cell {css}'>
                <div class='day-num'>{dn}</div>
                {names}
                </div>
                """,
                unsafe_allow_html=True
            )

            if st.button(
                "👁",
                key=f"d_{yr}_{mo}_{dn}"
            ):
                st.session_state.hol_sel = curr
                st.rerun()

# ======================================================
# DAY PANEL
# ======================================================

if st.session_state.hol_sel:
    sel = st.session_state.hol_sel
    st.divider()
    st.markdown(
        f"### {sel.strftime('%A %d %B %Y')}"
    )

    vals = hol_map.get(sel, [])

    if not vals:
        st.info("No holidays.")
    else:
        for n, s in vals:
            st.write(f"• {n} ({s})")

# ======================================================
# REQUEST TABLES
# ======================================================

st.divider()

tab1, tab2, tab3 = st.tabs([
    f"Pending ({pn})",
    "Approved",
    "All"
])

with tab1:
    if not df_h.empty:
        pending_df = df_h[df_h["Status"].astype(str).str.lower().eq("pending")]
    else:
        pending_df = pd.DataFrame()

    if pending_df.empty:
        st.success("No pending requests.")
    else:
        ranges = group_into_ranges(pending_df)

        for i, r in enumerate(ranges):
            st.markdown(
                f"**{r['Name']}** | "
                f"{r['Start']} → {r['End']} "
                f"({r['Days']} days)"
            )

            c1, c2 = st.columns(2)

            if c1.button(
                "Approve",
                key=f"a{i}"
            ):
                mask = (
                    (df_h["Name"] == r["Name"]) &
                    (df_h["Date"] >= pd.Timestamp(r["Start"])) &
                    (df_h["Date"] <= pd.Timestamp(r["End"])) &
                    (df_h["Status"] == "Pending")
                )
                df_h.loc[mask, "Status"] = "Approved"
                save_holidays(df_h, username)
                st.rerun()

            if c2.button(
                "Reject",
                key=f"r{i}"
            ):
                mask = (
                    (df_h["Name"] == r["Name"]) &
                    (df_h["Date"] >= pd.Timestamp(r["Start"])) &
                    (df_h["Date"] <= pd.Timestamp(r["End"])) &
                    (df_h["Status"] == "Pending")
                )
                df_h.loc[mask, "Status"] = "Rejected"
                save_holidays(df_h, username)
                st.rerun()

with tab2:
    if not df_h.empty:
        appr = df_h[df_h["Status"].astype(str).str.lower().eq("approved")]
        st.dataframe(
            appr,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No approved holidays.")

with tab3:
    if not df_h.empty:
        st.dataframe(
            df_h.sort_values(
                "Date",
                ascending=False
            ),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No data.")
