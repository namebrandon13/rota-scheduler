import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import time

def get_gspread_client():
    """Authenticates and returns the gspread client using Streamlit secrets."""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_sheet_data(sheet_id, tab_name):
    """Fetches a specific tab with automatic retries for Google 429 Quota errors."""
    client = get_gspread_client()
    
    # Try up to 4 times if we hit a rate limit
    for attempt in range(4):
        try:
            spreadsheet = client.open_by_key(sheet_id)
            worksheet = spreadsheet.worksheet(tab_name)
            df = get_as_dataframe(worksheet, evaluate_formulas=True)
            df = df.dropna(how='all').dropna(axis=1, how='all')
            return df
            
        except gspread.exceptions.APIError as e:
            if '429' in str(e) or 'Quota' in str(e):
                sleep_time = 2 ** attempt  # Pauses for 1s, then 2s, then 4s...
                print(f"⚠️ Google API Rate Limit hit. Pausing {sleep_time}s before retrying {tab_name}...")
                time.sleep(sleep_time)
            else:
                print(f"Error reading {tab_name}: {e}")
                return pd.DataFrame()
                
        except gspread.exceptions.WorksheetNotFound:
            print(f"Warning: Tab '{tab_name}' not found.")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error reading {tab_name}: {e}")
            return pd.DataFrame()
            
    # If it fails all 4 retries
    st.error(f"Failed to fetch {tab_name} due to strict Google API limits. Please wait 1 minute.")
    return pd.DataFrame()

def write_sheet_data(sheet_id, worksheet_name, df):
    """Writes a DataFrame to a Google Sheet, creating the tab if needed."""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(sheet_id)
        
        try:
            worksheet = sh.worksheet(worksheet_name)
            print(f"Tab '{worksheet_name}' found. Overwriting...")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Tab '{worksheet_name}' not found. Creating a new tab...")
            num_rows = str(max(1000, len(df) + 100))
            num_cols = str(max(26, len(df.columns) + 5))
            worksheet = sh.add_worksheet(title=worksheet_name, rows=num_rows, cols=num_cols)
        
        worksheet.clear()
        set_with_dataframe(worksheet, df)
        print(f"Successfully saved to Google Sheets tab: {worksheet_name}")
        
    except Exception as e:
        print(f"CRITICAL WRITE ERROR: {e}")
        st.error(f"Google Sheets Upload Failed: {e}")
        raise e
# ... (Keep all your existing code at the top of gsheets_db.py) ...

def get_user_database():
    """Reads the master user database from Google Sheets."""
    master_id = st.secrets["master_db_sheet_id"]
    df = get_sheet_data(master_id, "Users")
    if df.empty:
        return {}
    
    # Convert dataframe to a dictionary for easy login checking
    users = {}
    for _, row in df.iterrows():
        users[str(row['Username'])] = {
            "password": str(row['Password']),
            "sheet_id": str(row['Sheet_ID'])
        }
    return users

def create_new_user_sheet(username):
    """
    Creates a brand new Google Sheet inside the Admin's shared folder, 
    shares it, and sets up the default tabs. Returns the new Sheet ID.
    """
    import streamlit as st
    client = get_gspread_client()
    
    admin_email = st.secrets["admin_email"]
    folder_id = st.secrets["database_folder_id"]
    file_name = f"Rota_Scheduler_{username}"
    
    print(f"Creating new Google Sheet: {file_name} in folder {folder_id}...")
    
    # 1. Create the new file INSIDE your shared folder (fixes the quota error!)
    new_sheet = client.create(file_name, folder_id=folder_id)
    new_sheet_id = new_sheet.id
    
    # 2. Share it explicitly just to be safe
    new_sheet.share(admin_email, perm_type='user', role='writer')
    
    # 3. Create the required tabs
    tabs_to_create = ["Employees", "Shift Template", "Holiday", "Events"]
    for tab in tabs_to_create:
        new_sheet.add_worksheet(title=tab, rows="100", cols="20")
    
    # 4. Delete the default "Sheet1" that Google makes automatically
    try:
        sheet1 = new_sheet.worksheet("Sheet1")
        new_sheet.del_worksheet(sheet1)
    except:
        pass
        
    return new_sheet_id

def register_user_in_db(username, hashed_password, new_sheet_id):
    """Appends the new user to the Master Google Sheet database."""
    master_id = st.secrets["master_db_sheet_id"]
    client = get_gspread_client()
    
    sh = client.open_by_key(master_id)
    worksheet = sh.worksheet("Users")
    
    # Add a new row to the bottom of the "Users" tab
    new_row = [username, hashed_password, new_sheet_id]
    worksheet.append_row(new_row)
