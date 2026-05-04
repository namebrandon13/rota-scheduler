import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import os
import math
import subprocess
import sys

from gsheets_db import get_user_data, write_user_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVENT_SCRIPT = os.path.join(BASE_DIR, "eventapicall.py")

# ==============================================================================
#                            BUSINESS CONTROL PANEL
# ==============================================================================

ENABLE_HYBRID_MODE = True
REVENUE_PER_STAFF = 800   

DEFAULT_MIN_SHIFT = 6
MAX_SHIFT_LENGTH = 9
MIN_REST_HOURS = 12
MAX_CONSECUTIVE_DAYS = 6

ENABLE_STRICT_SECOND_START = True
DEFAULT_SECOND_START_EARLIEST = 9   
DEFAULT_SECOND_START_LATEST = 10    

EVENT_PREP_HOURS = 4

EVENT_THRESHOLDS = {
    8: (7, 8, 4),
    5: (8, 9, 3),
    1: (9, 10, 2),
    0: (9, 10, 2),
}

EVENING_START_HOUR = 17 
MORNING_END_HOUR = 12    

WEIGHT_UTILIZATION = 10
WEIGHT_PREFERRED_DAY = 100      
WEIGHT_PREFERRED_SLOT = 50      
WEIGHT_FAIRNESS = 2  # Quadratic load balancer — penalizes uneven hour distribution

# --- GRADUATED SOLVER CONFIGS ---
# relax_closer_rest: when True, closers are NOT forced to start >=12 after a close.
# This is needed when closer contracts are too high to satisfy with the rest rule active.
SOLVER_CONFIGS = [
    {'label': 'Standard',                                'min_shift': 6, 'reduction_pct': 0.00, 'trim_fixed': False, 'relax_closer_rest': False},
    {'label': '5% uniform contract reduction',           'min_shift': 6, 'reduction_pct': 0.05, 'trim_fixed': False, 'relax_closer_rest': False},
    {'label': '10% uniform contract reduction',          'min_shift': 6, 'reduction_pct': 0.10, 'trim_fixed': False, 'relax_closer_rest': False},
    {'label': '5h shifts + 10% + relaxed closer rest',  'min_shift': 5, 'reduction_pct': 0.10, 'trim_fixed': False, 'relax_closer_rest': True},
    {'label': 'Full relaxation + relaxed closer rest',   'min_shift': 5, 'reduction_pct': 0.15, 'trim_fixed': True,  'relax_closer_rest': True},
]

# ==============================================================================
#                            HELPER FUNCTIONS
# ==============================================================================

def get_event_params(impact_score):
    if impact_score >= 8: return EVENT_THRESHOLDS[8]
    elif impact_score >= 5: return EVENT_THRESHOLDS[5]
    elif impact_score >= 1: return EVENT_THRESHOLDS[1]
    return EVENT_THRESHOLDS[0]

def safe_int(val, default=0):
    """Convert any value (including NaN, None, float, str) to int safely."""
    try:
        if val is None: return default
        f = float(val)
        if math.isnan(f) or math.isinf(f): return default
        return int(f)
    except (ValueError, TypeError):
        return default

def parse_fixed_shifts(raw):
    result = {}
    raw = str(raw).strip()
    if raw in ["", "nan", "None"]: return result
    for item in raw.split(";"):
        parts = item.split("|")
        if len(parts) != 3: continue
        day_name = parts[0].strip()
        try:
            start_h = int(parts[1].split(":")[0])
            end_h = int(parts[2].split(":")[0])
            if end_h == 0: end_h = 24
            result[day_name] = (start_h, end_h)
        except: pass
    return result

def run_event_tracker():
    try:
        if os.path.exists(EVENT_SCRIPT):
            subprocess.run([sys.executable, EVENT_SCRIPT], capture_output=True, text=True, cwd=BASE_DIR)
    except: pass

def load_events_for_dates(dates_list, df_ev): 
    event_map = {}
    try:
        if df_ev.empty: return event_map
        df_ev.columns = df_ev.columns.str.strip()
        for _, row in df_ev.iterrows():
            try:
                d_str = pd.to_datetime(row['Date']).strftime('%Y-%m-%d')
                if d_str not in dates_list: continue
                start_time = str(row.get('Start Time', '12:00'))
                try: start_hour = int(start_time.split(':')[0]) if ':' in start_time else 12
                except: start_hour = 12
                impact = safe_int(row.get('Impact Score', 0), 0)
                if d_str not in event_map or impact > event_map[d_str]['impact']:
                    event_map[d_str] = {
                        'impact': impact, 'start_hour': start_hour,
                        'event_name': str(row.get('Event Name', 'Event')),
                        'venue': str(row.get('Venue', ''))
                    }
            except: continue
    except: pass
    return event_map


