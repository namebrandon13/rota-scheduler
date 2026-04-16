import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import os
import math
import subprocess
import sys

# Import your Google Sheets DB handler
from gsheets_db import get_sheet_data, write_sheet_data

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
WEIGHT_PREFERRED_DAY = 10      
WEIGHT_PREFERRED_SLOT = 5      

# ==============================================================================

def get_event_params(impact_score):
    if impact_score >= 8:
        return EVENT_THRESHOLDS[8]
    elif impact_score >= 5:
        return EVENT_THRESHOLDS[5]
    elif impact_score >= 1:
        return EVENT_THRESHOLDS[1]
    return EVENT_THRESHOLDS[0]

def parse_fixed_shifts(raw):
    result = {}
    raw = str(raw).strip()

    if raw in ["", "nan", "None"]:
        return result

    for item in raw.split(";"):
        parts = item.split("|")
        if len(parts) != 3:
            continue

        day_name = parts[0].strip()
        try:
            start_h = int(parts[1].split(":")[0])
            end_h = int(parts[2].split(":")[0])
            if end_h == 0:
                end_h = 24
            result[day_name] = (start_h, end_h)
        except:
            pass

    return result

def run_event_tracker():
    print("--- 0. UPDATING EVENT INTELLIGENCE ---")
    try:
        if os.path.exists(EVENT_SCRIPT):
            result = subprocess.run(
                [sys.executable, EVENT_SCRIPT],
                capture_output=True,
                text=True,
                cwd=BASE_DIR
            )
            if result.returncode == 0:
                print("Event scan complete.")
            else:
                print("Event scan error:", result.stderr)
        else:
            print("eventapicall.py not found.")
    except Exception as e:
        print("Event scanner failed:", e)
    print("----------------------------------")

def load_events_for_dates(dates_list, sheet_id):
    event_map = {}
    
    try:
        df_ev = get_sheet_data(sheet_id, 'Events')
        if df_ev.empty:
            return event_map

        df_ev.columns = df_ev.columns.str.strip()
        
        for _, row in df_ev.iterrows():
            try:
                d_str = pd.to_datetime(row['Date']).strftime('%Y-%m-%d')
                
                if d_str not in dates_list:
                    continue
                
                start_time = str(row.get('Start Time', '12:00'))
                try:
                    if ':' in start_time:
                        start_hour = int(start_time.split(':')[0])
                    else:
                        start_hour = 12 
                except:
                    start_hour = 12
                
                impact = int(row.get('Impact Score', 0))
                
                if d_str not in event_map or impact > event_map[d_str]['impact']:
                    event_map[d_str] = {
                        'impact': impact,
                        'start_hour': start_hour,
                        'event_name': str(row.get('Event Name', 'Event')),
                        'venue': str(row.get('Venue', ''))
                    }
                    
            except Exception as e:
                continue
                
        print(f"  > Loaded {len(event_map)} event day(s) for scheduling")
        
    except Exception as e:
        print(f"  > Warning reading Events tab: {e}")
    
    return event_map

