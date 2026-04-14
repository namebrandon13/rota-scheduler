import requests
import pandas as pd
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup
import math
import json
import os

# ==============================================================================
#                               CONFIGURATION
# ==============================================================================

INPUT_EXCEL_FILE = 'Book(Employees)_01.xlsx'
# 1. DATE RANGE
SEARCH_START_DATE = "2025-12-01" 
SEARCH_END_DATE   = "2026-01-31"

# 2. FILTERING (NEW)
# Minimum Impact Score (1-10) required to be saved.
# 1-3: Low (Pub/Small Club)
# 4-6: Medium (Theater/Large Club)
# 7-8: High (Arena)
# 9-10: Critical (Stadium)
MIN_IMPACT_THRESHOLD = 1 

# 3. TICKETMASTER CONFIG
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

def get_date_range_from_excel():
    """Reads the Excel file to find start and end dates."""
    print(f"  > Reading dates from {INPUT_EXCEL_FILE}...")
    try:
        if not os.path.exists(INPUT_EXCEL_FILE):
            print("    [Error] Excel file not found. Using defaults.")
            return "2025-12-01", "2026-01-31"
            
        df = pd.read_excel(INPUT_EXCEL_FILE, sheet_name="Shift Templates")
        df.columns = df.columns.str.strip()
        
        if 'Date' not in df.columns:
            print("    [Error] 'Date' column not found.")
            return "2025-12-01", "2026-01-31"
            
        dates = pd.to_datetime(df['Date']).dropna()
        if dates.empty:
            return "2025-12-01", "2026-01-31"
            
        start_date = dates.min().strftime('%Y-%m-%d')
        end_date = dates.max().strftime('%Y-%m-%d')
        print(f"    [Success] Detected Range: {start_date} to {end_date}")
        return start_date, end_date
        
    except Exception as e:
        print(f"    [Error] Reading Excel failed: {e}")
        return "2025-12-01", "2026-01-31"