# ==============================================================================
#                           PRE-FLIGHT DIAGNOSTICS
# ==============================================================================

def _run_diagnostics(employees, emp_indices, week_data, dates_in_order, 
                     approved_holidays, event_data, weekly_budget):
    issues = []
    
    # 1. Budget vs total contractual minimums
    total_min = 0
    for idx in emp_indices:
        total_min += safe_int(employees[idx].get('Minimum Contractual Hours', 0), 0)
    
    if weekly_budget < total_min:
        issues.append(
            f"💰 **Budget too low:** Budget is {weekly_budget}h but total contractual "
            f"minimums are {total_min}h. Increase budget by at least {total_min - weekly_budget}h."
        )
    
    # 2. Per-day: available staff vs minimum required
    for _, row in week_data.iterrows():
        date_str = row['Date'].strftime('%Y-%m-%d')
        day_name = row['Date'].day_name()
        min_staff = safe_int(row['Minimum Staff'], 0)
        
        available = 0
        for idx in emp_indices:
            emp = employees[idx]
            emp_id = str(emp['ID']).strip()
            emp_name = str(emp['Name']).strip()
            unavail = str(emp.get('Unavailable Days', ''))
            if unavail != 'nan' and day_name in unavail: continue
            if (emp_id, date_str) in approved_holidays or (emp_name, date_str) in approved_holidays: continue
            available += 1
        
        if available < min_staff:
            issues.append(
                f"📅 **{day_name}:** Only {available} staff available but template requires "
                f"{min_staff} minimum. Check holidays and unavailable days."
            )
    
    # 3. Opening-trained availability
    for _, row in week_data.iterrows():
        date_str = row['Date'].strftime('%Y-%m-%d')
        day_name = row['Date'].day_name()
        
        openers = 0
        for idx in emp_indices:
            emp = employees[idx]
            if emp.get('Opening Trained', 'No') != 'Yes': continue
            emp_id = str(emp['ID']).strip()
            emp_name = str(emp['Name']).strip()
            unavail = str(emp.get('Unavailable Days', ''))
            if unavail != 'nan' and day_name in unavail: continue
            if (emp_id, date_str) in approved_holidays or (emp_name, date_str) in approved_holidays: continue
            openers += 1
        
        if openers == 0:
            issues.append(
                f"🌅 **{day_name}:** No opening-trained staff available. "
                f"Someone must be trained to open or a holiday must be moved."
            )
    
    # 4. Individual employee feasibility
    for idx in emp_indices:
        emp = employees[idx]
        emp_name = str(emp['Name']).strip()
        emp_id = str(emp['ID']).strip()
        min_hrs = safe_int(emp.get('Minimum Contractual Hours', 0), 0)
        if min_hrs == 0: continue
        
        unavail = str(emp.get('Unavailable Days', ''))
        available_days = 0
        for d in dates_in_order:
            day_name = pd.to_datetime(d).day_name()
            if unavail != 'nan' and day_name in unavail: continue
            if (emp_id, d) in approved_holidays or (emp_name, d) in approved_holidays: continue
            available_days += 1
        
        max_possible = available_days * MAX_SHIFT_LENGTH
        if max_possible < min_hrs:
            issues.append(
                f"👤 **{emp_name}:** Needs {min_hrs}h but only has {available_days} "
                f"available days (max {max_possible}h possible). Reduce their minimum or adjust availability."
            )
    
    # 5. Fixed shift budget consumption
    fixed_total = 0
    for idx in emp_indices:
        emp = employees[idx]
        if str(emp.get('Fixed Shift Enabled', '')).strip() != 'Yes': continue
        fixed_map = parse_fixed_shifts(emp.get('Fixed Weekly Shift', ''))
        for day_name, (fs, fe) in fixed_map.items():
            for d in dates_in_order:
                if pd.to_datetime(d).day_name() == day_name:
                    emp_id = str(emp['ID']).strip()
                    emp_name = str(emp['Name']).strip()
                    if (emp_id, d) not in approved_holidays and (emp_name, d) not in approved_holidays:
                        fixed_total += (fe - fs)
    
    if fixed_total > 0 and weekly_budget > 0:
        pct = fixed_total / weekly_budget * 100
        if pct > 50:
            issues.append(
                f"📌 **Fixed shifts consume {fixed_total}h ({pct:.0f}% of budget).** "
                f"This leaves very little flexibility. Consider reducing fixed shift hours."
            )
    
    # 6. Closer feasibility: can they actually hit their contract minimum?
    for _, row in week_data.iterrows():
        store_end_h = pd.to_datetime(str(row['End'])).hour
        if store_end_h == 0: store_end_h = 24
        break  # just need the store close time

    for idx in emp_indices:
        emp = employees[idx]
        emp_name = str(emp['Name']).strip()
        emp_id = str(emp['ID']).strip()
        if str(emp.get('Fixed Role', '')).strip() != 'Closing': continue

        min_hrs = safe_int(emp.get('Minimum Contractual Hours', 0), 0)
        if min_hrs == 0: continue

        unavail = str(emp.get('Unavailable Days', ''))
        available_days = 0
        for d in dates_in_order:
            day_name = pd.to_datetime(d).day_name()
            if unavail != 'nan' and day_name in unavail: continue
            if (emp_id, d) in approved_holidays or (emp_name, d) in approved_holidays: continue
            available_days += 1

        # Closers can only work noon (12:00) → store close on days AFTER a worked day,
        # but on their FIRST day of a run they have no rest constraint.
        # Conservative estimate: assume worst case — every day restricted to noon start.
        closer_max_shift = min(MAX_SHIFT_LENGTH, store_end_h - MIN_REST_HOURS)  # e.g. 24-12=12, capped at 9
        max_possible_closer = available_days * closer_max_shift

        if max_possible_closer < min_hrs:
            issues.append(
                f"🌙 **{emp_name} (Closer) contract impossible:** Needs {min_hrs}h but with "
                f"noon-start rest rule can work max {closer_max_shift}h/day × {available_days} days "
                f"= {max_possible_closer}h. Reduce their minimum contractual hours to ≤{max_possible_closer}h."
            )
        elif available_days * closer_max_shift - min_hrs < 4:
            issues.append(
                f"🌙 **{emp_name} (Closer) very tight:** Needs {min_hrs}h, max possible with rest rule "
                f"is {max_possible_closer}h — almost no solver headroom. Consider reducing minimum by a few hours."
            )

    # 7. Fair-share cap conflict: check if budget is too low relative to contracts
    # even after the 15% reduction in the final config
    total_min = sum(safe_int(employees[idx].get('Minimum Contractual Hours', 0), 0) for idx in emp_indices)
    reduced_min = math.floor(total_min * 0.85)
    if weekly_budget < reduced_min and weekly_budget < 9999:
        issues.append(
            f"💸 **Budget vs reduced contracts:** Even after the maximum 15% contract reduction, "
            f"total minimum hours = {reduced_min}h but budget is only {weekly_budget}h. "
            f"Increase the budget to at least {reduced_min}h."
        )

    # Fallback
    if not issues:
        issues.append(
            "🔍 **No single obvious cause found.** The infeasibility is likely caused by "
            "a combination of tight constraints (budget + contracts + rest rules + availability). "
            "Try: (1) increasing the budget by 10-15%, (2) reducing closer minimum contractual hours, "
            "or (3) giving closers one or two unavailable days to reduce their required shift count."
        )
    
    return issues


