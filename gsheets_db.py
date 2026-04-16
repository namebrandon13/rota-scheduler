import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import time

def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_user_database():
    """Reads the Users tab and returns full user profiles."""
    master_id = st.secrets["master_db_sheet_id"]
    client = get_gspread_client()
    try:
        sh = client.open_by_key(master_id)
        ws = sh.worksheet("Users")
        # Ensure we get a clean dataframe
        df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how='all')
        
        users = {}
        for _, row in df.iterrows():
            # Convert the whole row to a dictionary
            user_info = row.to_dict()
            # Use Username as the key, and store all columns as the value
            users[str(row['Username'])] = user_info
            
        return users
    except Exception as e:
        st.error(f"Database Error: {e}")
        return {}

def register_user_in_db(username, hashed_password):
    """Adds a new user to the Users tab."""
    master_id = st.secrets["master_db_sheet_id"]
    client = get_gspread_client()
    sh = client.open_by_key(master_id)
    try:
        ws = sh.worksheet("Users")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet("Users", 100, 2)
        ws.append_row(["Username", "Password"])
    ws.append_row([username, hashed_password])

def get_user_data(sheet_id, tab_name, username):
    """Fetches ONLY the data belonging to the logged-in user."""
    client = get_gspread_client()
    for attempt in range(4):
        try:
            sh = client.open_by_key(sheet_id)
            ws = sh.worksheet(tab_name)
            df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how='all').dropna(axis=1, how='all')
            
            if 'Username' in df.columns:
                # Filter for this specific user
                user_df = df[df['Username'] == username].copy()
                # Hide the Username column from the UI
                return user_df.drop(columns=['Username'])
            else:
                # If the tab is totally empty, return empty dataframe
                return pd.DataFrame()
                
        except gspread.exceptions.APIError as e:
            if '429' in str(e) or 'Quota' in str(e):
                time.sleep(2 ** attempt)
            else:
                return pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def write_user_data(sheet_id, tab_name, username, user_df):
    """Updates ONLY the logged-in user's data, preserving everyone else's."""
    client = get_gspread_client()
    sh = client.open_by_key(sheet_id)
    
    try:
        ws = sh.worksheet(tab_name)
        all_df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how='all').dropna(axis=1, how='all')
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=20)
        all_df = pd.DataFrame()

    # 1. Remove the old data for the CURRENT user only
    if not all_df.empty and 'Username' in all_df.columns:
        all_df = all_df[all_df['Username'] != username]
    elif not all_df.empty:
        all_df = pd.DataFrame() # Safety wipe if structure is broken

    # 2. Add the "Name Tag" to the new data coming from the UI
    df_to_save = user_df.copy()
    if not df_to_save.empty:
        df_to_save['Username'] = username

    # 3. Combine everyone else's data with this user's updated data
    if not all_df.empty:
        final_df = pd.concat([all_df, df_to_save], ignore_index=True)
    else:
        final_df = df_to_save

    # 4. Save the combined master list back to Google
    ws.clear()
    set_with_dataframe(ws, final_df)
