import requests
import pandas as pd
from datetime import datetime, timedelta, date
import re
from bs4 import BeautifulSoup
import math
import json
import os

# ==============================================================================
#                               CONFIGURATION
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_EXCEL_FILE = os.path.join(BASE_DIR, 'Book(Employees)_01.xlsx')
EVENTS_OUTPUT_FILE = os.path.join(BASE_DIR, 'EventsData.xlsx')

# FILTERING
MIN_IMPACT_THRESHOLD = 1 

# TICKETMASTER CONFIG
TM_API_KEY = 'KsyBBAXwMHcPTRvtiCpCu6ctsArJNGx3'  
BUSINESS_LAT = 51.54585038269431   
BUSINESS_LONG = -0.10337318231768661
SEARCH_CITY_SLUG = "united-kingdom--london"
RADIUS_MILES = 2

# DIGITAL CALENDAR FEEDS
CALENDAR_FEEDS = [
    {'name': 'Arsenal', 'url': 'https://ics.fixtur.es/v2/arsenal.ics', 'home_venue': 'Emirates Stadium'}
]

# VENUE DATABASE
VENUE_DB = {
    'Emirates Stadium': {'capacity': 60704, 'lat': 51.5549, 'lon': -0.1084},
    'The O2':           {'capacity': 20000, 'lat': 51.5030, 'lon': 0.0032},
    'Wembley Stadium':  {'capacity': 90000, 'lat': 51.5560, 'lon': -0.2795},
    'DEFAULT':          {'capacity': 500,   'lat': 0.0,     'lon': 0.0}
}