# ==============================================================================
#                              MAIN SOLVER
# ==============================================================================

def solve_rota_final_v14(sheet_id=None, target_weeks=None, username=None):
    if not sheet_id:
        raise ValueError("System Error: No Google Sheet ID was provided.")
    if not username:
        raise ValueError("System Error: No Username was provided.")

    run_event_tracker()

    # --- DATA FETCH ---
    df_emp = get_user_data(sheet_id, "Employees", username)
    df_shifts = get_user_data(sheet_id, "Shift Template", username) 
    df_hol = get_user_data(sheet_id, "Holiday", username) 
    df_events = get_user_data(sheet_id, "Events", username)
    
    if df_emp.empty: raise ValueError("No data found in the 'Employees' tab.")
    if df_shifts.empty: raise ValueError("No data found in the 'Shift Template' tab.")

    df_shifts.columns = df_shifts.columns.str.strip()
    df_emp.columns = df_emp.columns.str.strip()
    
    df_shifts['Date'] = pd.to_datetime(df_shifts['Date'])
    df_shifts = df_shifts.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")

    if 'Total Sales' not in df_shifts.columns:
        df_shifts['Total Sales'] = 0

    df_shifts['Week_Num'] = df_shifts['Date'].dt.isocalendar().week
    df_shifts['Week_Start_Str'] = df_shifts['Date'].apply(
        lambda x: (x.date() - timedelta(days=x.weekday())).strftime('%Y-%m-%d')
    )
    
    if target_weeks:
        t_weeks_str = [x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x) for x in target_weeks]
        df_shifts = df_shifts[df_shifts['Week_Start_Str'].isin(t_weeks_str)].copy()

    if df_shifts.empty:
        raise ValueError("No shift template data found for the selected week.")

    approved_holidays = set() 
    if not df_hol.empty:
        try:
            df_hol.columns = df_hol.columns.str.strip()
            df_hol['Date'] = pd.to_datetime(df_hol['Date']).dt.normalize()
            if 'Employee ID' in df_hol.columns:
                df_hol['Employee ID'] = df_hol['Employee ID'].astype(str).str.strip()
            elif 'Name' in df_hol.columns:
                df_hol['Employee ID'] = df_hol['Name'].astype(str).str.strip()
            if 'Status' in df_hol.columns:
                approved_df = df_hol[df_hol['Status'].astype(str).str.lower() == 'approved']
                for _, row in approved_df.iterrows():
                    h_date = row['Date'].strftime('%Y-%m-%d')
                    h_id = str(row.get('Employee ID', row.get('Name', '')))
                    approved_holidays.add((h_id, h_date))
        except: pass

    df_emp['ID'] = df_emp['ID'].astype(str)
    employees = df_emp.to_dict('index')
    
    unique_weeks = df_shifts['Week_Num'].unique()
    weekly_dataframes = {}

    for week in unique_weeks:
        week_data = df_shifts[df_shifts['Week_Num'] == week].copy()
        week_data = week_data.sort_values('Date')
        dates_in_order = week_data['Date'].dt.strftime('%Y-%m-%d').unique()
        
        event_data = load_events_for_dates(list(dates_in_order), df_events)
        
        weekly_budget_hours = 9999
        if 'Budget' in week_data.columns:
            val = week_data['Budget'].max()
            if not pd.isna(val) and val > 0: weekly_budget_hours = int(val)

        emp_indices = df_emp.index.tolist()

        # ==========================================================
        #   INNER FUNCTION: BUILD & SOLVE WITH GIVEN CONFIG
        # ==========================================================
        
        def attempt_solve(config):
            min_shift_len = config['min_shift']
            reduction_pct = config['reduction_pct']
            trim_fixed = config['trim_fixed']
            relax_closer_rest = config.get('relax_closer_rest', False)
            
            model = cp_model.CpModel()
            work, start, is_working_day = {}, {}, {}
            daily_start_hour, daily_end_hour = {}, {}
            all_worked_hours_vars = []
            objective_terms = []

            # --- Variables ---
            for idx in emp_indices:
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0: end_h = 24
                    is_working_day[(idx, date_str)] = model.NewBoolVar(f'day_{idx}_{date_str}')
                    daily_start_hour[(idx, date_str)] = model.NewIntVar(0, 24, f'start_h_{idx}_{date_str}')
                    daily_end_hour[(idx, date_str)] = model.NewIntVar(0, 24, f'end_h_{idx}_{date_str}')
                    for h in range(start_h, end_h):
                        work[(idx, date_str, h)] = model.NewBoolVar(f'w_{idx}_{date_str}_{h}')
                        start[(idx, date_str, h)] = model.NewBoolVar(f's_{idx}_{date_str}_{h}')
                        all_worked_hours_vars.append(work[(idx, date_str, h)])

            # --- Budget ceiling ---
            model.Add(sum(all_worked_hours_vars) <= weekly_budget_hours)
            objective_terms.append(WEIGHT_UTILIZATION * sum(all_worked_hours_vars))

            # --- Fixed weekly shifts ---
            for idx in emp_indices:
                emp = employees[idx]
                emp_id = str(emp['ID']).strip()
                if str(emp.get('Fixed Shift Enabled', 'No')).strip() != "Yes": continue
                fixed_map = parse_fixed_shifts(emp.get('Fixed Weekly Shift', ''))
                if not fixed_map: continue
                for _, row in week_data.iterrows():
                    date_obj = row['Date']
                    date_str = date_obj.strftime('%Y-%m-%d')
                    day_name = date_obj.day_name()
                    if (emp_id, date_str) in approved_holidays: continue
                    unavailable = str(emp.get('Unavailable Days', ''))
                    if unavailable != 'nan' and day_name in unavailable: continue
                    if day_name not in fixed_map: continue
                    fixed_start, fixed_end = fixed_map[day_name]
                    shop_start = pd.to_datetime(str(row['Start'])).hour
                    shop_end = pd.to_datetime(str(row['End'])).hour
                    if shop_end == 0: shop_end = 24
                    # Trim fixed shifts by 1h from end if enabled
                    if trim_fixed and (fixed_end - fixed_start) > min_shift_len:
                        fixed_end = fixed_end - 1
                    fixed_start = max(fixed_start, shop_start)
                    fixed_end = min(fixed_end, shop_end)
                    if fixed_end > fixed_start and (fixed_end - fixed_start) >= min_shift_len:
                        model.Add(is_working_day[(idx, date_str)] == 1)
                        for h in range(shop_start, shop_end):
                            if fixed_start <= h < fixed_end: model.Add(work[(idx, date_str, h)] == 1)
                            else: model.Add(work[(idx, date_str, h)] == 0)

            # --- Fixed role (Opening/Closing) ---
            for idx in emp_indices:
                emp = employees[idx]
                fixed_role = str(emp.get('Fixed Role', '')).strip()
                if fixed_role not in ['Opening', 'Closing']: continue
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0: end_h = 24
                    if fixed_role == 'Opening':
                        model.Add(daily_start_hour[(idx, date_str)] == start_h).OnlyEnforceIf(is_working_day[(idx, date_str)])
                    elif fixed_role == 'Closing':
                        model.Add(daily_end_hour[(idx, date_str)] == end_h).OnlyEnforceIf(is_working_day[(idx, date_str)])

            # --- Holiday blocks ---
            for idx in emp_indices:
                emp_id = employees[idx]['ID']
                emp_name = employees[idx]['Name']
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    if (emp_id, date_str) not in approved_holidays and (emp_name, date_str) not in approved_holidays:
                        continue
                    model.Add(is_working_day[(idx, date_str)] == 0)
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0: end_h = 24
                    for h in range(start_h, end_h): model.Add(work[(idx, date_str, h)] == 0)

            # --- Per-employee hours: collect originals (with override) ---
            total_contract_min = 0
            emp_original_mins = {}
            emp_effective_maxs = {}   # Takes override into account

            for idx in emp_indices:
                emp = employees[idx]

                # Contractual minimum
                if 'Minimum Contractual Hours' in emp:
                    om = safe_int(emp['Minimum Contractual Hours'], 0)
                elif 'Minimum Contractual Hours ' in emp:
                    om = safe_int(emp['Minimum Contractual Hours '], 0)
                else:
                    om = 0

                # Normal max from contract
                normal_max = safe_int(emp.get('Max Weekly Hours', 40), 40)

                # ── MAX HOURS OVERRIDE ──────────────────────────────────────
                # If a non-zero override is set, it acts as a hard ceiling
                # for this employee, replacing their normal max. The min
                # is also clamped down to the override so the constraint
                # min <= hours <= max remains satisfiable.

                effective_max = normal_max

                emp_original_mins[idx] = om
                emp_effective_maxs[idx] = effective_max
                total_contract_min += om

            # Surplus: how many hours above total minimums does the budget allow?
            if total_contract_min > 0 and weekly_budget_hours < 9999:
                total_surplus = max(0, weekly_budget_hours - total_contract_min)
            else:
                total_surplus = 9999
            
            # --- Contractual hours + fairness ---
            for idx in emp_indices:
                emp = employees[idx]
                emp_id = emp['ID']
                emp_name = emp['Name']
                
                available_days_count = 0
                for d in dates_in_order:
                    unavailable_str = str(emp.get('Unavailable Days', ''))
                    day_name = pd.to_datetime(d).day_name()
                    is_holiday = (emp_id, d) in approved_holidays or (emp_name, d) in approved_holidays
                    is_unavailable = (unavailable_str != 'nan' and day_name in unavailable_str)
                    if not is_holiday and not is_unavailable: available_days_count += 1
                
                max_physical_capacity = available_days_count * MAX_SHIFT_LENGTH
                
                original_min = emp_original_mins[idx]
                effective_max = emp_effective_maxs[idx]

                # PROPORTIONAL REDUCTION (for failed attempts)
                if reduction_pct > 0 and original_min > 0:
                    adjusted_min = max(0, math.floor(original_min * (1.0 - reduction_pct)))
                    adjusted_max = max(adjusted_min, math.floor(effective_max * (1.0 - reduction_pct)))
                else:
                    adjusted_min = original_min
                    adjusted_max = effective_max
                
                # FAIR-SHARE CAP: proportional share of surplus + 2h solver headroom
                if total_surplus < 9999 and adjusted_min > 0 and total_contract_min > 0:
                    proportional_share = total_surplus * adjusted_min / total_contract_min
                    fair_share_max = adjusted_min + max(2, math.ceil(proportional_share))
                    adjusted_max = min(adjusted_max, fair_share_max)
                
                adjusted_min = min(adjusted_min, max_physical_capacity)
                adjusted_max = max(adjusted_max, adjusted_min)  # sanity

                total_hours_vars = [
                    work[(idx, row['Date'].strftime('%Y-%m-%d'), h)] 
                    for _, row in week_data.iterrows() 
                    for h in range(pd.to_datetime(str(row['Start'])).hour, 
                                   24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour)
                ]
                
                emp_hours_var = model.NewIntVar(0, 100, f'emp_hrs_{idx}')
                model.Add(emp_hours_var == sum(total_hours_vars))
                model.Add(emp_hours_var >= adjusted_min)
                model.Add(emp_hours_var <= adjusted_max)
                
                sq_hours = model.NewIntVar(0, 10000, f'sq_hrs_{idx}')
                model.AddMultiplicationEquality(sq_hours, [emp_hours_var, emp_hours_var])
                objective_terms.append(-WEIGHT_FAIRNESS * sq_hours)
                
                total_working_days = [is_working_day[(idx, d)] for d in dates_in_order]
                model.Add(sum(total_working_days) <= MAX_CONSECUTIVE_DAYS)

            # --- Shift structure ---
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                start_h = pd.to_datetime(str(row['Start'])).hour
                end_h = pd.to_datetime(str(row['End'])).hour
                if end_h == 0: end_h = 24
                hours_range = list(range(start_h, end_h))
                for idx in emp_indices:
                    # Per-employee shift length cap: use Max Shift Length if set, else global max
                    emp_max_shift_len = safe_int(employees[idx].get('Max Shift Length', 0), 0)
                    effective_max_shift = min(MAX_SHIFT_LENGTH, emp_max_shift_len) if emp_max_shift_len > 0 else MAX_SHIFT_LENGTH

                    model.Add(sum(work[(idx, date_str, h)] for h in hours_range) > 0).OnlyEnforceIf(is_working_day[(idx, date_str)])
                    model.Add(sum(work[(idx, date_str, h)] for h in hours_range) == 0).OnlyEnforceIf(is_working_day[(idx, date_str)].Not())
                    # Pin start/end to 0 on OFF days so the rest rule formula never fires spuriously
                    model.Add(daily_start_hour[(idx, date_str)] == 0).OnlyEnforceIf(is_working_day[(idx, date_str)].Not())
                    model.Add(daily_end_hour[(idx, date_str)] == 0).OnlyEnforceIf(is_working_day[(idx, date_str)].Not())
                    for h in hours_range:
                        if h == start_h: model.Add(start[(idx, date_str, h)] == work[(idx, date_str, h)])
                        else:
                            model.Add(work[(idx, date_str, h)] >= start[(idx, date_str, h)])
                            model.Add(start[(idx, date_str, h)] >= work[(idx, date_str, h)] - work[(idx, date_str, h-1)])
                    model.Add(sum(start[(idx, date_str, h)] for h in hours_range) <= 1)
                    model.Add(daily_start_hour[(idx, date_str)] == sum(h * start[(idx, date_str, h)] for h in hours_range))
                    duration = sum(work[(idx, date_str, h)] for h in hours_range)
                    model.Add(daily_end_hour[(idx, date_str)] == daily_start_hour[(idx, date_str)] + duration)
                    model.Add(duration >= min_shift_len).OnlyEnforceIf(is_working_day[(idx, date_str)])
                    model.Add(duration <= effective_max_shift).OnlyEnforceIf(is_working_day[(idx, date_str)])

            # --- Fixed slot ---
            for idx in emp_indices:
                emp = employees[idx]
                fixed_slot = str(emp.get('Fixed Slot', ''))
                if fixed_slot in ['nan', 'None', 'Any', '']: continue
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0: end_h = 24
                    if 'Morning' in fixed_slot and 'Evening' not in fixed_slot:
                        for h in range(start_h, end_h):
                            if h >= EVENING_START_HOUR: model.Add(work[(idx, date_str, h)] == 0)
                    if 'Evening' in fixed_slot and 'Morning' not in fixed_slot:
                        for h in range(start_h, end_h):
                            if h < MORNING_END_HOUR: model.Add(work[(idx, date_str, h)] == 0)
                    if fixed_slot == 'Afternoon':
                        for h in range(start_h, end_h):
                            if h < 10 or h >= 20: model.Add(work[(idx, date_str, h)] == 0)

            # --- Daily availability windows ---
            for idx in emp_indices:
                emp = employees[idx]
                daily_avail_raw = str(emp.get('Daily Available Hours', ''))
                if daily_avail_raw in ['', 'nan', 'None']: continue
                avail_map = parse_fixed_shifts(daily_avail_raw)
                if not avail_map: continue
                for _, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    day_name = row['Date'].day_name()
                    if day_name not in avail_map: continue
                    avail_start, avail_end = avail_map[day_name]
                    shop_start = pd.to_datetime(str(row['Start'])).hour
                    shop_end = pd.to_datetime(str(row['End'])).hour
                    if shop_end == 0: shop_end = 24
                    for h in range(shop_start, shop_end):
                        if h < avail_start or h >= avail_end:
                            model.Add(work[(idx, date_str, h)] == 0)

            # --- Rest between consecutive days ---
            # For Closing-role employees (end = midnight/24), the standard formula
            # (tomorrow_start + 24) - today_end can create phantom violations because
            # daily_start_hour defaults to 0 on OFF days. We handle them separately
            # with an explicit noon-start constraint on the next worked day.
            for idx in emp_indices:
                emp = employees[idx]
                fixed_role = str(emp.get('Fixed Role', '')).strip()
                is_closer = (fixed_role == 'Closing')

                for i in range(len(dates_in_order) - 1):
                    today_d = dates_in_order[i]
                    tomorrow_d = dates_in_order[i+1]

                    if is_closer and not relax_closer_rest:
                        # Closers always finish at store-close (midnight=24).
                        # Enforce that if they work tomorrow, they start no earlier than noon.
                        model.Add(
                            daily_start_hour[(idx, tomorrow_d)] >= MIN_REST_HOURS
                        ).OnlyEnforceIf([is_working_day[(idx, today_d)], is_working_day[(idx, tomorrow_d)]])
                    elif not is_closer:
                        model.Add(
                            (daily_start_hour[(idx, tomorrow_d)] + 24) - daily_end_hour[(idx, today_d)] >= MIN_REST_HOURS
                        ).OnlyEnforceIf([is_working_day[(idx, today_d)], is_working_day[(idx, tomorrow_d)]])
                    # When relax_closer_rest=True: no consecutive-day rest constraint for closers.
                    # The Closing role constraint still forces them to end at midnight,
                    # but the solver can schedule them any start time the next day if needed.

            # --- Daily staffing + events ---
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                day_name = row['Date'].day_name()
                manual_min = safe_int(row['Minimum Staff'], 0)
                
                day_event = event_data.get(date_str, None)
                event_impact = day_event['impact'] if day_event else 0
                event_start_hour = day_event['start_hour'] if day_event else None
                
                second_start_earliest, second_start_latest, min_rush_staff = get_event_params(event_impact)
                
                sales_min = 0
                if ENABLE_HYBRID_MODE:
                    sales_val = row['Total Sales']
                    if pd.isna(sales_val): sales_val = 0
                    sales_min = math.ceil(sales_val / REVENUE_PER_STAFF)
                
                final_min_headcount = max(manual_min, sales_min)
                min_closing = safe_int(row['Minimum closing staff'], 1)
                min_headcount = max(final_min_headcount, min_closing)
                manual_max = safe_int(row['Maximum Employees'], min_headcount)
                if min_headcount > manual_max: min_headcount = manual_max
                max_headcount = manual_max  

                model.Add(sum(is_working_day[(idx, date_str)] for idx in emp_indices) >= min_headcount)
                model.Add(sum(is_working_day[(idx, date_str)] for idx in emp_indices) <= max_headcount)
                
                start_h = pd.to_datetime(str(row['Start'])).hour
                end_h = pd.to_datetime(str(row['End'])).hour
                if end_h == 0: end_h = 24
                
                for h in range(start_h, end_h): 
                    model.Add(sum(work[(idx, date_str, h)] for idx in emp_indices) >= 1)
                
                last_hour = end_h - 1
                model.Add(sum(work[(idx, date_str, last_hour)] for idx in emp_indices) >= min_closing)

                # Second start rule
                if ENABLE_STRICT_SECOND_START:
                    if day_name == 'Sunday' and start_h == 6 and max_headcount >= 2:
                        model.Add(sum(work[(idx, date_str, 6)] for idx in emp_indices) == 1)
                        model.Add(sum(work[(idx, date_str, 7)] for idx in emp_indices) >= 2)
                    elif start_h <= second_start_earliest and end_h >= second_start_latest and max_headcount >= 2:
                        for h in range(start_h, second_start_earliest): 
                            model.Add(sum(work[(idx, date_str, h)] for idx in emp_indices) == 1)
                        model.Add(sum(work[(idx, date_str, second_start_latest)] for idx in emp_indices) >= 2)

                # EVENT-AWARE STAFFING
                if day_event and event_start_hour:
                    prep_hour = max(start_h, event_start_hour - EVENT_PREP_HOURS)
                    event_end_coverage = min(event_start_hour + 3, end_h)
                    for h in range(prep_hour, event_end_coverage): 
                        model.Add(sum(work[(idx, date_str, h)] for idx in emp_indices) >= min_rush_staff)

            # --- Opening trained at first hour ---
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                start_h = pd.to_datetime(str(row['Start'])).hour
                trained = [idx for idx in emp_indices if employees[idx].get('Opening Trained', 'No') == 'Yes']
                model.Add(sum(work[(idx, date_str, start_h)] for idx in trained) >= 1)
                
            # --- Unavailable days ---
            for idx in emp_indices:
                emp = employees[idx]
                unavailable_str = str(emp.get('Unavailable Days', ''))
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    if unavailable_str != 'nan' and row['Date'].day_name() in unavailable_str: 
                        model.Add(is_working_day[(idx, date_str)] == 0)

            # --- Soft preferences ---
            for idx in emp_indices:
                emp = employees[idx]
                pref_day = str(emp.get('Preferred Day', ''))
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    if pref_day != 'nan' and row['Date'].day_name() in pref_day: 
                        objective_terms.append(WEIGHT_PREFERRED_DAY * is_working_day[(idx, date_str)])
                
                pref_slot = str(emp.get('Preferred slot', ''))
                if pref_slot in ['nan', 'None', 'Any', '']: continue
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0: end_h = 24
                    if 'Morning' in pref_slot:
                        for mh in [work[(idx, date_str, h)] for h in range(start_h, min(MORNING_END_HOUR, end_h))]:
                            objective_terms.append(WEIGHT_PREFERRED_SLOT * mh)
                    if 'Afternoon' in pref_slot:
                        for ah in [work[(idx, date_str, h)] for h in range(max(12, start_h), min(17, end_h))]:
                            objective_terms.append(WEIGHT_PREFERRED_SLOT * ah)
                    if 'Evening' in pref_slot:
                        for eh in [work[(idx, date_str, h)] for h in range(max(EVENING_START_HOUR, start_h), end_h)]:
                            objective_terms.append(WEIGHT_PREFERRED_SLOT * eh)

            # --- SOLVE ---
            model.Maximize(sum(objective_terms))
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 25.0
            status = solver.Solve(model)
            
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                return {'solver': solver, 'work': work, 'is_working_day': is_working_day, 'config': config}
            return None

        # ==========================================================
        #   GRADUATED SOLVER: TRY EACH CONFIG
        # ==========================================================
        
        solve_result = None
        for config in SOLVER_CONFIGS:
            solve_result = attempt_solve(config)
            if solve_result:
                break
        
        # ==========================================================
        #   EXTRACT RESULTS OR DIAGNOSE
        # ==========================================================
        
        if solve_result:
            solver = solve_result['solver']
            work = solve_result['work']
            is_working_day = solve_result['is_working_day']
            used_config = solve_result['config']
            
            current_week_results = []
            for idx in emp_indices:
                row_data = {
                    'Employee ID': employees[idx]['ID'],
                    'Name': employees[idx]['Name'],
                }
                weekly_h = 0
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0: end_h = 24
                    
                    shift_start, shift_end = None, None
                    for h in range(start_h, end_h):
                        if solver.Value(work[(idx, date_str, h)]):
                            if shift_start is None: shift_start = h
                            shift_end = h + 1
                            weekly_h += 1
                    
                    col_key = f"{date_str} ({row['Date'].day_name()[:3]})"
                    if shift_start is not None: 
                        row_data[col_key] = f"{shift_start:02d}:00 - {shift_end:02d}:00"
                    else:
                        emp_id = str(employees[idx]['ID']).strip()
                        emp_name = str(employees[idx]['Name']).strip()
                        if (emp_id, date_str) in approved_holidays or (emp_name, date_str) in approved_holidays: 
                            row_data[col_key] = "Holiday"
                        else: 
                            row_data[col_key] = "OFF"
                
                row_data['Total Weekly Hours'] = weekly_h
                current_week_results.append(row_data)
            
            df_week = pd.DataFrame(current_week_results)
            cols = ['Name', 'Total Weekly Hours'] + [c for c in df_week.columns if c not in ['Name', 'Employee ID', 'Total Weekly Hours']]
            df_week = df_week[cols]
            
            # Add warning row if relaxation was used
            if used_config['reduction_pct'] > 0 or used_config['min_shift'] < DEFAULT_MIN_SHIFT or used_config['trim_fixed'] or used_config.get('relax_closer_rest'):
                notes = []
                if used_config['reduction_pct'] > 0:
                    notes.append(f"Contracts reduced uniformly by {used_config['reduction_pct']*100:.0f}%")
                if used_config['min_shift'] < DEFAULT_MIN_SHIFT:
                    notes.append(f"Min shift reduced to {used_config['min_shift']}h")
                if used_config['trim_fixed']:
                    notes.append("Fixed shifts trimmed by 1h")
                if used_config.get('relax_closer_rest'):
                    notes.append("Closer consecutive-day rest rule relaxed")
                warning_row = {col: '' for col in df_week.columns}
                warning_row['Name'] = f"⚠️ ADJUSTED: {' | '.join(notes)}"
                warning_row['Total Weekly Hours'] = ''
                df_week = pd.concat([pd.DataFrame([warning_row]), df_week], ignore_index=True)
            
            weekly_dataframes[week] = df_week
            
        else:
            issues = _run_diagnostics(
                employees, emp_indices, week_data, dates_in_order,
                approved_holidays, event_data, weekly_budget_hours
            )
            diagnostic_msg = (
                f"Could not generate a schedule for Week {week} "
                f"after trying {len(SOLVER_CONFIGS)} configurations "
                f"(including contract reductions up to 15% and 5h minimum shifts).\n\n"
                f"Diagnostic Analysis:\n\n"
                + "\n\n".join(issues)
            )
            raise ValueError(diagnostic_msg)

    if weekly_dataframes:
        for week_num, df_week in weekly_dataframes.items():
            sheet_name = f"Rota_{week_num}"
            write_user_data(sheet_id, sheet_name, username, df_week)
    else:
        raise ValueError("Unknown Error: The solver finished but no Rota was generated.")
