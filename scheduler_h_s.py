import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import os
import math
import subprocess
import sys

# Import your new database handler
from gsheets_db import get_user_data, write_user_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVENT_SCRIPT = os.path.join(BASE_DIR, "eventapicall.py")

# ==============================================================================
#                            BUSINESS CONTROL PANEL
# ==============================================================================

ENABLE_HYBRID_MODE = True
REVENUE_PER_STAFF = 800   

MIN_SHIFT_LENGTH = 6
MAX_SHIFT_LENGTH = 9
MIN_REST_HOURS = 12
MAX_CONSECUTIVE_DAYS = 6

# --- DEFAULT VALUES (No Event) ---
ENABLE_STRICT_SECOND_START = True
DEFAULT_SECOND_START_EARLIEST = 9   
DEFAULT_SECOND_START_LATEST = 10    

ENABLE_RUSH_LOCK = True 
DEFAULT_RUSH_TRIGGER = 2
DEFAULT_MIN_RUSH_STAFF = 2

# --- EVENT-BASED OVERRIDES ---
EVENT_PREP_HOURS = 4

EVENT_THRESHOLDS = {
    8: (7, 8, 4),   # High impact (8-10)
    5: (8, 9, 3),   # Medium impact (5-7)
    1: (9, 10, 2),  # Low impact (1-4)
    0: (9, 10, 2),  # No event / default
}

EVENING_START_HOUR = 17 
MORNING_END_HOUR = 12    

# --- SOFT CONSTRAINT WEIGHTS ---
# Utilization is high to ensure we use the budget
# Extra Fairness is HIGHER to ensure that budget is shared equally
WEIGHT_UTILIZATION = 1000   
WEIGHT_EXTRA_FAIRNESS = 5000  # Penalty for hours worked ABOVE minimum (Square)
WEIGHT_PREFERRED_DAY = 200   
WEIGHT_PREFERRED_SLOT = 100  

# ==============================================================================

def get_event_params(impact_score):
    if impact_score >= 8: return EVENT_THRESHOLDS[8]
    elif impact_score >= 5: return EVENT_THRESHOLDS[5]
    elif impact_score >= 1: return EVENT_THRESHOLDS[1]
    return EVENT_THRESHOLDS[0]

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
                try:
                    start_hour = int(start_time.split(':')[0]) if ':' in start_time else 12 
                except: start_hour = 12
                impact = int(row.get('Impact Score', 0))
                if d_str not in event_map or impact > event_map[d_str]['impact']:
                    event_map[d_str] = {
                        'impact': impact,
                        'start_hour': start_hour,
                        'event_name': str(row.get('Event Name', 'Event')),
                        'venue': str(row.get('Venue', ''))
                    }
            except: continue
    except: pass
    return event_map