# ==============================================================================
#                               HELPER FUNCTIONS
# ==============================================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    if lat2 == 0.0 or lat2 is None: return 0.0
    R = 3958.8 
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def get_event_details(url):
    """Visits a specific Eventbrite page to find the JSON-LD Schema."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None, None, None

        soup = BeautifulSoup(response.content, 'html.parser')
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') in ['Event', 'MusicEvent']:
                    location = data.get('location', {})
                    venue_name = location.get('name', 'Unknown Venue')
                    geo = location.get('geo', {})
                    lat = float(geo.get('latitude', 0.0))
                    lon = float(geo.get('longitude', 0.0))
                    if lat != 0.0:
                        return lat, lon, venue_name
            except:
                continue
    except:
        pass
    return None, None, None


def calculate_weighted_impact(row):
    footfall = row['Est. Footfall']
    dist = row['Distance (Miles)']
    if footfall > 20000: base = 10
    elif footfall > 5000: base = 8
    else: base = 4
    if dist < 1.0: decay = 1.0
    elif dist < 3.0: decay = 0.5
    else: decay = 0.2
    return max(1, int(base * decay))


def load_existing_events():
    """Load existing events from EventsData.xlsx"""
    if not os.path.exists(EVENTS_OUTPUT_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_excel(EVENTS_OUTPUT_FILE)
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except:
        return pd.DataFrame()


def save_events(df_new, merge=True):
    """Save events, optionally merging with existing data"""
    if merge:
        df_existing = load_existing_events()
        if not df_existing.empty:
            # Convert dates for comparison
            df_new['Date'] = pd.to_datetime(df_new['Date']).dt.date
            
            # Remove duplicates from existing that match new data (by Date + Event Name)
            if not df_new.empty:
                merge_keys = df_new[['Date', 'Event Name']].apply(tuple, axis=1).tolist()
                df_existing = df_existing[
                    ~df_existing[['Date', 'Event Name']].apply(tuple, axis=1).isin(merge_keys)
                ]
            
            # Combine
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined = df_combined.drop_duplicates(subset=['Date', 'Event Name'])
            df_combined = df_combined.sort_values('Date')
            df_combined.to_excel(EVENTS_OUTPUT_FILE, index=False)
            return df_combined
    
    # Just save new data
    df_new.to_excel(EVENTS_OUTPUT_FILE, index=False)
    return df_new


# ==============================================================================
#                               DATA SOURCES
# ==============================================================================

def scrape_eventbrite(start_date, end_date):
    print(f"  > Scraping Eventbrite ({start_date} to {end_date})...")
    events_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    seen_links = set()
    
    try:
        url = f"https://www.eventbrite.co.uk/d/{SEARCH_CITY_SLUG}/events/?start_date={start_date}&end_date={end_date}&page=1"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200: 
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.find_all('a', href=True)
        
        count = 0
        max_scan = 10
        
        for link in links:
            href = link['href']
            if 'eventbrite.co.uk/e/' in href:
                clean_url = href.split('?')[0]
                
                if clean_url not in seen_links:
                    seen_links.add(clean_url)
                    text = link.text.strip()
                    if len(text) < 5: continue
                    
                    real_lat, real_lon, real_venue = get_event_details(clean_url)
                    
                    if real_lat and real_lon:
                        lat_val, lon_val, venue_val = real_lat, real_lon, real_venue
                    else:
                        lat_val, lon_val = BUSINESS_LAT, BUSINESS_LONG
                        venue_val = "Unknown (Check Link)"

                    events_list.append({
                        'Date': start_date,
                        'Start Time': "19:00", 
                        'End Time': "22:00",
                        'Duration': "3.0h", 
                        'Event Name': f"[EB] {text[:30]}...",
                        'Venue': venue_val, 
                        'Est. Footfall': 300, 
                        'Lat': lat_val, 
                        'Lon': lon_val, 
                        'Source': 'Eventbrite'
                    })
                    
                    count += 1
                    if count >= max_scan: break
                    
    except Exception as e: 
        print(f"    [!] Error scraping Eventbrite: {e}")
        
    return events_list


def get_ticketmaster_events(start_date, end_date):
    print(f"  > Pinging Ticketmaster ({start_date} to {end_date})...")
    events_list = []
    try:
        start_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_obj = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        
        api_start = start_obj.strftime('%Y-%m-%dT00:00:00Z')
        api_end = end_obj.strftime('%Y-%m-%dT23:59:59Z')
        
        url = "https://app.ticketmaster.com/discovery/v2/events.json"
        params = {
            'apikey': TM_API_KEY, 
            'geoPoint': f"{BUSINESS_LAT},{BUSINESS_LONG}",
            'radius': RADIUS_MILES, 
            'unit': 'miles',
            'startDateTime': api_start, 
            'endDateTime': api_end, 
            'size': 50
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200: return []
        data = response.json()
        
        if '_embedded' in data:
            for ev in data['_embedded']['events']:
                try:
                    name = ev.get('name', 'Unknown')
                    if "Season Ticket" in name: continue 
                    ev_date = ev['dates']['start'].get('localDate', '')
                    time_str = ev['dates']['start'].get('localTime', '19:00')[:5]
                    
                    venue_data = ev.get('_embedded', {}).get('venues', [{}])[0]
                    venue = venue_data.get('name', 'Unknown')
                    try:
                        v_lat = float(venue_data['location']['latitude'])
                        v_lon = float(venue_data['location']['longitude'])
                    except: 
                        v_lat, v_lon = BUSINESS_LAT, BUSINESS_LONG

                    capacity = VENUE_DB.get(venue, {}).get('capacity', 1000)
                    events_list.append({
                        'Date': ev_date, 
                        'Start Time': time_str, 
                        'End Time': '22:00',
                        'Duration': '3.0h', 
                        'Event Name': name, 
                        'Venue': venue,
                        'Est. Footfall': int(capacity * 0.9), 
                        'Lat': v_lat, 
                        'Lon': v_lon, 
                        'Source': 'TM API'
                    })
                except: 
                    continue
    except Exception as e:
        print(f"    [!] Error with Ticketmaster: {e}")
    return events_list


def parse_ics_feed(start_date, end_date):
    print(f"  > Reading Digital Calendars (ICS) ({start_date} to {end_date})...")
    matches = []
    for feed in CALENDAR_FEEDS:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(feed['url'], headers=headers, timeout=10)
            events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', response.text, re.DOTALL)
            for ev in events:
                summary_search = re.search(r'SUMMARY:(.*)', ev)
                start_search = re.search(r'DTSTART.*:(\d{8}T\d{6})', ev) 
                if not start_search or not summary_search: continue
                
                raw_start = start_search.group(1)
                dt_start = datetime.strptime(raw_start, '%Y%m%dT%H%M%S')
                date_str = dt_start.strftime('%Y-%m-%d')
                time_str = dt_start.strftime('%H:%M')
                
                if not (start_date <= date_str <= end_date): continue
                
                summary = summary_search.group(1).strip()
                if " - " in summary: 
                    home_team = summary.split(" - ")[0].strip()
                elif " vs " in summary: 
                    home_team = summary.split(" vs ")[0].strip()
                else: 
                    home_team = summary

                if "Arsenal" in home_team:
                    matches.append({
                        'Date': date_str, 
                        'Start Time': time_str, 
                        'End Time': (dt_start + timedelta(hours=2)).strftime('%H:%M'),
                        'Duration': '2.0h', 
                        'Event Name': summary, 
                        'Venue': 'Emirates Stadium',
                        'Est. Footfall': 60704, 
                        'Lat': 51.5549, 
                        'Lon': -0.1084, 
                        'Source': 'ICS Feed'
                    })
        except Exception as e:
            print(f"    [!] Error with ICS feed: {e}")
            continue
    return matches


# ==============================================================================
#                               MAIN SCAN FUNCTION
# ==============================================================================

def run_event_scan(start_date=None, end_date=None, merge=True):
    """
    Run event scan for a specific date range.
    
    Args:
        start_date: Start date string (YYYY-MM-DD) or None for today
        end_date: End date string (YYYY-MM-DD) or None for start + 30 days
        merge: If True, merge with existing events. If False, replace.
    
    Returns:
        DataFrame of found events
    """
    print("--- STARTING EVENT SCAN ---")
    
    # Set default dates
    today = date.today()
    if start_date is None:
        start_date = today.strftime('%Y-%m-%d')
    if end_date is None:
        end_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Ensure we don't scan past dates
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    if start_dt < today:
        start_date = today.strftime('%Y-%m-%d')
    
    print(f"  Scan Range: {start_date} to {end_date}")
    
    # Fetch from all sources
    tm = get_ticketmaster_events(start_date, end_date)
    ics = parse_ics_feed(start_date, end_date)
    eb = scrape_eventbrite(start_date, end_date)
    
    all_events = tm + ics + eb
    
    if not all_events:
        print("  No events found.")
        return pd.DataFrame()

    df = pd.DataFrame(all_events)
    
    # Calculate distance
    df['Distance (Miles)'] = df.apply(
        lambda x: haversine_distance(BUSINESS_LAT, BUSINESS_LONG, x['Lat'], x['Lon']), 
        axis=1
    )
    
    # Filter by radius
    df = df[df['Distance (Miles)'] <= RADIUS_MILES]
    
    # Calculate impact
    df['Impact Score'] = df.apply(calculate_weighted_impact, axis=1)
    
    # Filter by minimum impact
    initial_count = len(df)
    df = df[df['Impact Score'] >= MIN_IMPACT_THRESHOLD]
    dropped_count = initial_count - len(df)
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['Date', 'Event Name'])
    
    # Save (merge or replace)
    if not df.empty:
        save_events(df, merge=merge)
    
    print(f"\n  Found {len(df)} significant events (>={MIN_IMPACT_THRESHOLD}/10 impact).")
    if dropped_count > 0: 
        print(f"  Filtered out {dropped_count} low-impact events.")
    
    return df


def scan_week(week_start_date):
    """
    Scan events for a specific week.
    
    Args:
        week_start_date: date object or string (YYYY-MM-DD) for Monday of the week
    
    Returns:
        DataFrame of found events for that week
    """
    if isinstance(week_start_date, str):
        ws = datetime.strptime(week_start_date, '%Y-%m-%d').date()
    else:
        ws = week_start_date
    
    we = ws + timedelta(days=6)
    
    return run_event_scan(
        start_date=ws.strftime('%Y-%m-%d'),
        end_date=we.strftime('%Y-%m-%d'),
        merge=True
    )


def scan_live(days_ahead=30):
    """
    Scan from today + specified days ahead.
    
    Args:
        days_ahead: Number of days to scan ahead from today
    
    Returns:
        DataFrame of found events
    """
    today = date.today()
    end = today + timedelta(days=days_ahead)
    
    return run_event_scan(
        start_date=today.strftime('%Y-%m-%d'),
        end_date=end.strftime('%Y-%m-%d'),
        merge=True
    )


# ==============================================================================
#                               STANDALONE EXECUTION
# ==============================================================================

if __name__ == "__main__":
    # When run directly, scan today + 30 days
    scan_live(30)
