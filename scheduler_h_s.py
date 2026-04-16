import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import os
import math
import subprocess
import sys

# Import your database handler
from gsheets_db import get_user_data, write_user_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==============================================================================
#                            BUSINESS CONTROL PANEL
# ==============================================================================
MIN_SHIFT_LENGTH = 6
MAX_SHIFT_LENGTH = 9
MIN_REST_HOURS = 12
MAX_CONSECUTIVE_DAYS = 6

# --- SOFT CONSTRAINT WEIGHTS ---
WEIGHT_CONTRACT_VIOLATION = 1000000 
WEIGHT_UTILIZATION = 10000          
WEIGHT_EXTRA_FAIRNESS = 5000        
WEIGHT_FLAT_PENALTY = 10            

# ==============================================================================

def solve_rota_final_v14(sheet_id=None, target_weeks=None, username=None):
    if not sheet_id or not username:
        raise ValueError("Missing Sheet ID or Username.")

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

    employees = df_emp.to_dict('index')
    emp_indices = df_emp.index.tolist()
    
    unique_weeks = df_shifts['Week_Num'].unique()
    weekly_dataframes = {}

    for week in unique_weeks:
        week_data = df_shifts[df_shifts['Week_Num'] == week].copy().sort_values('Date')
        dates_in_order = week_data['Date'].dt.strftime('%Y-%m-%d').unique()
        weekly_budget_hours = int(week_data['Budget'].max()) if 'Budget' in week_data.columns else 9999

        total_physical_hours = sum(int(row['Maximum Employees']) * MAX_SHIFT_LENGTH for _, row in week_data.iterrows())
        daily_boost = math.ceil(max(0, weekly_budget_hours - total_physical_hours) / (len(week_data) * MAX_SHIFT_LENGTH)) if len(week_data) > 0 else 0

        model = cp_model.CpModel()
        work, start, is_working_day, daily_start_hour, daily_end_hour = {}, {}, {}, {}, {}
        all_worked_hours_vars = []
        objective_terms = []

        for idx in emp_indices:
            total_hours_vars = []
            for i, row in week_data.iterrows():
                d_str = row['Date'].strftime('%Y-%m-%d')
                s_h = pd.to_datetime(str(row['Start'])).hour
                e_h = 24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour

                is_working_day[(idx, d_str)] = model.NewBoolVar(f'day_{idx}_{d_str}')
                daily_start_hour[(idx, d_str)] = model.NewIntVar(0, 24, f'start_h_{idx}_{d_str}')
                daily_end_hour[(idx, d_str)] = model.NewIntVar(0, 24, f'end_h_{idx}_{d_str}')
                
                for h in range(s_h, e_h):
                    w_var = model.NewBoolVar(f'w_{idx}_{d_str}_{h}')
                    work[(idx, d_str, h)] = w_var
                    start[(idx, d_str, h)] = model.NewBoolVar(f's_{idx}_{d_str}_{h}')
                    all_worked_hours_vars.append(w_var)
                    total_hours_vars.append(w_var)

            emp = employees[idx]
            o_min, o_max = int(emp.get('Minimum Contractual Hours', 0)), int(emp.get('Max Weekly Hours', 45))
            
            actual_h = model.NewIntVar(0, 100, f'actual_h_{idx}')
            model.Add(actual_h == sum(total_hours_vars))
            
            missing_h = model.NewIntVar(0, 100, f'missing_h_{idx}')
            model.Add(missing_h >= o_min - actual_h)
            objective_terms.append(-WEIGHT_CONTRACT_VIOLATION * missing_h)
            model.Add(actual_h <= o_max)

            extra_h = model.NewIntVar(0, 100, f'extra_h_{idx}')
            model.Add(extra_h >= actual_h - o_min)
            sq_extra_h = model.NewIntVar(0, 10000, f'sq_extra_{idx}')
            model.AddMultiplicationEquality(sq_extra_h, [extra_h, extra_h])
            objective_terms.append(-WEIGHT_EXTRA_FAIRNESS * sq_extra_h)
            objective_terms.append(-WEIGHT_FLAT_PENALTY * extra_h)

        model.Add(sum(all_worked_hours_vars) <= weekly_budget_hours)

        for i, row in week_data.iterrows():
            d_str = row['Date'].strftime('%Y-%m-%d')
            s_h = pd.to_datetime(str(row['Start'])).hour
            e_h = 24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour
            m_max = int(row['Maximum Employees']) + daily_boost
            m_closing = int(row.get('Minimum closing staff', 1))
            
            model.Add(sum(is_working_day[(idx, d_str)] for idx in emp_indices) <= m_max)
            
            # Trained Opener
            trained_ids = [idx for idx in emp_indices if employees[idx].get('Opening Trained') == 'Yes']
            if trained_ids:
                model.Add(sum(work[(idx, d_str, s_h)] for idx in trained_ids) >= 1)

            # Minimum Closing Staff (Final hour of business)
            model.Add(sum(work[(idx, d_str, e_h - 1)] for idx in emp_indices) >= m_closing)

            for idx in emp_indices:
                h_vars = [work[(idx, d_str, h)] for h in range(s_h, e_h)]
                model.Add(sum(h_vars) >= MIN_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, d_str)])
                model.Add(sum(h_vars) <= MAX_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, d_str)])
                model.Add(sum(h_vars) == 0).OnlyEnforceIf(is_working_day[(idx, d_str)].Not())
                
                for h in range(s_h, e_h):
                    if h == s_h: model.Add(start[(idx, d_str, h)] == work[(idx, d_str, h)])
                    else: model.Add(start[(idx, d_str, h)] >= work[(idx, d_str, h)] - work[(idx, d_str, h-1)])
                
                model.Add(sum(start[(idx, d_str, h)] for h in range(s_h, e_h)) <= 1)
                model.Add(daily_start_hour[(idx, d_str)] == sum(h * start[(idx, d_str, h)] for h in range(s_h, e_h)))
                model.Add(daily_end_hour[(idx, d_str)] == daily_start_hour[(idx, d_str)] + sum(h_vars))

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
                    s_h = pd.to_datetime(str(row['Start'])).hour
                    e_h = 24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour
                    shift_h = [h for h in range(s_h, e_h) if solver.Value(work[(idx, d_s, h)])]
                    col = f"{d_s} ({row['Date'].day_name()[:3]})"
                    if shift_h:
                        rd[col] = f"{min(shift_h):02d}:00 - {max(shift_h)+1:02d}:00"
                        rd['Total Weekly Hours'] += len(shift_h)
                    else: rd[col] = "OFF"
                res.append(rd)
            weekly_dataframes[week] = pd.DataFrame(res)

    for wk_n, df_w in weekly_dataframes.items():
        write_user_data(sheet_id, f"Rota_{wk_n}", username, df_w)
