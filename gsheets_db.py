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