def solve_rota_final_v14(sheet_id=None, target_weeks=None, username=None):
    if not sheet_id or not username:
        raise ValueError("Missing Sheet ID or Username.")

    run_event_tracker()

    df_emp = get_user_data(sheet_id, "Employees", username)
    df_shifts = get_user_data(sheet_id, "Shift Template", username) 
    df_hol = get_user_data(sheet_id, "Holiday", username) 
    df_events = get_user_data(sheet_id, "Events", username)
    
    df_shifts.columns = df_shifts.columns.str.strip()
    df_emp.columns = df_emp.columns.str.strip()
    df_shifts['Date'] = pd.to_datetime(df_shifts['Date'])
    df_shifts = df_shifts.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    df_shifts['Week_Num'] = df_shifts['Date'].dt.isocalendar().week
    df_shifts['Week_Start_Str'] = df_shifts['Date'].apply(lambda x: (x.date() - timedelta(days=x.weekday())).strftime('%Y-%m-%d'))
    
    if target_weeks:
        t_weeks_str = [x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x) for x in target_weeks]
        df_shifts = df_shifts[df_shifts['Week_Start_Str'].isin(t_weeks_str)].copy()

    approved_holidays = set() 
    if not df_hol.empty:
        try:
            df_hol.columns = df_hol.columns.str.strip()
            df_hol['Date'] = pd.to_datetime(df_hol['Date']).dt.normalize()
            approved_df = df_hol[df_hol['Status'].astype(str).str.lower() == 'approved']
            for _, row in approved_df.iterrows():
                h_date = row['Date'].strftime('%Y-%m-%d')
                h_id = str(row.get('Employee ID', row.get('Name', ''))).strip()
                approved_holidays.add((h_id, h_date))
        except: pass

    df_emp['ID'] = df_emp['ID'].astype(str)
    employees = df_emp.to_dict('index')
    emp_indices = df_emp.index.tolist()
    
    unique_weeks = df_shifts['Week_Num'].unique()
    weekly_dataframes = {}

    for week in unique_weeks:
        week_data = df_shifts[df_shifts['Week_Num'] == week].copy().sort_values('Date')
        dates_in_order = week_data['Date'].dt.strftime('%Y-%m-%d').unique()
        event_data = load_events_for_dates(list(dates_in_order), df_events)
        weekly_budget_hours = int(week_data['Budget'].max()) if 'Budget' in week_data.columns else 9999

        # --- AUTO-OVERRIDE CALCULATION ---
        total_physical_hours = sum(int(row['Maximum Employees']) * ( (24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour) - pd.to_datetime(str(row['Start'])).hour ) for _, row in week_data.iterrows())
        budget_deficit_shifts = math.ceil(max(0, weekly_budget_hours - total_physical_hours) / MAX_SHIFT_LENGTH)
        daily_shift_boost = math.ceil(budget_deficit_shifts / len(week_data)) if len(week_data) > 0 else 0

        model = cp_model.CpModel()
        work, start, is_working_day, daily_start_hour, daily_end_hour = {}, {}, {}, {}, {}
        all_worked_hours_vars = []
        objective_terms = []

        for idx in emp_indices:
            total_hours_vars = []
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                s_h = pd.to_datetime(str(row['Start'])).hour
                e_h = 24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour

                is_working_day[(idx, date_str)] = model.NewBoolVar(f'day_{idx}_{date_str}')
                daily_start_hour[(idx, date_str)] = model.NewIntVar(0, 24, f'start_h_{idx}_{date_str}')
                daily_end_hour[(idx, date_str)] = model.NewIntVar(0, 24, f'end_h_{idx}_{date_str}')
                
                for h in range(s_h, e_h):
                    work[(idx, date_str, h)] = model.NewBoolVar(f'w_{idx}_{date_str}_{h}')
                    start[(idx, date_str, h)] = model.NewBoolVar(f's_{idx}_{date_str}_{h}')
                    all_worked_hours_vars.append(work[(idx, date_str, h)])
                    total_hours_vars.append(work[(idx, date_str, h)])

            # --- CONTRACTS & EXTRA HOURS FAIRNESS ---
            emp = employees[idx]
            o_min = int(emp.get('Minimum Contractual Hours', 0))
            o_max = int(emp.get('Max Weekly Hours', 40))
            
            emp_total_h = model.NewIntVar(0, 100, f'total_h_{idx}')
            model.Add(emp_total_h == sum(total_hours_vars))
            model.Add(emp_total_h >= o_min)
            model.Add(emp_total_h <= o_max)

            # Fairness: Penalize squaring the "Extra Hours" only.
            extra_h = model.NewIntVar(0, 100, f'extra_h_{idx}')
            model.Add(extra_h == emp_total_h - o_min)
            sq_extra_h = model.NewIntVar(0, 10000, f'sq_extra_h_{idx}')
            model.AddMultiplicationEquality(sq_extra_h, [extra_h, extra_h])
            objective_terms.append(-WEIGHT_EXTRA_FAIRNESS * sq_extra_h)

        model.Add(sum(all_worked_hours_vars) <= weekly_budget_hours)

        for idx in emp_indices:
            emp = employees[idx]
            emp_id, emp_name = str(emp['ID']).strip(), str(emp['Name']).strip()
            fixed_map = parse_fixed_shifts(emp.get('Fixed Weekly Shift', '')) if str(emp.get('Fixed Shift Enabled')) == "Yes" else {}
            unavailable = str(emp.get('Unavailable Days', ''))

            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                day_name = row['Date'].day_name()
                s_h = pd.to_datetime(str(row['Start'])).hour
                e_h = 24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour

                if (emp_id, date_str) in approved_holidays or (emp_name, date_str) in approved_holidays or (unavailable != 'nan' and day_name in unavailable):
                    model.Add(is_working_day[(idx, date_str)] == 0)
                    for h in range(s_h, e_h): model.Add(work[(idx, date_str, h)] == 0)
                    continue

                if day_name in fixed_map:
                    f_s, f_e = fixed_map[day_name]
                    f_s, f_e = max(f_s, s_h), min(f_e, e_h)
                    if f_e > f_s:
                        model.Add(is_working_day[(idx, date_str)] == 1)
                        for h in range(s_h, e_h):
                            if f_s <= h < f_e: model.Add(work[(idx, date_str, h)] == 1)
                            else: model.Add(work[(idx, date_str, h)] == 0)

            for i in range(len(dates_in_order)-1):
                d1, d2 = dates_in_order[i], dates_in_order[i+1]
                model.Add((daily_start_hour[(idx, d2)] + 24) - daily_end_hour[(idx, d1)] >= MIN_REST_HOURS).OnlyEnforceIf([is_working_day[(idx, d1)], is_working_day[(idx, d2)]])

        for i, row in week_data.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d')
            s_h = pd.to_datetime(str(row['Start'])).hour
            e_h = 24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour
            m_min = int(row['Minimum Staff'])
            m_max = int(row['Maximum Employees']) + daily_shift_boost
            
            working_now = [is_working_day[(idx, date_str)] for idx in emp_indices]
            model.Add(sum(working_now) >= m_min)
            model.Add(sum(working_now) <= m_max)

            trained = [idx for idx in emp_indices if employees[idx].get('Opening Trained') == 'Yes']
            model.Add(sum(work[(idx, date_str, s_h)] for idx in trained) >= 1)

            for idx in emp_indices:
                h_vars = [work[(idx, date_str, h)] for h in range(s_h, e_h)]
                model.Add(sum(h_vars) > 0).OnlyEnforceIf(is_working_day[(idx, date_str)])
                model.Add(sum(h_vars) == 0).OnlyEnforceIf(is_working_day[(idx, date_str)].Not())
                model.Add(sum(h_vars) >= MIN_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, date_str)])
                model.Add(sum(h_vars) <= MAX_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, date_str)])
                
                for h in range(s_h, e_h):
                    if h == s_h: model.Add(start[(idx, date_str, h)] == work[(idx, date_str, h)])
                    else: model.Add(start[(idx, date_str, h)] >= work[(idx, date_str, h)] - work[(idx, date_str, h-1)])
                model.Add(sum(start[(idx, date_str, h)] for h in range(s_h, e_h)) <= 1)
                model.Add(daily_start_hour[(idx, date_str)] == sum(h * start[(idx, date_str, h)] for h in range(s_h, e_h)))
                model.Add(daily_end_hour[(idx, date_str)] == daily_start_hour[(idx, date_str)] + sum(h_vars))

        objective_terms.append(WEIGHT_UTILIZATION * sum(all_worked_hours_vars))
        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        if solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            res = []
            for idx in emp_indices:
                rd = {'Name': employees[idx]['Name'], 'Total Weekly Hours': 0}
                for _, row in week_data.iterrows():
                    d_s = row['Date'].strftime('%Y-%m-%d')
                    s_h, e_h = pd.to_datetime(str(row['Start'])).hour, (24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour)
                    shift = [h for h in range(s_h, e_h) if solver.Value(work[(idx, d_s, h)])]
                    col = f"{d_s} ({row['Date'].day_name()[:3]})"
                    if shift:
                        rd[col] = f"{min(shift):02d}:00 - {max(shift)+1:02d}:00"
                        rd['Total Weekly Hours'] += len(shift)
                    else:
                        rd[col] = "Holiday" if (str(employees[idx]['ID']), d_s) in approved_holidays else "OFF"
                res.append(rd)
            weekly_dataframes[week] = pd.DataFrame(res)

    for wk_n, df_w in weekly_dataframes.items():
        write_user_data(sheet_id, f"Rota_{wk_n}", username, df_w)