# Global Start/End (Will be set at runtime)
SEARCH_START_DATE, SEARCH_END_DATE = "2025-12-01", "2026-01-31"

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
    """
    Visits a specific Eventbrite page to find the JSON-LD Schema 
    which contains the exact Latitude and Longitude.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200: return None, None, None

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Eventbrite stores data in <script type="application/ld+json">
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                # Look for 'Event' type schema
                if data.get('@type') == 'Event' or data.get('@type') == 'MusicEvent':
                    location = data.get('location', {})
                    
                    # Extract Venue Name
                    venue_name = location.get('name', 'Unknown Venue')
                    
                    # Extract Coordinates
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

def scrape_eventbrite():
    print(f"  > Scraping Eventbrite ({SEARCH_START_DATE} to {SEARCH_END_DATE})...")
    events_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    # We use a set to avoid processing the same event twice
    seen_links = set()
    
    try:
        # Search URL
        url = f"https://www.eventbrite.co.uk/d/{SEARCH_CITY_SLUG}/events/?start_date={SEARCH_START_DATE}&end_date={SEARCH_END_DATE}&page=1"
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200: 
            print("    [!] Could not connect to Eventbrite search page.")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        # Find all links that look like events
        links = soup.find_all('a', href=True)
        
        count = 0
        max_scan = 10 # Limit to 10 events to keep speed reasonable
        
        for link in links:
            href = link['href']
            # Basic cleanup of the URL
            if 'eventbrite.co.uk/e/' in href:
                # Remove query parameters for cleaner ID
                clean_url = href.split('?')[0]
                
                if clean_url not in seen_links:
                    seen_links.add(clean_url)
                    
                    # Get the title from the search card text
                    text = link.text.strip()
                    if len(text) < 5: continue # Skip empty links
                    
                    print(f"    -> Deep scanning: {text[:20]}...")
                    
                    # --- DEEP SCAN: Visit the page to get real Lat/Lon ---
                    real_lat, real_lon, real_venue = get_event_details(clean_url)
                    
                    # If we found coordinates, use them. If not, skip or use defaults.
                    if real_lat and real_lon:
                        lat_val = real_lat
                        lon_val = real_lon
                        venue_val = real_venue
                    else:
                        # Fallback (Only if Deep Scan fails)
                        lat_val = BUSINESS_LAT
                        lon_val = BUSINESS_LONG
                        venue_val = "Unknown (Check Link)"

                    events_list.append({
                        'Date': SEARCH_START_DATE, # Note: You might want to scrape the real date from JSON too
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
        pass
        
    return events_list

def get_ticketmaster_events():
    print(f"  > Pinging Ticketmaster...")
    events_list = []
    try:
        start_obj = datetime.strptime(SEARCH_START_DATE, "%Y-%m-%d")
        end_obj = datetime.strptime(SEARCH_END_DATE, "%Y-%m-%d")
        # Add 1 day to end to ensure coverage
        end_obj = end_obj + timedelta(days=1)
        
        api_start = start_obj.strftime('%Y-%m-%dT00:00:00Z')
        api_end   = end_obj.strftime('%Y-%m-%dT23:59:59Z')
        
        url = "https://app.ticketmaster.com/discovery/v2/events.json"
        params = {
            'apikey': TM_API_KEY, 'geoPoint': f"{BUSINESS_LAT},{BUSINESS_LONG}",
            'radius': RADIUS_MILES, 'unit': 'miles',
            'startDateTime': api_start, 'endDateTime': api_end, 'size': 50
        }
        response = requests.get(url, params=params)
        if response.status_code != 200: return []
        data = response.json()
        
        if '_embedded' in data:
            for ev in data['_embedded']['events']:
                try:
                    name = ev.get('name', 'Unknown')
                    if "Season Ticket" in name: continue 
                    date = ev['dates']['start'].get('localDate', '')
                    time_str = ev['dates']['start'].get('localTime', '19:00')[:5]
                    
                    venue_data = ev.get('_embedded', {}).get('venues', [{}])[0]
                    venue = venue_data.get('name', 'Unknown')
                    try:
                        v_lat = float(venue_data['location']['latitude'])
                        v_lon = float(venue_data['location']['longitude'])
                    except: v_lat, v_lon = BUSINESS_LAT, BUSINESS_LONG

                    capacity = VENUE_DB.get(venue, {}).get('capacity', 1000)
                    events_list.append({
                        'Date': date, 'Start Time': time_str, 'End Time': '22:00',
                        'Duration': '3.0h', 'Event Name': name, 'Venue': venue,
                        'Est. Footfall': int(capacity * 0.9), 'Lat': v_lat, 'Lon': v_lon, 'Source': 'TM API'
                    })
                except: continue
    except: pass
    return events_list

def parse_ics_feed():
    print("  > Reading Digital Calendars (ICS)...")
    matches = []
    for feed in CALENDAR_FEEDS:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(feed['url'], headers=headers)
            events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', response.text, re.DOTALL)
            for ev in events:
                summary_search = re.search(r'SUMMARY:(.*)', ev)
                start_search = re.search(r'DTSTART.*:(\d{8}T\d{6})', ev) 
                if not start_search or not summary_search: continue
                
                raw_start = start_search.group(1)
                dt_start = datetime.strptime(raw_start, '%Y%m%dT%H%M%S')
                date_str = dt_start.strftime('%Y-%m-%d')
                time_str = dt_start.strftime('%H:%M')
                
                if not (SEARCH_START_DATE <= date_str <= SEARCH_END_DATE): continue
                
                summary = summary_search.group(1).strip()
                if " - " in summary: home_team = summary.split(" - ")[0].strip()
                elif " vs " in summary: home_team = summary.split(" vs ")[0].strip()
                else: home_team = summary

                if "Arsenal" in home_team:
                    matches.append({
                        'Date': date_str, 'Start Time': time_str, 
                        'End Time': (dt_start+timedelta(hours=2)).strftime('%H:%M'),
                        'Duration': '2.0h', 'Event Name': summary, 'Venue': 'Emirates Stadium',
                        'Est. Footfall': 60704, 'Lat': 51.5549, 'Lon': -0.1084, 'Source': 'ICS Feed'
                    })
        except: continue
    return matches

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

def run_event_scan():
    global SEARCH_START_DATE, SEARCH_END_DATE
    print("--- STARTING EVENT SCAN ---")
    
    # 1. Update Dates Dynamically
    SEARCH_START_DATE, SEARCH_END_DATE = get_date_range_from_excel()
    
    tm = get_ticketmaster_events()
    ics = parse_ics_feed()
    eb = scrape_eventbrite()
    
    all_events = tm + ics + eb
    if not all_events:
        print("No events found.")
        return

    df = pd.DataFrame(all_events)
    df['Distance (Miles)'] = df.apply(lambda x: haversine_distance(BUSINESS_LAT, BUSINESS_LONG, x['Lat'], x['Lon']), axis=1)
    
    # 1. Filter by Radius
    df = df[df['Distance (Miles)'] <= RADIUS_MILES]
    
    # 2. Calculate Impact
    df['Impact Score'] = df.apply(calculate_weighted_impact, axis=1)
    
    # 3. Filter by Minimum Impact
    initial_count = len(df)
    df = df[df['Impact Score'] >= MIN_IMPACT_THRESHOLD]
    dropped_count = initial_count - len(df)
    
    df = df.drop_duplicates(subset=['Date', 'Event Name'])
    
    output_file = 'EventsData.xlsx'
    df.to_excel(output_file, index=False)
    
    print(f"\nFound {len(df)} significant events (>{MIN_IMPACT_THRESHOLD}/10 impact).")
    if dropped_count > 0: print(f"Filtered out {dropped_count} low-impact events.")
    if not df.empty:
        print(df[['Date', 'Start Time', 'Event Name', 'Impact Score']].head().to_string())
    print(f"Saved to {output_file}")

if __name__ == "__main__":
    run_event_scan()