import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe

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

def write_sheet_data(sheet_id, tab_name, df):
    """Writes a DataFrame to a specific tab, replacing existing data. Creates tab if missing."""
    client = get_gspread_client()
    spreadsheet = client.open_by_key(sheet_id)
    
    try:
        worksheet = spreadsheet.worksheet(tab_name)
        worksheet.clear() # Clear existing data
    except gspread.exceptions.WorksheetNotFound:
        # Create it if it doesn't exist
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows="100", cols="20")
    
    # Write the new dataframe
    set_with_dataframe(worksheet, df, resize=True)
