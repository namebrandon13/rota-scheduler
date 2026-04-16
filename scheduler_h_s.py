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

# ==============================================================================
#                            BUSINESS CONTROL PANEL
# ==============================================================================
MIN_SHIFT_LENGTH = 6
MAX_SHIFT_LENGTH = 9
MIN_REST_HOURS = 12
MAX_CONSECUTIVE_DAYS = 6

# --- PENALTY WEIGHTS ---
# Utilization is moderate, Fairness is EXTREMELY high.
# Contract violation is effectively infinite.
WEIGHT_CONTRACT_VIOLATION = 1000000 
WEIGHT_EQUALITY_DRIVE = 50000       # Penalty for "Extra Hours" variance
WEIGHT_UTILIZATION = 500            # Reward for using budget
WEIGHT_PREFERRED_DAY = 200   
WEIGHT_PREFERRED_SLOT = 100  

# ==============================================================================

def solve_rota_final_v14(sheet_id=None, target_weeks=None, username=None):
    if not sheet_id or not username:
        raise ValueError("Missing Sheet ID or Username.")

    # 1. Fetch Data
    df_emp = get_user_data(sheet_id, "Employees", username)
    df_shifts = get_user_data(sheet_id, "Shift Template", username) 
    df_hol = get_user_data(sheet_id, "Holiday", username) 
    
    df_shifts.columns = df_shifts.columns.str.strip()
    df_emp.columns = df_emp.columns.str.strip()
    df_shifts['Date'] = pd.to_datetime(df_shifts['Date'])
    df_shifts = df_shifts.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    df_shifts['Week_Num'] = df_shifts['Date'].dt.isocalendar().week
    df_shifts['Week_Start_Str'] = df_shifts['Date'].apply(lambda x: (x.date() - timedelta(days=x.weekday())).strftime('%Y-%m-%d'))
    
    if target_weeks:
        t_weeks_str = [x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x) for x in target_weeks]
        df_shifts = df_shifts[df_shifts['Week_Start_Str'].isin(t_weeks_str)].copy()

    # 2. Setup Employees
    employees = df_emp.to_dict('index')
    emp_indices = df_emp.index.tolist()
    
    unique_weeks = df_shifts['Week_Num'].unique()
    weekly_dataframes = {}

    for week in unique_weeks:
        week_data = df_shifts[df_shifts['Week_Num'] == week].copy().sort_values('Date')
        dates_in_order = week_data['Date'].dt.strftime('%Y-%m-%d').unique()
        weekly_budget_hours = int(week_data['Budget'].max()) if 'Budget' in week_data.columns else 9999

        # --- DYNAMIC HEADCOUNT OVERRIDE ---
        # Ensure the daily max staff is high enough to physically allow everyone to hit their hours
        total_physical_hours = sum(int(row['Maximum Employees']) * MAX_SHIFT_LENGTH for _, row in week_data.iterrows())
        daily_boost = math.ceil(max(0, weekly_budget_hours - total_physical_hours) / (len(week_data) * MAX_SHIFT_LENGTH)) if len(week_data) > 0 else 0

        model = cp_model.CpModel()
        work, start, is_working_day, daily_start_hour, daily_end_hour = {}, {}, {}, {}, {}
        all_worked_hours_vars = []
        objective_terms = []

        for idx in emp_indices:
            emp_week_hours = []
            for i, row in week_data.iterrows():
                d_str = row['Date'].strftime('%Y-%m-%d')
                s_h, e_h = pd.to_datetime(str(row['Start'])).hour, (24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour)

                is_working_day[(idx, d_str)] = model.NewBoolVar(f'day_{idx}_{d_str}')
                daily_start_hour[(idx, d_str)] = model.NewIntVar(0, 24, f'start_h_{idx}_{d_str}')
                daily_end_hour[(idx, d_str)] = model.NewIntVar(0, 24, f'end_h_{idx}_{d_str}')
                
                for h in range(s_h, e_h):
                    work[(idx, d_str, h)] = model.NewBoolVar(f'w_{idx}_{d_str}_{h}')
                    start[(idx, d_str, h)] = model.NewBoolVar(f's_{idx}_{d_str}_{h}')
                    all_worked_hours_vars.append(work[(idx, d_str, h)])
                    emp_week_hours.append(work[(idx, d_str, h)])

            # --- TARGET CONTRACT LOGIC ---
            emp = employees[idx]
            min_h = int(emp.get('Minimum Contractual Hours', 0))
            max_h = int(emp.get('Max Weekly Hours', 45))
            
            actual_h = model.NewIntVar(0, 100, f'actual_h_{idx}')
            model.Add(actual_h == sum(emp_week_hours))
            
            # 1. Hard Target Violation (Penalty for missing min contract)
            missing_h = model.NewIntVar(0, 100, f'missing_h_{idx}')
            model.Add(missing_h >= min_h - actual_h)
            objective_terms.append(-WEIGHT_CONTRACT_VIOLATION * missing_h)
            
            # 2. Limit to Max
            model.Add(actual_h <= max_h)

            # 3. EXTRA HOURS FAIRNESS (Penalty for variance in "extra" hours)
            extra_h = model.NewIntVar(0, 100, f'extra_h_{idx}')
            model.Add(extra_h == actual_h - min_h)
            
            # Square the extra hours: 1hr extra = 1 penalty, 8hr extra = 64 penalty.
            sq_extra_h = model.NewIntVar(0, 10000, f'sq_extra_{idx}')
            model.AddMultiplicationEquality(sq_extra_h, [extra_h, extra_h])
            objective_terms.append(-WEIGHT_EQUALITY_DRIVE * sq_extra_h)

        # Budget Constraint
        model.Add(sum(all_worked_hours_vars) <= weekly_budget_hours)

        # Daily Logic
        for i, row in week_data.iterrows():
            d_str = row['Date'].strftime('%Y-%m-%d')
            s_h, e_h = pd.to_datetime(str(row['Start'])).hour, (24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour)
            m_max = int(row['Maximum Employees']) + daily_boost
            
            model.Add(sum(is_working_day[(idx, d_str)] for idx in emp_indices) <= m_max)
            
            # Opener constraint
            trained_ids = [idx for idx in emp_indices if employees[idx].get('Opening Trained') == 'Yes']
            if trained_ids:
                model.Add(sum(work[(idx, d_str, s_h)] for idx in trained_ids) >= 1)

            for idx in emp_indices:
                h_vars = [work[(idx, d_str, h)] for h in range(s_h, e_h)]
                
                # Active shift must be between MIN and MAX length
                model.Add(sum(h_vars) >= MIN_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, d_str)])
                model.Add(sum(h_vars) <= MAX_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, d_str)])
                model.Add(sum(h_vars) == 0).OnlyEnforceIf(is_working_day[(idx, d_str)].Not())
                
                # Shift continuity (no gaps)
                for h in range(s_h, e_h):
                    if h == s_h: model.Add(start[(idx, d_str, h)] == work[(idx, d_str, h)])
                    else: model.Add(start[(idx, d_str, h)] >= work[(idx, d_str, h)] - work[(idx, d_str, h-1)])
                model.Add(sum(start[(idx, d_str, h)] for h in range(s_h, e_h)) <= 1)
                
                # Link hours to start/end for rest calculation
                model.Add(daily_start_hour[(idx, d_str)] == sum(h * start[(idx, d_str, h)] for h in range(s_h, e_h)))
                model.Add(daily_end_hour[(idx, d_str)] == daily_start_hour[(idx, d_str)] + sum(h_vars))

        # Objective: Maximize utilization within fairness and contract bounds
        objective_terms.append(WEIGHT_UTILIZATION * sum(all_worked_hours_vars))
        model.Maximize(sum(objective_terms))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            res = []
            for idx in emp_indices:
                rd = {'Name': employees[idx]['Name'], 'Total Weekly Hours': 0}
                for _, row in week_data.iterrows():
                    d_s = row['Date'].strftime('%Y-%m-%d')
                    h_r = range(pd.to_datetime(str(row['Start'])).hour, (24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour))
                    shift_h = [h for h in h_r if solver.Value(work[(idx, d_s, h)])]
                    col = f"{d_s} ({row['Date'].day_name()[:3]})"
                    if shift_h:
                        rd[col] = f"{min(shift_h):02d}:00 - {max(shift_h)+1:02d}:00"
                        rd['Total Weekly Hours'] += len(shift_h)
                    else:
                        rd[col] = "OFF"
                res.append(rd)
            weekly_dataframes[week] = pd.DataFrame(res)
        else:
            raise ValueError(f"Infeasible week {week}. Check if Staffing Max allows enough shifts for contracts.")

    for wk_n, df_w in weekly_dataframes.items():
        write_user_data(sheet_id, f"Rota_{wk_n}", username, df_w)
