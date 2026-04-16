import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import gspread
from gspread_dataframe import set_with_dataframe

def get_gspread_client():
    """Authenticates and returns the gspread client using Streamlit secrets."""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    # Convert Streamlit secrets to a standard dictionary
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # FIX: Use from_json_keyfile_dict instead of from_service_account_info
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    return gspread.authorize(creds)

def get_sheet_data(sheet_id, tab_name):
    """Fetches a specific tab as a pandas DataFrame."""
    client = get_gspread_client()
    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        # Fetch and clean empty trailing rows/cols
        df = get_as_dataframe(worksheet, evaluate_formulas=True)
        df = df.dropna(how='all').dropna(axis=1, how='all')
        return df
    except gspread.exceptions.WorksheetNotFound:
        print(f"Warning: Tab '{tab_name}' not found.")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error reading {tab_name}: {e}")
        return pd.DataFrame()

def write_sheet_data(sheet_id, worksheet_name, df):
    """
    Writes a DataFrame to a Google Sheet. 
    If the tab (worksheet_name) doesn't exist, it creates a new one.
    """
    try:
        client = get_gspread_client()
        sh = client.open_by_key(sheet_id)
        
        # 1. Try to find the existing tab
        try:
            worksheet = sh.worksheet(worksheet_name)
            print(f"Tab '{worksheet_name}' found. Overwriting...")
        except gspread.exceptions.WorksheetNotFound:
            # 2. If it doesn't exist, CREATE IT
            print(f"Tab '{worksheet_name}' not found. Creating a new tab...")
            
            # Make sure we create enough rows/cols for the dataframe
            num_rows = str(max(1000, len(df) + 100))
            num_cols = str(max(26, len(df.columns) + 5))
            
            worksheet = sh.add_worksheet(title=worksheet_name, rows=num_rows, cols=num_cols)
        
        # 3. Clear old data and paste the new data
        worksheet.clear()
        set_with_dataframe(worksheet, df)
        print(f"Successfully saved to Google Sheets tab: {worksheet_name}")
        
    except Exception as e:
        print(f"CRITICAL WRITE ERROR: {e}")
        # This will force the error to show up in your Streamlit app!
        st.error(f"Google Sheets Upload Failed: {e}")
        raise e
