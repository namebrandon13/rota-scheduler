import streamlit as st
import pandas as pd
import os
from datetime import datetime

# ======================================================
# PATHS
# ======================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMP_FILE = os.path.join(BASE_DIR, "Book(Employees)_01.xlsx")
SHEET_NAME = "Employees"

# ======================================================
# STYLES
# ======================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}

.page-title{font-size:2em;font-weight:900;color:#1E293B;letter-spacing:-0.03em;margin-bottom:2px;}
.page-sub{font-size:0.88em;color:#64748B;margin-bottom:14px;}

.emp-card{
    background:white;
    border:1px solid #E2E8F0;
    border-radius:14px;
    padding:16px 20px;
    margin-bottom:12px;
    box-shadow:0 1px 4px rgba(0,0,0,0.05);
}
.emp-card:hover{
    border-color:#BFDBFE;
    box-shadow:0 4px 12px rgba(37,99,235,0.1);
}
.emp-name{font-size:1.1em;font-weight:700;color:#1E293B;margin-bottom:4px;}
.emp-role{
    display:inline-block;
    font-size:0.75em;
    font-weight:600;
    padding:3px 10px;
    border-radius:20px;
    margin-right:6px;
}
.role-manager{background:#DBEAFE;color:#1D4ED8;}
.role-shift-leader{background:#EDE9FE;color:#6D28D9;}
.role-team-leader{background:#CFFAFE;color:#0E7490;}
.role-associate{background:#F1F5F9;color:#374151;}

.emp-detail{font-size:0.82em;color:#64748B;margin:2px 0;}
.emp-badge{
    display:inline-block;
    font-size:0.7em;
    font-weight:600;
    padding:2px 8px;
    border-radius:12px;
    margin:2px 3px 2px 0;
}
.badge-green{background:#DCFCE7;color:#166534;}
.badge-yellow{background:#FEF3C7;color:#92400E;}
.badge-red{background:#FEE2E2;color:#991B1B;}
.badge-blue{background:#DBEAFE;color:#1E40AF;}
.badge-gray{background:#F1F5F9;color:#475569;}

div[data-testid="stMetric"]{
    background:white;
    border:1px solid #E2E8F0;
    border-radius:12px;
    padding:14px 18px;
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# SESSION STATE
# ======================================================

if 'emp_view' not in st.session_state:
    st.session_state.emp_view = 'list'
if 'edit_emp_id' not in st.session_state:
    st.session_state.edit_emp_id = None

# ======================================================
# HELPERS
# ======================================================

@st.cache_data(ttl=10)
def load_employees():
    if not os.path.exists(EMP_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_excel(EMP_FILE, sheet_name=SHEET_NAME)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Error loading employees: {e}")
        return pd.DataFrame()


def save_employees(df):
    """Save employees back to Excel, preserving other sheets"""
    try:
        # Load all existing sheets
        with pd.ExcelFile(EMP_FILE) as xls:
            all_sheets = {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in xls.sheet_names}
        
        # Update Employees sheet
        all_sheets[SHEET_NAME] = df
        
        # Write all sheets back
        with pd.ExcelWriter(EMP_FILE, engine='openpyxl') as writer:
            for sheet_name, sheet_df in all_sheets.items():
                sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving: {e}")
        return False


def get_role_class(role):
    role = str(role).lower().replace(' ', '-')
    if 'manager' in role:
        return 'role-manager'
    elif 'shift' in role:
        return 'role-shift-leader'
    elif 'team' in role:
        return 'role-team-leader'
    return 'role-associate'


def nav_to(view, emp_id=None):
    st.session_state.emp_view = view
    st.session_state.edit_emp_id = emp_id
    st.rerun()

# ======================================================
# SIDEBAR
# ======================================================

def render_sidebar():
    df = load_employees()
    
    with st.sidebar:
        st.markdown("### 👥 Employees")
        
        if not df.empty:
            m1, m2 = st.columns(2)
            m1.metric("Total Staff", len(df))
            
            if 'Designation' in df.columns:
                managers = len(df[df['Designation'].str.contains('Manager', case=False, na=False)])
                m2.metric("Managers", managers)
            
            st.markdown("---")
            
            # Quick stats
            if 'Opening Trained' in df.columns:
                openers = len(df[df['Opening Trained'] == 'Yes'])
                st.markdown(f"🌅 **Opening Trained:** {openers}")
            
            if 'Fixed Shift Enabled' in df.columns:
                fixed = len(df[df['Fixed Shift Enabled'] == 'Yes'])
                st.markdown(f"📌 **Fixed Shifts:** {fixed}")

render_sidebar()

# ======================================================
# LIST VIEW
# ======================================================

def show_list_view():
    st.markdown("<div class='page-title'>👥 Employees</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Manage staff details, availability, and preferences</div>", unsafe_allow_html=True)
    
    df = load_employees()
    
    if df.empty:
        st.warning("No employee data found.")
        return
    
    # Action buttons
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("➕ Add Employee", type="primary", use_container_width=True):
            nav_to('add')
    with col2:
        if st.button("📊 Table View", use_container_width=True):
            nav_to('table')
    
    st.divider()
    
    # Search and filter
    fc1, fc2, fc3 = st.columns([2, 1, 1])
    
    with fc1:
        search = st.text_input("🔍 Search", placeholder="Search by name...", label_visibility="collapsed")
    
    with fc2:
        roles = ['All'] + df['Designation'].dropna().unique().tolist() if 'Designation' in df.columns else ['All']
        role_filter = st.selectbox("Role", roles, label_visibility="collapsed")
    
    with fc3:
        sort_by = st.selectbox("Sort by", ['Name', 'ID', 'Max Weekly Hours'], label_visibility="collapsed")
    
    # Filter data
    filtered = df.copy()
    
    if search:
        filtered = filtered[filtered['Name'].str.contains(search, case=False, na=False)]
    
    if role_filter != 'All':
        filtered = filtered[filtered['Designation'] == role_filter]
    
    if sort_by == 'Name':
        filtered = filtered.sort_values('Name')
    elif sort_by == 'ID':
        filtered = filtered.sort_values('ID')
    elif sort_by == 'Max Weekly Hours':
        filtered = filtered.sort_values('Max Weekly Hours', ascending=False)
    
    st.caption(f"Showing {len(filtered)} employee(s)")
    
    # Employee cards
    for _, emp in filtered.iterrows():
        with st.container():
            c1, c2 = st.columns([5, 1])
            
            with c1:
                role = str(emp.get('Designation', 'Associate'))
                role_class = get_role_class(role)
                
                # Name and role
                st.markdown(f"""
                <div class='emp-card'>
                    <div class='emp-name'>{emp['Name']}</div>
                    <span class='emp-role {role_class}'>{role}</span>
                """, unsafe_allow_html=True)
                
                # Hours info
                min_hrs = emp.get('Minimum Contractual Hours', 0)
                max_hrs = emp.get('Max Weekly Hours', 40)
                st.markdown(f"<div class='emp-detail'>📊 Hours: {min_hrs} - {max_hrs} per week</div>", unsafe_allow_html=True)
                
                # Badges
                badges_html = ""
                
                if emp.get('Opening Trained') == 'Yes':
                    badges_html += "<span class='emp-badge badge-green'>🌅 Opener</span>"
                
                if emp.get('Fixed Shift Enabled') == 'Yes':
                    badges_html += "<span class='emp-badge badge-blue'>📌 Fixed Shift</span>"
                
                pref_slot = str(emp.get('Preferred slot', ''))
                if pref_slot not in ['nan', '', 'None', 'Any']:
                    badges_html += f"<span class='emp-badge badge-yellow'>⏰ {pref_slot}</span>"
                
                fixed_slot = str(emp.get('Fixed Slot', ''))
                if fixed_slot not in ['nan', '', 'None', 'Any']:
                    badges_html += f"<span class='emp-badge badge-red'>🔒 {fixed_slot}</span>"
                
                unavail = str(emp.get('Unavailable Days', ''))
                if unavail not in ['nan', '', 'None']:
                    days_count = len([d for d in unavail.split(',') if d.strip()])
                    badges_html += f"<span class='emp-badge badge-gray'>🚫 {days_count} day(s) off</span>"
                
                if badges_html:
                    st.markdown(badges_html, unsafe_allow_html=True)
                
                st.markdown("</div>", unsafe_allow_html=True)
            
            with c2:
                st.write("")
                st.write("")
                if st.button("✏️ Edit", key=f"edit_{emp['ID']}", use_container_width=True):
                    nav_to('edit', emp_id=emp['ID'])

# ======================================================
# TABLE VIEW
# ======================================================

def show_table_view():
    st.markdown("<div class='page-title'>📊 Employee Table</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Edit employee data directly in the table</div>", unsafe_allow_html=True)
    
    if st.button("◀ Back to Cards"):
        nav_to('list')
    
    st.divider()
    
    df = load_employees()
    
    if df.empty:
        st.warning("No employee data found.")
        return
    
    # Column config for better editing
    column_config = {
        'ID': st.column_config.NumberColumn('ID', disabled=True),
        'Name': st.column_config.TextColumn('Name', width='medium'),
        'Max Weekly Hours': st.column_config.NumberColumn('Max Hours', min_value=0, max_value=60),
        'Minimum Contractual Hours': st.column_config.NumberColumn('Min Hours', min_value=0, max_value=60),
        'Designation': st.column_config.SelectboxColumn(
            'Role',
            options=['Manager', 'Shift Leader', 'Team Leader', 'Associate'],
            width='medium'
        ),
        'Preferred Day': st.column_config.TextColumn('Preferred Days', width='large'),
        'Preferred slot': st.column_config.SelectboxColumn(
            'Preferred Slot',
            options=['Any', 'Morning', 'Afternoon', 'Evening', 'Morning, Evening'],
            width='medium'
        ),
        'Fixed Slot': st.column_config.SelectboxColumn(
            'Fixed Slot',
            options=['Any', 'Morning', 'Afternoon', 'Evening', 'Morning, Evening'],
            width='medium'
        ),
        'Fixed Role': st.column_config.SelectboxColumn(
            'Fixed Role',
            options=['', 'Opening', 'Closing'],
            width='small'
        ),
        'Unavailable Days': st.column_config.TextColumn('Unavailable', width='large'),
        'Opening Trained': st.column_config.SelectboxColumn(
            'Opener?',
            options=['Yes', 'No'],
            width='small'
        ),
        'Fixed Shift Enabled': st.column_config.SelectboxColumn(
            'Fixed Enabled?',
            options=['Yes', 'No'],
            width='small'
        ),
        'Fixed Weekly Shift': st.column_config.TextColumn('Fixed Weekly Shift', width='large'),
    }
    
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        num_rows="dynamic"
    )
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Changes", type="primary", use_container_width=True):
            if save_employees(edited_df):
                st.success("✅ Saved successfully!")
                st.rerun()
    
    with c2:
        if st.button("🔄 Discard Changes", use_container_width=True):
            st.rerun()

# ======================================================
# ADD/EDIT VIEW
# ======================================================

def show_edit_view():
    df = load_employees()
    emp_id = st.session_state.edit_emp_id
    is_new = emp_id is None
    
    if is_new:
        st.markdown("<div class='page-title'>➕ Add Employee</div>", unsafe_allow_html=True)
        emp = {}
        new_id = int(df['ID'].max()) + 1 if not df.empty else 1
    else:
        st.markdown("<div class='page-title'>✏️ Edit Employee</div>", unsafe_allow_html=True)
        emp_row = df[df['ID'] == emp_id]
        if emp_row.empty:
            st.error("Employee not found")
            return
        emp = emp_row.iloc[0].to_dict()
        new_id = emp_id
    
    if st.button("◀ Back"):
        nav_to('list')
    
    st.divider()
    
    # Form
    with st.form("emp_form"):
        st.subheader("📋 Basic Information")
        
        fc1, fc2 = st.columns(2)
        
        with fc1:
            name = st.text_input("Name *", value=emp.get('Name', ''))
            
            designation = st.selectbox(
                "Designation *",
                options=['Associate', 'Team Leader', 'Shift Leader', 'Manager'],
                index=['Associate', 'Team Leader', 'Shift Leader', 'Manager'].index(emp.get('Designation', 'Associate')) if emp.get('Designation') in ['Associate', 'Team Leader', 'Shift Leader', 'Manager'] else 0
            )
        
        with fc2:
            min_hours = st.number_input(
                "Minimum Contractual Hours",
                min_value=0,
                max_value=60,
                value=int(emp.get('Minimum Contractual Hours', 0)) if pd.notna(emp.get('Minimum Contractual Hours')) else 0
            )
            
            max_hours = st.number_input(
                "Max Weekly Hours",
                min_value=0,
                max_value=60,
                value=int(emp.get('Max Weekly Hours', 40)) if pd.notna(emp.get('Max Weekly Hours')) else 40
            )
        
        st.divider()
        st.subheader("📅 Availability")
        
        # Preferred Days
        st.markdown("**Preferred Days** (days they prefer to work)")
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        current_pref = str(emp.get('Preferred Day', ''))
        pref_days_list = [d.strip() for d in current_pref.split(',') if d.strip() and d.strip() != 'nan']
        
        pref_cols = st.columns(7)
        selected_pref_days = []
        for i, day in enumerate(days):
            with pref_cols[i]:
                if st.checkbox(day[:3], value=(day in pref_days_list), key=f"pref_{day}"):
                    selected_pref_days.append(day)
        
        # Unavailable Days
        st.markdown("**Unavailable Days** (days they CANNOT work)")
        
        current_unavail = str(emp.get('Unavailable Days', ''))
        unavail_days_list = [d.strip() for d in current_unavail.split(',') if d.strip() and d.strip() != 'nan']
        
        unavail_cols = st.columns(7)
        selected_unavail_days = []
        for i, day in enumerate(days):
            with unavail_cols[i]:
                if st.checkbox(day[:3], value=(day in unavail_days_list), key=f"unavail_{day}"):
                    selected_unavail_days.append(day)
        
        st.divider()
        st.subheader("⏰ Shift Preferences")
        
        sc1, sc2 = st.columns(2)
        
        with sc1:
            slot_options = ['Any', 'Morning', 'Afternoon', 'Evening', 'Morning, Evening']
            
            current_pref_slot = str(emp.get('Preferred slot', 'Any'))
            if current_pref_slot in ['nan', 'None', '']:
                current_pref_slot = 'Any'
            
            preferred_slot = st.selectbox(
                "Preferred Slot (soft - will TRY to schedule)",
                options=slot_options,
                index=slot_options.index(current_pref_slot) if current_pref_slot in slot_options else 0,
                help="The scheduler will try to give shifts in this time slot when possible"
            )
        
        with sc2:
            current_fixed_slot = str(emp.get('Fixed Slot', 'Any'))
            if current_fixed_slot in ['nan', 'None', '']:
                current_fixed_slot = 'Any'
            
            fixed_slot = st.selectbox(
                "Fixed Slot (hard - MUST work this slot)",
                options=slot_options,
                index=slot_options.index(current_fixed_slot) if current_fixed_slot in slot_options else 0,
                help="If set, employee can ONLY work in this time slot"
            )
        
        st.divider()
        st.subheader("🔧 Special Settings")
        
        sp1, sp2, sp3 = st.columns(3)
        
        with sp1:
            opening_trained = st.checkbox(
                "Opening Trained",
                value=(emp.get('Opening Trained') == 'Yes'),
                help="Can this employee open the store?"
            )
        
        with sp2:
            fixed_shift_enabled = st.checkbox(
                "Fixed Shift Enabled",
                value=(emp.get('Fixed Shift Enabled') == 'Yes'),
                help="Enable fixed weekly shift pattern?"
            )
        
        with sp3:
            fixed_role_options = ['', 'Opening', 'Closing']
            current_fixed_role = str(emp.get('Fixed Role', ''))
            if current_fixed_role in ['nan', 'None']:
                current_fixed_role = ''
            
            fixed_role = st.selectbox(
                "Fixed Role",
                options=fixed_role_options,
                index=fixed_role_options.index(current_fixed_role) if current_fixed_role in fixed_role_options else 0
            )
        
        # Fixed Weekly Shift
        if fixed_shift_enabled:
            st.markdown("**Fixed Weekly Shift Pattern**")
            st.caption("Format: Monday|09:00|17:00;Wednesday|12:00|20:00")
            
            fixed_weekly = st.text_input(
                "Fixed Weekly Shift",
                value=emp.get('Fixed Weekly Shift', '') if pd.notna(emp.get('Fixed Weekly Shift')) else '',
                label_visibility="collapsed"
            )
        else:
            fixed_weekly = ''
        
        st.divider()
        
        # Submit buttons
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            submitted = st.form_submit_button("💾 Save Employee", type="primary", use_container_width=True)
        
        with col3:
            if not is_new:
                delete = st.form_submit_button("🗑️ Delete", use_container_width=True)
            else:
                delete = False
    
    # Handle form submission
    if submitted:
        if not name:
            st.error("Name is required!")
            return
        
        new_emp = {
            'ID': new_id,
            'Name': name,
            'Max Weekly Hours': max_hours,
            'Minimum Contractual Hours': min_hours,
            'Designation': designation,
            'Preferred Day': ', '.join(selected_pref_days) if selected_pref_days else '',
            'Preferred slot': preferred_slot if preferred_slot != 'Any' else '',
            'Fixed Slot': fixed_slot if fixed_slot != 'Any' else '',
            'Fixed Role': fixed_role,
            'Unavailable Days': ', '.join(selected_unavail_days) if selected_unavail_days else '',
            'Opening Trained': 'Yes' if opening_trained else 'No',
            'Fixed Shift Enabled': 'Yes' if fixed_shift_enabled else '',
            'Fixed Weekly Shift': fixed_weekly if fixed_shift_enabled else ''
        }
        
        if is_new:
            df = pd.concat([df, pd.DataFrame([new_emp])], ignore_index=True)
        else:
            for col, val in new_emp.items():
                df.loc[df['ID'] == emp_id, col] = val
        
        if save_employees(df):
            st.success("✅ Employee saved!")
            nav_to('list')
    
    if delete:
        df = df[df['ID'] != emp_id]
        if save_employees(df):
            st.success("✅ Employee deleted!")
            nav_to('list')

# ======================================================
# ROUTER
# ======================================================

view = st.session_state.emp_view

if view == 'list':
    show_list_view()
elif view == 'table':
    show_table_view()
elif view in ('edit', 'add'):
    show_edit_view()