# RENAMED AND PARAMETERS UPDATED HERE:
def solve_rota_final_v14(sheet_id=None, target_weeks=None):
    if not sheet_id:
        print("Error: No Google Sheet ID provided to scheduler.")
        return

    run_event_tracker()

    print("--- 1. LOADING DATA FROM GOOGLE SHEETS ---")

    try:
        df_emp = get_sheet_data(sheet_id, "Employees")
        df_shifts = get_sheet_data(sheet_id, "Shift Templates") # Updated to match your other files
        df_hol = get_sheet_data(sheet_id, "Holidays") # Updated to match your other files
        
        if df_shifts.empty or df_emp.empty:
            print("CRITICAL ERROR: Shift Template or Employees data is empty.")
            return

        df_shifts.columns = df_shifts.columns.str.strip()
        df_emp.columns = df_emp.columns.str.strip()
        
        print(f"  > Employee Columns: {list(df_emp.columns)}")

    except Exception as e:
        print(f"CRITICAL ERROR reading from GSheets. Reason: {e}")
        return

    df_shifts['Date'] = pd.to_datetime(df_shifts['Date'])

    # Handle missing Total Sales if Sales Forecast tab was removed
    if 'Total Sales' not in df_shifts.columns:
        df_shifts['Total Sales'] = 0

    # --- UPDATED FILTERING LOGIC ---
    df_shifts['Week_Num'] = df_shifts['Date'].dt.isocalendar().week
    df_shifts['Week_Start_Date'] = df_shifts['Date'].apply(lambda x: (x.date() - timedelta(days=x.weekday())))
    
    if target_weeks:
        # Now it properly compares the Date passed from the UI!
        df_shifts = df_shifts[df_shifts['Week_Start_Date'].isin(target_weeks)].copy()

    # Load Holidays
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

            print(f'  > Loaded {len(approved_holidays)} approved holidays.')
        except Exception as e:
            print(f'  > Warning: Holiday parsing error: {e}')

    df_emp['ID'] = df_emp['ID'].astype(str)
    employees = df_emp.to_dict('index')
    
    unique_weeks = df_shifts['Week_Num'].unique()
    weekly_dataframes = {}

    print(f"--- 2. SOLVING FOR {len(unique_weeks)} WEEKS ---")

    for week in unique_weeks:
        print(f"\nProcessing Week {week}...")
        week_data = df_shifts[df_shifts['Week_Num'] == week].copy()
        week_data = week_data.sort_values('Date')
        dates_in_order = week_data['Date'].dt.strftime('%Y-%m-%d').unique()
        
        event_data = load_events_for_dates(list(dates_in_order), sheet_id)
        
        weekly_budget_hours = 9999
        if 'Budget' in week_data.columns:
            val = week_data['Budget'].max()
            if not pd.isna(val) and val > 0:
                weekly_budget_hours = int(val)
                print(f"  > [CONSTRAINT] Weekly Budget: {weekly_budget_hours} hours")

        model = cp_model.CpModel()
        
        work = {}           
        start = {}          
        is_working_day = {} 
        daily_start_hour = {} 
        daily_end_hour = {}   
        
        emp_indices = df_emp.index.tolist()
        all_worked_hours_vars = []

        # 1. SETUP VARIABLES
        for idx in emp_indices:
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                start_h = pd.to_datetime(str(row['Start'])).hour
                end_h = pd.to_datetime(str(row['End'])).hour
                if end_h == 0:
                    end_h = 24

                is_working_day[(idx, date_str)] = model.NewBoolVar(f'day_{idx}_{date_str}')
                daily_start_hour[(idx, date_str)] = model.NewIntVar(0, 24, f'start_h_{idx}_{date_str}')
                daily_end_hour[(idx, date_str)] = model.NewIntVar(0, 24, f'end_h_{idx}_{date_str}')
                
                for h in range(start_h, end_h):
                    work[(idx, date_str, h)] = model.NewBoolVar(f'w_{idx}_{date_str}_{h}')
                    start[(idx, date_str, h)] = model.NewBoolVar(f's_{idx}_{date_str}_{h}')
                    all_worked_hours_vars.append(work[(idx, date_str, h)])

        # 2. CONSTRAINTS
        model.Add(sum(all_worked_hours_vars) <= weekly_budget_hours)

        for idx in emp_indices:
            emp = employees[idx]
            emp_id = str(emp['ID']).strip()
            enabled = str(emp.get('Fixed Shift Enabled', 'No')).strip()

            if enabled != "Yes":
                continue

            fixed_map = parse_fixed_shifts(emp.get('Fixed Weekly Shift', ''))

            if not fixed_map:
                continue

            for _, row in week_data.iterrows():
                date_obj = row['Date']
                date_str = date_obj.strftime('%Y-%m-%d')
                day_name = date_obj.day_name()

                if (emp_id, date_str) in approved_holidays:
                    continue

                unavailable = str(emp.get('Unavailable Days', ''))
                if unavailable != 'nan' and day_name in unavailable:
                    continue

                if day_name not in fixed_map:
                    continue

                fixed_start, fixed_end = fixed_map[day_name]
                shop_start = pd.to_datetime(str(row['Start'])).hour
                shop_end = pd.to_datetime(str(row['End'])).hour
                if shop_end == 0:
                    shop_end = 24

                fixed_start = max(fixed_start, shop_start)
                fixed_end = min(fixed_end, shop_end)

                if fixed_end <= fixed_start:
                    continue

                model.Add(is_working_day[(idx, date_str)] == 1)

                for h in range(shop_start, shop_end):
                    if fixed_start <= h < fixed_end:
                        model.Add(work[(idx, date_str, h)] == 1)
                    else:
                        model.Add(work[(idx, date_str, h)] == 0)

        for idx in emp_indices:
            emp_id = employees[idx]['ID']
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                if (emp_id, date_str) in approved_holidays or (employees[idx]['Name'], date_str) in approved_holidays:
                    model.Add(is_working_day[(idx, date_str)] == 0)
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0:
                        end_h = 24
                    for h in range(start_h, end_h):
                        model.Add(work[(idx, date_str, h)] == 0)

        print(f"  > Employee Hour Constraints:")
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
                if not is_holiday and not is_unavailable:
                    available_days_count += 1
            
            max_physical_capacity = available_days_count * MAX_SHIFT_LENGTH
            
            try:
                if 'Minimum Contractual Hours' in emp:
                    original_min = int(emp['Minimum Contractual Hours'])
                elif 'Minimum Contractual Hours ' in emp:
                    original_min = int(emp['Minimum Contractual Hours '])
                else:
                    original_min = 0 
            except:
                original_min = 0

            adjusted_min = min(original_min, max_physical_capacity)
            original_max = int(emp.get('Max Weekly Hours', 40))
            
            print(f"    - {emp_name}: Min={adjusted_min}h, Max={original_max}h (available {available_days_count} days)")

            total_hours_vars = [
                work[(idx, row['Date'].strftime('%Y-%m-%d'), h)] 
                for _, row in week_data.iterrows() 
                for h in range(
                    pd.to_datetime(str(row['Start'])).hour, 
                    24 if pd.to_datetime(str(row['End'])).hour == 0 else pd.to_datetime(str(row['End'])).hour
                )
            ]
            
            model.Add(sum(total_hours_vars) >= adjusted_min)
            model.Add(sum(total_hours_vars) <= original_max)
            
            total_working_days = [is_working_day[(idx, d)] for d in dates_in_order]
            model.Add(sum(total_working_days) <= MAX_CONSECUTIVE_DAYS) 

        for i, row in week_data.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d')
            start_h = pd.to_datetime(str(row['Start'])).hour
            end_h = pd.to_datetime(str(row['End'])).hour
            if end_h == 0:
                end_h = 24
            hours_range = list(range(start_h, end_h))

            for idx in emp_indices:
                model.Add(sum(work[(idx, date_str, h)] for h in hours_range) > 0).OnlyEnforceIf(is_working_day[(idx, date_str)])
                model.Add(sum(work[(idx, date_str, h)] for h in hours_range) == 0).OnlyEnforceIf(is_working_day[(idx, date_str)].Not())
                
                for h in hours_range:
                    if h == start_h:
                        model.Add(start[(idx, date_str, h)] == work[(idx, date_str, h)])
                    else:
                        model.Add(work[(idx, date_str, h)] >= start[(idx, date_str, h)])
                        model.Add(start[(idx, date_str, h)] >= work[(idx, date_str, h)] - work[(idx, date_str, h-1)])
                
                model.Add(sum(start[(idx, date_str, h)] for h in hours_range) <= 1)
                model.Add(daily_start_hour[(idx, date_str)] == sum(h * start[(idx, date_str, h)] for h in hours_range))
                
                duration = sum(work[(idx, date_str, h)] for h in hours_range)
                model.Add(daily_end_hour[(idx, date_str)] == daily_start_hour[(idx, date_str)] + duration)
                model.Add(duration >= MIN_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, date_str)])
                model.Add(duration <= MAX_SHIFT_LENGTH).OnlyEnforceIf(is_working_day[(idx, date_str)])

        for idx in emp_indices:
            emp = employees[idx]
            fixed_slot = str(emp.get('Fixed Slot', ''))
            if fixed_slot not in ['nan', 'None', 'Any', '']:
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0:
                        end_h = 24
                    
                    if 'Morning' in fixed_slot and 'Evening' not in fixed_slot:
                        for h in range(start_h, end_h):
                            if h >= EVENING_START_HOUR:
                                model.Add(work[(idx, date_str, h)] == 0)
                    
                    if 'Evening' in fixed_slot and 'Morning' not in fixed_slot:
                        for h in range(start_h, end_h):
                            if h < MORNING_END_HOUR:
                                model.Add(work[(idx, date_str, h)] == 0)
                    
                    if fixed_slot == 'Afternoon':
                        for h in range(start_h, end_h):
                            if h < 10 or h >= 20:
                                model.Add(work[(idx, date_str, h)] == 0)

        for idx in emp_indices:
            for i in range(len(dates_in_order) - 1):
                today = dates_in_order[i]
                tomorrow = dates_in_order[i+1]
                model.Add(
                    (daily_start_hour[(idx, tomorrow)] + 24) - daily_end_hour[(idx, today)] >= MIN_REST_HOURS
                ).OnlyEnforceIf([is_working_day[(idx, today)], is_working_day[(idx, tomorrow)]])

        print(f"  > Daily Staffing Constraints:")
        for i, row in week_data.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d')
            day_name = row['Date'].day_name()
            manual_min = int(row['Minimum Staff'])
            
            day_event = event_data.get(date_str, None)
            
            if day_event:
                event_impact = day_event['impact']
                event_start_hour = day_event['start_hour']
                print(f"    > {date_str}: Event at {event_start_hour}:00 (Impact: {event_impact})")
            else:
                event_impact = 0
                event_start_hour = None
            
            second_start_earliest, second_start_latest, min_rush_staff = get_event_params(event_impact)
            
            if day_event:
                print(f"      → SECOND_START: {second_start_earliest}-{second_start_latest}, MIN_RUSH: {min_rush_staff}")
            
            sales_min = 0
            if ENABLE_HYBRID_MODE:
                sales_val = row['Total Sales']
                if pd.isna(sales_val):
                    sales_val = 0
                sales_min = math.ceil(sales_val / REVENUE_PER_STAFF)
            
            final_min_headcount = max(manual_min, sales_min)
            min_closing = int(row['Minimum closing staff'])
            min_headcount = max(final_min_headcount, min_closing)
            
            manual_max = int(row['Maximum Employees'])
            
            if min_headcount > manual_max:
                print(f"    ⚠️ WARNING {date_str}: Min staff ({min_headcount}) > Max employees ({manual_max})!")
                print(f"       → Adjusting min to match max ({manual_max})")
                min_headcount = manual_max
            
            max_headcount = manual_max  
            
            print(f"    - {date_str} ({day_name[:3]}): Staff {min_headcount}-{max_headcount}, Closing≥{min_closing}") 

            model.Add(sum(is_working_day[(idx, date_str)] for idx in emp_indices) >= min_headcount)
            model.Add(sum(is_working_day[(idx, date_str)] for idx in emp_indices) <= max_headcount)
            
            start_h = pd.to_datetime(str(row['Start'])).hour
            end_h = pd.to_datetime(str(row['End'])).hour
            if end_h == 0:
                end_h = 24
            
            for h in range(start_h, end_h):
                model.Add(sum(work[(idx, date_str, h)] for idx in emp_indices) >= 1)
            
            last_hour = end_h - 1
            model.Add(sum(work[(idx, date_str, last_hour)] for idx in emp_indices) >= min_closing)

            if ENABLE_STRICT_SECOND_START:
                if day_name == 'Sunday' and start_h == 6 and max_headcount >= 2:
                    model.Add(sum(work[(idx, date_str, 6)] for idx in emp_indices) == 1)
                    if day_event and event_start_hour:
                        prep_hour = max(7, event_start_hour - EVENT_PREP_HOURS)
                        model.Add(sum(work[(idx, date_str, prep_hour)] for idx in emp_indices) >= min_rush_staff)
                    else:
                        model.Add(sum(work[(idx, date_str, 7)] for idx in emp_indices) >= 2)
                        
                elif start_h < second_start_earliest and end_h > second_start_latest and max_headcount >= 2:
                    for h in range(start_h, second_start_earliest):
                        model.Add(sum(work[(idx, date_str, h)] for idx in emp_indices) == 1)
                    
                    model.Add(sum(work[(idx, date_str, second_start_latest)] for idx in emp_indices) >= 2)
                    
                    if day_event and event_start_hour:
                        prep_hour = max(start_h, event_start_hour - EVENT_PREP_HOURS)
                        for h in range(prep_hour, min(event_start_hour + 2, end_h)):
                            model.Add(sum(work[(idx, date_str, h)] for idx in emp_indices) >= min_rush_staff)

            if ENABLE_RUSH_LOCK:
                operating_hours = list(range(start_h, end_h))
                for k in range(1, len(operating_hours) - 1):
                    current_h = operating_hours[k]
                    prev_h = operating_hours[k-1]
                    
                    current_staff = sum(work[(idx, date_str, current_h)] for idx in emp_indices)
                    prev_staff = sum(work[(idx, date_str, prev_h)] for idx in emp_indices)
                    
                    rush_active = model.NewBoolVar(f'rush_active_{date_str}_{prev_h}')
                    model.Add(prev_staff >= DEFAULT_RUSH_TRIGGER).OnlyEnforceIf(rush_active)
                    model.Add(prev_staff < DEFAULT_RUSH_TRIGGER).OnlyEnforceIf(rush_active.Not())
                    
                    model.Add(current_staff >= min_rush_staff).OnlyEnforceIf(rush_active)

        for i, row in week_data.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d')
            start_h = pd.to_datetime(str(row['Start'])).hour
            trained = [idx for idx in emp_indices if employees[idx].get('Opening Trained', 'No') == 'Yes']
            model.Add(sum(work[(idx, date_str, start_h)] for idx in trained) >= 1)
            
        for idx in emp_indices:
            emp = employees[idx]
            unavailable_str = str(emp.get('Unavailable Days', ''))
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                if unavailable_str != 'nan' and row['Date'].day_name() in unavailable_str:
                    model.Add(is_working_day[(idx, date_str)] == 0)

        objective_terms = []
        
        for idx in emp_indices:
            emp = employees[idx]
            
            pref_day = str(emp.get('Preferred Day', ''))
            for i, row in week_data.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                if pref_day != 'nan' and row['Date'].day_name() in pref_day:
                    objective_terms.append(WEIGHT_PREFERRED_DAY * is_working_day[(idx, date_str)])
            
            pref_slot = str(emp.get('Preferred slot', ''))
            if pref_slot not in ['nan', 'None', 'Any', '']:
                for i, row in week_data.iterrows():
                    date_str = row['Date'].strftime('%Y-%m-%d')
                    start_h = pd.to_datetime(str(row['Start'])).hour
                    end_h = pd.to_datetime(str(row['End'])).hour
                    if end_h == 0:
                        end_h = 24
                    
                    if 'Morning' in pref_slot:
                        morning_hours = [work[(idx, date_str, h)] for h in range(start_h, min(MORNING_END_HOUR, end_h))]
                        if morning_hours:
                            for mh in morning_hours:
                                objective_terms.append(WEIGHT_PREFERRED_SLOT * mh)
                    
                    if 'Afternoon' in pref_slot:
                        afternoon_hours = [work[(idx, date_str, h)] for h in range(max(12, start_h), min(17, end_h))]
                        if afternoon_hours:
                            for ah in afternoon_hours:
                                objective_terms.append(WEIGHT_PREFERRED_SLOT * ah)
                    
                    if 'Evening' in pref_slot:
                        evening_hours = [work[(idx, date_str, h)] for h in range(max(EVENING_START_HOUR, start_h), end_h)]
                        if evening_hours:
                            for eh in evening_hours:
                                objective_terms.append(WEIGHT_PREFERRED_SLOT * eh)

        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0 
        status = solver.Solve(model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"  > Schedule found for Week {week}")
            
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
                    if end_h == 0:
                        end_h = 24
                    
                    shift_start, shift_end = None, None
                    for h in range(start_h, end_h):
                        if solver.Value(work[(idx, date_str, h)]):
                            if shift_start is None:
                                shift_start = h
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
            
            weekly_dataframes[week] = df_week
            
        else:
            print(f"  > NO SOLUTION for Week {week}. Budget too tight or constraints conflict?")

    # --- WRITE TO GOOGLE SHEETS ---
    if weekly_dataframes:
        print("\n--- WRITING TO GOOGLE SHEETS ---")
        for week_num, df_week in weekly_dataframes.items():
            sheet_name = f"Rota_{week_num}"
            print(f"  > Uploading {sheet_name} to Google Sheets...")
            write_sheet_data(sheet_id, sheet_name, df_week)
        
        print("\nSUCCESS! Rota generated and uploaded to Google Sheets.")
    else:
        print("No Rota generated for any week.")
