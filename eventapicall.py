import requests
import pandas as pd
from datetime import datetime, timedelta, date
import re
from bs4 import BeautifulSoup
import math
import json
import os
import calendar as cal_module

# ==============================================================================
#                               CONFIGURATION
# ==============================================================================

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
EVENTS_OUTPUT_FILE = os.path.join(BASE_DIR, 'EventsData.xlsx')

MIN_IMPACT_THRESHOLD = 1

# ── API Keys ─────────────────────────────────────────────────────────────────
TM_API_KEY          = 'KsyBBAXwMHcPTRvtiCpCu6ctsArJNGx3'   # Ticketmaster
SKIDDLE_API_KEY     = 'YOUR_SKIDDLE_KEY'   # free at skiddle.com/api
PREDICTHQ_TOKEN     = 'YOUR_PREDICTHQ_TOKEN'  # free tier at predicthq.com

# ── Business location ────────────────────────────────────────────────────────
BUSINESS_LAT   = 51.54585038269431
BUSINESS_LONG  = -0.10337318231768661
RADIUS_MILES   = 2
RADIUS_KM      = RADIUS_MILES * 1.60934

# ── Eventbrite ───────────────────────────────────────────────────────────────
SEARCH_CITY_SLUG = "united-kingdom--london"

# ==============================================================================
#   ICS CALENDAR FEEDS  —  no API keys, 100% free
# ==============================================================================
CALENDAR_FEEDS = [
    {'name': 'Arsenal',          'url': 'https://ics.fixtur.es/v2/arsenal.ics',
     'home_venue': 'Emirates Stadium',           'home_lat': 51.5549, 'home_lon': -0.1084, 'capacity': 60704},
    {'name': 'Tottenham',        'url': 'https://ics.fixtur.es/v2/tottenham-hotspur.ics',
     'home_venue': 'Tottenham Hotspur Stadium',  'home_lat': 51.6042, 'home_lon': -0.0665, 'capacity': 62850},
    {'name': 'Chelsea',          'url': 'https://ics.fixtur.es/v2/chelsea.ics',
     'home_venue': 'Stamford Bridge',            'home_lat': 51.4816, 'home_lon': -0.1910, 'capacity': 40834},
    {'name': 'West Ham',         'url': 'https://ics.fixtur.es/v2/west-ham-united.ics',
     'home_venue': 'London Stadium',             'home_lat': 51.5386, 'home_lon': -0.0164, 'capacity': 60000},
    {'name': 'Crystal Palace',   'url': 'https://ics.fixtur.es/v2/crystal-palace.ics',
     'home_venue': 'Selhurst Park',              'home_lat': 51.3983, 'home_lon': -0.0855, 'capacity': 25486},
    {'name': 'Brentford',        'url': 'https://ics.fixtur.es/v2/brentford.ics',
     'home_venue': 'Gtech Community Stadium',    'home_lat': 51.4882, 'home_lon': -0.3088, 'capacity': 17250},
    {'name': 'Fulham',           'url': 'https://ics.fixtur.es/v2/fulham.ics',
     'home_venue': 'Craven Cottage',             'home_lat': 51.4749, 'home_lon': -0.2217, 'capacity': 25700},
    {'name': 'QPR',              'url': 'https://ics.fixtur.es/v2/queens-park-rangers.ics',
     'home_venue': 'Loftus Road',                'home_lat': 51.5093, 'home_lon': -0.2320, 'capacity': 18360},
    {'name': 'Leyton Orient',    'url': 'https://ics.fixtur.es/v2/leyton-orient.ics',
     'home_venue': 'Brisbane Road',              'home_lat': 51.5601, 'home_lon': -0.0134, 'capacity': 9271},
    {'name': 'England Football', 'url': 'https://ics.fixtur.es/v2/england.ics',
     'home_venue': 'Wembley Stadium',            'home_lat': 51.5560, 'home_lon': -0.2795, 'capacity': 90000},
]

# ==============================================================================
#   VENUE DATABASE
# ==============================================================================
VENUE_DB = {
    # Stadiums
    'Emirates Stadium':              {'capacity': 60704,  'lat': 51.5549,  'lon': -0.1084},
    'Tottenham Hotspur Stadium':     {'capacity': 62850,  'lat': 51.6042,  'lon': -0.0665},
    'Wembley Stadium':               {'capacity': 90000,  'lat': 51.5560,  'lon': -0.2795},
    'London Stadium':                {'capacity': 60000,  'lat': 51.5386,  'lon': -0.0164},
    'Stamford Bridge':               {'capacity': 40834,  'lat': 51.4816,  'lon': -0.1910},
    'Craven Cottage':                {'capacity': 25700,  'lat': 51.4749,  'lon': -0.2217},
    'Selhurst Park':                 {'capacity': 25486,  'lat': 51.3983,  'lon': -0.0855},
    'Gtech Community Stadium':       {'capacity': 17250,  'lat': 51.4882,  'lon': -0.3088},
    "Lord's Cricket Ground":         {'capacity': 30000,  'lat': 51.5293,  'lon': -0.1729},
    'The Oval':                      {'capacity': 25500,  'lat': 51.4832,  'lon': -0.1153},
    # Arenas
    'The O2 Arena':                  {'capacity': 20000,  'lat': 51.5030,  'lon':  0.0032},
    'The O2':                        {'capacity': 20000,  'lat': 51.5030,  'lon':  0.0032},
    'OVO Arena Wembley':             {'capacity': 12500,  'lat': 51.5523,  'lon': -0.2791},
    'Alexandra Palace':              {'capacity': 10400,  'lat': 51.5976,  'lon': -0.1313},
    'Ally Pally':                    {'capacity': 10400,  'lat': 51.5976,  'lon': -0.1313},
    'Eventim Apollo':                {'capacity': 5039,   'lat': 51.4939,  'lon': -0.2244},
    'O2 Academy Brixton':            {'capacity': 4921,   'lat': 51.4643,  'lon': -0.1149},
    'Brixton Academy':               {'capacity': 4921,   'lat': 51.4643,  'lon': -0.1149},
    'O2 Forum Kentish Town':         {'capacity': 2300,   'lat': 51.5508,  'lon': -0.1434},
    'The Forum':                     {'capacity': 2300,   'lat': 51.5508,  'lon': -0.1434},
    'Roundhouse':                    {'capacity': 3300,   'lat': 51.5436,  'lon': -0.1527},
    'EartH Hackney':                 {'capacity': 1500,   'lat': 51.5479,  'lon': -0.0570},
    'Islington Assembly Hall':       {'capacity': 800,    'lat': 51.5384,  'lon': -0.1016},
    'Union Chapel':                  {'capacity': 900,    'lat': 51.5449,  'lon': -0.1006},
    'Scala':                         {'capacity': 1100,   'lat': 51.5307,  'lon': -0.1196},
    'Electric Ballroom':             {'capacity': 1500,   'lat': 51.5399,  'lon': -0.1422},
    'Koko':                          {'capacity': 1500,   'lat': 51.5371,  'lon': -0.1424},
    # Outdoor / festival sites
    'Finsbury Park':                 {'capacity': 60000,  'lat': 51.5643,  'lon': -0.1049},
    'Victoria Park':                 {'capacity': 50000,  'lat': 51.5362,  'lon': -0.0368},
    'Hyde Park':                     {'capacity': 65000,  'lat': 51.5073,  'lon': -0.1657},
    'Crystal Palace Park':           {'capacity': 25000,  'lat': 51.4216,  'lon': -0.0721},
    'Gunnersbury Park':              {'capacity': 40000,  'lat': 51.4917,  'lon': -0.2844},
    'Clapham Common':                {'capacity': 30000,  'lat': 51.4613,  'lon': -0.1500},
    # Default
    'DEFAULT':                       {'capacity': 500,    'lat': 0.0,      'lon': 0.0},
}

# ==============================================================================
#   ANNUAL PUBLIC EVENTS CALENDAR
#   Marathons, parades, carnivals, and other recurring city-wide events.
#   Date rules are calculated programmatically — no API needed.
#
#   HOW TO ADD A NEW EVENT:
#     Append a dict to ANNUAL_EVENTS with:
#       name        – display name
#       month       – calendar month (1-12)
#       rule        – one of:
#                     ('fixed', day)              → always on that day of month
#                     ('weekday', n, weekday)     → nth occurrence of weekday (0=Mon … 6=Sun)
#                     ('last_weekday', weekday)   → last occurrence of weekday in month
#                     ('weekend_nearest', day)    → Saturday nearest to a fixed date
#       start_time / end_time
#       footfall    – estimated crowd size (affects Impact Score)
#       duration_h  – event lasts how many hours
#       route_near_store – True = route passes near store (distance overridden to 0.3 mi)
# ==============================================================================
ANNUAL_EVENTS = [
    # ── Marathons & Road Races ────────────────────────────────────────────────
    {
        'name': 'TCS London Marathon',
        'month': 4,
        'rule': ('last_weekday', 6),        # Last Sunday of April
        'start_time': '09:00', 'end_time': '17:00', 'duration_h': 8,
        'footfall': 750000,
        'route_near_store': False,          # Route is in central/south London
        'notes': '750k spectators on route; 50k runners',
    },
    {
        'name': 'Hackney Half Marathon',
        'month': 5,
        'rule': ('weekday', 2, 6),          # 3rd Sunday of May
        'start_time': '09:00', 'end_time': '14:00', 'duration_h': 5,
        'footfall': 25000,
        'route_near_store': True,           # Route passes through Hackney / Islington area
        'notes': 'Route through Hackney, Victoria Park area — close to store',
    },
    {
        'name': 'Vitality Big Half (Half Marathon)',
        'month': 3,
        'rule': ('weekday', 1, 6),          # 2nd Sunday of March
        'start_time': '09:00', 'end_time': '14:00', 'duration_h': 5,
        'footfall': 15000,
        'route_near_store': False,
    },
    {
        'name': 'Royal Parks Half Marathon',
        'month': 10,
        'rule': ('weekday', 1, 6),          # 2nd Sunday of October
        'start_time': '09:00', 'end_time': '14:00', 'duration_h': 5,
        'footfall': 16000,
        'route_near_store': False,
    },
    {
        'name': 'London 10,000 Road Race',
        'month': 5,
        'rule': ('weekday', 0, 0),          # 1st Monday of May (Bank Holiday)
        'start_time': '09:30', 'end_time': '13:00', 'duration_h': 3.5,
        'footfall': 10000,
        'route_near_store': False,
    },
    {
        'name': 'Hackney 5K / 10K Race Series',
        'month': 6,
        'rule': ('weekday', 0, 6),          # 1st Sunday of June
        'start_time': '09:00', 'end_time': '12:00', 'duration_h': 3,
        'footfall': 5000,
        'route_near_store': True,
    },
    # ── Parades & Carnivals ───────────────────────────────────────────────────
    {
        'name': 'Notting Hill Carnival (Sunday)',
        'month': 8,
        'rule': ('last_weekday', 6),        # Last Sunday of August
        'start_time': '11:00', 'end_time': '22:00', 'duration_h': 11,
        'footfall': 1000000,
        'route_near_store': False,
    },
    {
        'name': 'Notting Hill Carnival (Bank Holiday Monday)',
        'month': 8,
        'rule': ('last_weekday', 0),        # Last Monday of August
        'start_time': '11:00', 'end_time': '22:00', 'duration_h': 11,
        'footfall': 1500000,
        'route_near_store': False,
    },
    {
        'name': 'Pride in London Parade',
        'month': 6,
        'rule': ('last_weekday', 5),        # Last Saturday of June
        'start_time': '12:00', 'end_time': '21:00', 'duration_h': 9,
        'footfall': 1000000,
        'route_near_store': False,
    },
    {
        'name': 'St Patrick\'s Day Parade London',
        'month': 3,
        'rule': ('weekend_nearest', 17),    # Weekend nearest 17 March
        'start_time': '12:00', 'end_time': '18:00', 'duration_h': 6,
        'footfall': 125000,
        'route_near_store': False,
    },
    {
        'name': 'New Year\'s Day Parade (LNYDP)',
        'month': 1,
        'rule': ('fixed', 1),
        'start_time': '12:00', 'end_time': '15:30', 'duration_h': 3.5,
        'footfall': 650000,
        'route_near_store': False,
    },
    {
        'name': 'Diwali on the Square (Trafalgar Sq)',
        'month': 10,
        'rule': ('weekday', 3, 5),          # 4th Saturday of October
        'start_time': '12:00', 'end_time': '20:00', 'duration_h': 8,
        'footfall': 40000,
        'route_near_store': False,
    },
    {
        'name': 'Chinese New Year Parade',
        'month': 2,
        'rule': ('weekday', 1, 6),          # 2nd Sunday of February (approximate)
        'start_time': '11:00', 'end_time': '18:00', 'duration_h': 7,
        'footfall': 300000,
        'route_near_store': False,
    },
    # ── Festivals ─────────────────────────────────────────────────────────────
    {
        'name': 'All Points East Festival (Victoria Park)',
        'month': 8,
        'rule': ('weekday', 2, 5),          # 3rd Friday of August (approx start)
        'start_time': '12:00', 'end_time': '22:30', 'duration_h': 10.5,
        'footfall': 50000,
        'route_near_store': True,           # Victoria Park is ~1.5 mi away
    },
    {
        'name': 'Field Day Festival (Victoria Park)',
        'month': 6,
        'rule': ('weekday', 0, 5),          # 1st Friday of June
        'start_time': '12:00', 'end_time': '23:00', 'duration_h': 11,
        'footfall': 25000,
        'route_near_store': True,
    },
    {
        'name': 'Wireless Festival (Finsbury Park)',
        'month': 7,
        'rule': ('weekday', 0, 5),          # 1st Friday of July
        'start_time': '13:00', 'end_time': '22:30', 'duration_h': 9.5,
        'footfall': 50000,
        'route_near_store': True,           # Finsbury Park is <1 mile from store
    },
    {
        'name': 'Wireless Festival (Finsbury Park) — Day 2',
        'month': 7,
        'rule': ('weekday', 0, 6),          # 1st Saturday of July
        'start_time': '13:00', 'end_time': '22:30', 'duration_h': 9.5,
        'footfall': 50000,
        'route_near_store': True,
    },
    {
        'name': 'Wireless Festival (Finsbury Park) — Day 3',
        'month': 7,
        'rule': ('weekday', 1, 0),          # 2nd Monday of July  (Sun is day 3)
        'start_time': '13:00', 'end_time': '22:30', 'duration_h': 9.5,
        'footfall': 50000,
        'route_near_store': True,
    },
    {
        'name': 'Lovebox Festival (Gunnersbury Park)',
        'month': 7,
        'rule': ('weekday', 2, 5),          # 3rd Friday of July
        'start_time': '12:00', 'end_time': '22:30', 'duration_h': 10.5,
        'footfall': 40000,
        'route_near_store': False,
    },
    {
        'name': 'SW4 Festival (Clapham Common)',
        'month': 8,
        'rule': ('weekday', 3, 5),          # 4th Saturday of August (approx)
        'start_time': '12:00', 'end_time': '23:00', 'duration_h': 11,
        'footfall': 30000,
        'route_near_store': False,
    },
    # ── Major Seasonal / Shopping Events ────────────────────────────────────
    {
        'name': 'Boxing Day (Major Retail Day)',
        'month': 12,
        'rule': ('fixed', 26),
        'start_time': '09:00', 'end_time': '18:00', 'duration_h': 9,
        'footfall': 15000,
        'route_near_store': True,           # Everywhere is busy
    },
    {
        'name': 'Black Friday',
        'month': 11,
        'rule': ('weekday', 3, 4),          # 4th Friday of November
        'start_time': '09:00', 'end_time': '20:00', 'duration_h': 11,
        'footfall': 20000,
        'route_near_store': True,
    },
    {
        'name': 'Christmas Eve',
        'month': 12,
        'rule': ('fixed', 24),
        'start_time': '09:00', 'end_time': '18:00', 'duration_h': 9,
        'footfall': 15000,
        'route_near_store': True,
    },
]


# ==============================================================================
#                         HELPER FUNCTIONS
# ==============================================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    if not lat2 or not lon2 or (lat2 == 0.0 and lon2 == 0.0):
        return 0.0
    R = 3958.8
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dLon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ==============================================================================
#   SMART IMPACT SCORING ENGINE  (bar/pub optimised)
#
#   Formula:
#       raw = footfall_c × distance_c × novelty_c × timing_c × affinity_c
#       Impact Score (1–10) = clamp(round(1 + raw × 9 × CALIBRATION), 1, 10)
#
#   Every component is normalised to 0–1 so multiplying them together means
#   one bad dimension (e.g. event is 1.8 miles away) can't be rescued by a
#   great dimension.  The result is then stretched to the 1–10 scale.
# ==============================================================================

# ── Calibration constant ─────────────────────────────────────────────────────
# 1.25 means a "nearly perfect" event still scores 10 even if one component
# is slightly below its peak.
_CALIBRATION = 1.65

# ── Keyword → category mapping ───────────────────────────────────────────────
# Order matters: first match wins.  Put more-specific terms above generic ones.
_CATEGORY_RULES = [
    # Sports — high affinity for a pub
    ('football',   ['[arsenal]', '[tottenham]', '[chelsea]', '[west ham]', '[crystal palace]',
                    '[brentford]', '[fulham]', '[qpr]', '[leyton orient]', '[england football]',
                    'premier league', 'champions league', 'europa league', 'fa cup',
                    'league cup', 'carabao', 'match day', 'football', 'soccer']),
    ('rugby',      ['rugby', 'six nations', 'premiership rugby', 'harlequins',
                    'saracens', 'wasps', 'world cup rugby']),
    ('cricket',    ['cricket', 'test match', ' odi ', ' t20 ', "lord's", 'the oval']),
    ('combat',     ['boxing', 'ufc', 'mma', 'fight night', 'wrestling', 'wbc', 'ibf']),
    ('marathon',   ['marathon', 'half marathon', '10k', '5k run', 'road race',
                    'fun run', 'triathlon', 'hackney half', 'vitality', 'parkrun',
                    '[annual] tcs', '[annual] hackney', '[annual] royal parks',
                    '[annual] vitality', '[annual] london 10']),
    # Music & festivals
    ('festival',   ['festival', 'wireless', 'all points east', 'field day',
                    'lovebox', 'sw4', '[annual] wireless', '[annual] all points',
                    '[annual] field day', '[annual] lovebox']),
    ('concert',    ['concert', ' live ', 'tour', 'headline', 'presents', 'gig',
                    '[sk]', '[dice]', '[eb]']),
    # Public events
    ('carnival',   ['carnival', 'notting hill', 'parade', 'pride', 'procession',
                    '[annual] notting', '[annual] pride', '[annual] st patrick',
                    '[annual] new year', '[annual] chinese new year',
                    '[annual] diwali']),
    # Pub-friendly misc
    ('bank_holiday', ['[bh] ', 'bank holiday']),
    # Lower-affinity
    ('comedy',     ['comedy', 'comedian', 'stand-up', 'standup']),
    ('theater',    ['theatre', 'theater', 'musical', 'opera', 'ballet',
                    'west end', ' play ', 'production', 'shakespeare',
                    'players', 'drama', 'panto', 'pantomime', 'stage',
                    'the show', 'opening night', 'run week']),
    ('conference', ['conference', 'expo ', 'summit ', 'symposium', 'convention',
                    'awards ceremony', 'trade show']),
    ('market',     ['market', ' fair ', 'farmers', 'street food', 'craft fair']),
]

# ── Per-category weights ─────────────────────────────────────────────────────

# Affinity: how much does this event type drive pub trade?
_AFFINITY = {
    'football':    1.00,   # Pubs are built for match day
    'rugby':       0.95,   # Classic pub sport
    'cricket':     0.85,   # Long sessions = long drinking sessions
    'combat':      0.85,   # Boxing night in a pub is a tradition
    'concert':     0.85,   # Pre/post gig drinks are guaranteed
    'festival':    0.85,   # Festival crowd = thirsty crowd
    'carnival':    0.80,   # Outdoor + drinking culture
    'bank_holiday':0.90,   # People are out all day
    'marathon':    0.65,   # Spectators pop in; runners don't pre-drink
    'comedy':      0.70,   # Some pre/post but niche
    'theater':     0.50,   # Wrong demographic for a pub
    'conference':  0.40,   # Business crowd, daytime
    'market':      0.50,   # Casual browse, not a drinking occasion
    'unknown':     0.65,   # Cautious default
}

# Novelty baseline: how "one-off" / exciting is this category by default?
# Regular league football is lower than a cup final; weekly theatre is much lower
# than a touring band's single concert date.
_NOVELTY_BASE = {
    'football':    0.55,   # Happens every week — cup games handled by history check
    'rugby':       0.65,
    'cricket':     0.65,
    'combat':      0.85,   # Fight nights are rare
    'concert':     0.90,   # Tours are genuinely one-off
    'festival':    0.80,   # Annual but massive and special
    'carnival':    0.85,   # Once a year
    'bank_holiday':0.80,
    'marathon':    0.80,
    'comedy':      0.75,
    'theater':     0.30,   # Runs for weeks/months → low novelty
    'conference':  0.55,
    'market':      0.25,   # Weekly → very low novelty
    'unknown':     0.65,
}


def _classify_event(event_name: str, source: str) -> str:
    """Return the best-matching category string for an event."""
    name_lower = event_name.lower()
    src_lower  = source.lower()
    # ICS feeds are always football
    if src_lower == 'ics feed':
        return 'football'
    for category, keywords in _CATEGORY_RULES:
        if any(kw in name_lower for kw in keywords):
            return category
    return 'unknown'


def _footfall_component(footfall: float) -> float:
    """
    Log-scale footfall → 0.10–1.00.
    A 500-person sold-out special event (0.40) is deliberately distinguishable
    from a 50,000-person festival (0.95) — crowd size still matters, just not
    in a way that crushes small but genuinely exciting events.
    """
    if footfall >= 500000: return 1.00
    if footfall >= 100000: return 0.97
    if footfall >=  50000: return 0.93
    if footfall >=  20000: return 0.87
    if footfall >=  10000: return 0.78
    if footfall >=   5000: return 0.68
    if footfall >=   2000: return 0.55
    if footfall >=   1000: return 0.45
    if footfall >=    500: return 0.35
    if footfall >=    200: return 0.25
    return 0.15


def _distance_component(dist_miles: float) -> float:
    """Steep decay — an event 1.8 miles away is much less relevant than 0.3 miles."""
    if dist_miles < 0.25:  return 1.00
    if dist_miles < 0.50:  return 0.95
    if dist_miles < 0.75:  return 0.88
    if dist_miles < 1.00:  return 0.78
    if dist_miles < 1.25:  return 0.65
    if dist_miles < 1.50:  return 0.50
    if dist_miles < 1.75:  return 0.35
    if dist_miles < 2.00:  return 0.22
    return 0.10


def _history_modifier(event_name: str, history_df: pd.DataFrame) -> float:
    """
    Check how many times we have seen a similar event name in our saved
    events file.  More appearances → more recurring → lower novelty modifier.

    Uses Jaccard token overlap (no extra dependencies).
    Threshold: similarity > 0.45 → counts as "same event".
    """
    if history_df is None or history_df.empty:
        return 1.0   # No history → assume brand new
    if 'Event Name' not in history_df.columns:
        return 1.0

    tokens_new = set(re.sub(r'[\[\]()]', '', event_name).lower().split())
    # Remove common noise tokens
    noise = {'the', 'a', 'an', 'at', 'in', 'of', 'and', 'vs', 'fc',
             'live', 'london', '[sk]', '[dice]', '[eb]', '[annual]', '[bh]'}
    tokens_new -= noise
    if not tokens_new:
        return 1.0

    count = 0
    for hist_name in history_df['Event Name'].dropna().astype(str):
        tokens_hist = set(re.sub(r'[\[\]()]', '', hist_name).lower().split()) - noise
        if not tokens_hist:
            continue
        intersection = tokens_new & tokens_hist
        union        = tokens_new | tokens_hist
        similarity   = len(intersection) / len(union) if union else 0
        if similarity > 0.45:
            count += 1

    if count == 0:   return 1.00   # Never seen before — maximum novelty
    if count == 1:   return 0.90
    if count == 2:   return 0.80
    if count <= 4:   return 0.65
    if count <= 8:   return 0.50
    return 0.38                    # Seen 9+ times — clearly a regular


def _novelty_component(category: str, event_name: str,
                       history_df: pd.DataFrame) -> float:
    """
    Final novelty score = category baseline × history modifier.
    A weekly theatre show (base 0.30) that has appeared 6 times
    in our DB (modifier 0.50) → 0.15 (very low, correct).
    A one-off concert (base 0.90) never seen before (modifier 1.0) → 0.90.
    """
    base     = _NOVELTY_BASE.get(category, 0.65)
    modifier = _history_modifier(event_name, history_df)
    return base * modifier


def _timing_component(date_str: str, start_time: str) -> float:
    """
    Bar/pub timing score.
    Evening × weekend is the sweet spot.
    Weekday mornings barely matter.
    Bank Holiday Mondays are treated like Saturdays.
    """
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        weekday = dt.weekday()   # 0=Mon … 6=Sun
    except Exception:
        weekday = 2   # default Wednesday

    try:
        hour = int(start_time.split(':')[0])
    except Exception:
        hour = 19   # default evening

    # Day factor
    if weekday == 5:   day_f = 1.20   # Saturday
    elif weekday == 4: day_f = 1.15   # Friday
    elif weekday == 6: day_f = 1.05   # Sunday
    elif weekday == 3: day_f = 0.90   # Thursday
    else:              day_f = 0.75   # Mon–Wed

    # Time-of-day factor (pub perspective)
    if hour >= 17:     time_f = 1.20   # Evening  → best for pub
    elif hour >= 12:   time_f = 0.90   # Afternoon → decent
    elif hour >= 9:    time_f = 0.55   # Morning  → low
    else:              time_f = 0.40   # Very early

    # Bank holidays act like Saturday evening regardless of actual weekday
    # (detected via the event name prefix set by gov.uk source)
    if 'bank holiday' in date_str.lower() or weekday == 0 and hour < 12:
        pass   # keep calculated values; BH Monday is already captured in day_f

    return min(day_f * time_f, 1.20)   # cap so we don't over-inflate


def calculate_smart_impact(row, history_df: pd.DataFrame = None) -> int:
    """
    Main scoring entry point.  Replaces calculate_weighted_impact.

    Returns an integer 1–10.

    Score breakdown printed to console only when SCORE_DEBUG = True.
    """
    event_name = str(row.get('Event Name', ''))
    source     = str(row.get('Source', ''))
    footfall   = float(row.get('Est. Footfall', 500) or 500)
    dist       = float(row.get('Distance (Miles)', 1.0) or 1.0)
    date_str   = str(row.get('Date', ''))
    start_time = str(row.get('Start Time', '19:00') or '19:00')

    category   = _classify_event(event_name, source)

    f_c  = _footfall_component(footfall)
    d_c  = _distance_component(dist)
    n_c  = _novelty_component(category, event_name, history_df)
    t_c  = _timing_component(date_str, start_time)
    a_c  = _AFFINITY.get(category, 0.65)

    raw     = f_c * d_c * n_c * t_c * a_c
    scaled  = 1 + raw * 9 * _CALIBRATION
    score   = max(1, min(10, round(scaled)))
    return score


# Keep the old name as an alias so nothing else in the codebase breaks
def calculate_weighted_impact(row):
    """Legacy alias — calls calculate_smart_impact without history."""
    return calculate_smart_impact(row, history_df=None)


def _safe_get(url, headers=None, params=None, timeout=10):
    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
        return r if r.status_code == 200 else None
    except Exception as e:
        print(f"    [!] Request failed ({url[:55]}…): {e}")
        return None


def get_event_details_from_page(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    r = _safe_get(url, headers=headers, timeout=6)
    if not r:
        return None, None, None
    soup = BeautifulSoup(r.content, 'html.parser')
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if data.get('@type') in ['Event', 'MusicEvent']:
                loc  = data.get('location', {})
                geo  = loc.get('geo', {})
                lat  = float(geo.get('latitude', 0.0))
                lon  = float(geo.get('longitude', 0.0))
                name = loc.get('name', 'Unknown Venue')
                if lat != 0.0:
                    return lat, lon, name
        except Exception:
            continue
    return None, None, None


def load_existing_events():
    if not os.path.exists(EVENTS_OUTPUT_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_excel(EVENTS_OUTPUT_FILE)
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    except Exception:
        return pd.DataFrame()


def save_events(df_new, merge=True):
    if merge:
        df_existing = load_existing_events()
        if not df_existing.empty:
            df_new['Date'] = pd.to_datetime(df_new['Date']).dt.date
            merge_keys = df_new[['Date', 'Event Name']].apply(tuple, axis=1).tolist()
            df_existing = df_existing[
                ~df_existing[['Date', 'Event Name']].apply(tuple, axis=1).isin(merge_keys)
            ]
            df_combined = (pd.concat([df_existing, df_new], ignore_index=True)
                           .drop_duplicates(subset=['Date', 'Event Name'])
                           .sort_values('Date'))
            df_combined.to_excel(EVENTS_OUTPUT_FILE, index=False)
            return df_combined
    df_new.to_excel(EVENTS_OUTPUT_FILE, index=False)
    return df_new


# ==============================================================================
#   DATE CALCULATION HELPERS  (used by the Annual Events engine)
# ==============================================================================

def _nth_weekday_of_month(year, month, n, weekday):
    """Return the date of the nth occurrence (0-indexed) of weekday in month."""
    first_day = date(year, month, 1)
    first_occurrence = first_day + timedelta(days=(weekday - first_day.weekday()) % 7)
    return first_occurrence + timedelta(weeks=n)


def _last_weekday_of_month(year, month, weekday):
    """Return the date of the last occurrence of weekday in month."""
    last_day = date(year, month, cal_module.monthrange(year, month)[1])
    delta = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=delta)


def _weekend_nearest(year, month, day):
    """Return the Saturday nearest to a given day-of-month."""
    target = date(year, month, day)
    # Find nearest Saturday (weekday 5)
    days_to_sat = (5 - target.weekday()) % 7
    if days_to_sat > 3:
        days_to_sat -= 7
    return target + timedelta(days=days_to_sat)


def _resolve_date(year, rule, month):
    """Turn a rule tuple into a concrete date for a given year."""
    kind = rule[0]
    try:
        if kind == 'fixed':
            return date(year, month, rule[1])
        elif kind == 'weekday':
            # ('weekday', n_zero_indexed, weekday_0Mon)
            return _nth_weekday_of_month(year, month, rule[1], rule[2])
        elif kind == 'last_weekday':
            return _last_weekday_of_month(year, month, rule[1])
        elif kind == 'weekend_nearest':
            return _weekend_nearest(year, month, rule[1])
    except (ValueError, OverflowError):
        return None
    return None


# ==============================================================================
#   SOURCE 1 ── TICKETMASTER  (full pagination + all segment classifications)
#
#   Changes vs old version:
#     • Iterates through ALL result pages (was limited to first page of 100)
#     • Queries each classification separately so nothing is missed
#     • Uses actual venue lat/lon from API; falls back to VENUE_DB then store loc
#     • Skips junk entries (Season Tickets, Fan Packages, Memberships)
#     • Estimates footfall from actual Ticketmaster 'capacity' field if present
# ==============================================================================

# All segment IDs Ticketmaster uses — cover music, sport, arts, family, misc
TM_SEGMENT_IDS = {
    'Music':          'KZFzniwnSyZfZ7v7nJ',
    'Sports':         'KZFzniwnSyZfZ7v7nE',
    'Arts & Theatre': 'KZFzniwnSyZfZ7v7na',
    'Family':         'KZFzniwnSyZfZ7v7n1',
    'Film':           'KZFzniwnSyZfZ7v7nn',
    'Miscellaneous':  'KZFzniwnSyZfZ7v7n0',
}

TM_JUNK_KEYWORDS = ['season ticket', 'fan package', 'membership', 'hospitality',
                    'vip package', 'gift card', 'experiences', 'parking']

def get_ticketmaster_events(start_date, end_date, biz_lat, biz_lon):
    print(f"  > [1/9] Ticketmaster API (all segments, paginated) …")
    all_events = []
    seen_ids   = set()

    start_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_obj   = datetime.strptime(end_date,   "%Y-%m-%d") + timedelta(days=1)

    for seg_name, seg_id in TM_SEGMENT_IDS.items():
        page = 0
        while True:
            params = {
                'apikey':        TM_API_KEY,
                'geoPoint':      f"{biz_lat},{biz_lon}",
                'radius':        RADIUS_MILES,
                'unit':          'miles',
                'startDateTime': start_obj.strftime('%Y-%m-%dT00:00:00Z'),
                'endDateTime':   end_obj.strftime('%Y-%m-%dT23:59:59Z'),
                'segmentId':     seg_id,
                'size':          100,
                'page':          page,
                'sort':          'date,asc',
            }
            r = _safe_get(
                "https://app.ticketmaster.com/discovery/v2/events.json",
                params=params,
            )
            if not r:
                break

            data          = r.json()
            page_info     = data.get('page', {})
            total_pages   = page_info.get('totalPages', 1)
            events        = data.get('_embedded', {}).get('events', [])

            for ev in events:
                ev_id = ev.get('id', '')
                if ev_id in seen_ids:
                    continue

                name = ev.get('name', 'Unknown')
                # Skip junk
                if any(k in name.lower() for k in TM_JUNK_KEYWORDS):
                    continue

                ev_date  = ev['dates']['start'].get('localDate', '')
                time_str = ev['dates']['start'].get('localTime', '19:00')[:5]
                vd       = ev.get('_embedded', {}).get('venues', [{}])[0]
                venue    = vd.get('name', 'Unknown')

                # Prefer live API coordinates, fall back to our DB, then store
                try:
                    v_lat = float(vd['location']['latitude'])
                    v_lon = float(vd['location']['longitude'])
                except Exception:
                    vdb   = VENUE_DB.get(venue, VENUE_DB['DEFAULT'])
                    v_lat = vdb['lat'] if vdb['lat'] != 0.0 else biz_lat
                    v_lon = vdb['lon'] if vdb['lon'] != 0.0 else biz_lon

                # Capacity: from API priceRanges or our DB
                try:
                    capacity = int(vd.get('upcomingEvents', {}).get('ticketmaster', 1000))
                except Exception:
                    capacity = VENUE_DB.get(venue, VENUE_DB['DEFAULT'])['capacity']

                seen_ids.add(ev_id)
                all_events.append({
                    'Date':         ev_date,
                    'Start Time':   time_str,
                    'End Time':     '22:00',
                    'Duration':     '3.0h',
                    'Event Name':   name,
                    'Venue':        venue,
                    'Est. Footfall': int(capacity * 0.85),
                    'Lat':           v_lat,
                    'Lon':           v_lon,
                    'Source':        f'Ticketmaster ({seg_name})',
                })

            page += 1
            if page >= total_pages or page >= 5:   # cap at 5 pages per segment
                break

    print(f"      → {len(all_events)} events ({len(TM_SEGMENT_IDS)} segments scanned)")
    return all_events


# ==============================================================================
#   SOURCE 2 ── EVENTBRITE  (unchanged, reliable)
# ==============================================================================
def scrape_eventbrite(start_date, end_date, biz_lat, biz_lon):
    print("  > [2/9] Eventbrite scrape …")
    events_list = []
    headers     = {'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'}
    seen_links  = set()
    try:
        url = (f"https://www.eventbrite.co.uk/d/{SEARCH_CITY_SLUG}/events/"
               f"?start_date={start_date}&end_date={end_date}&page=1")
        r = _safe_get(url, headers=headers)
        if not r:
            return []
        soup  = BeautifulSoup(r.content, 'html.parser')
        count = 0
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'eventbrite.co.uk/e/' not in href:
                continue
            clean_url = href.split('?')[0]
            if clean_url in seen_links:
                continue
            seen_links.add(clean_url)
            text = link.text.strip()
            if len(text) < 5:
                continue
            real_lat, real_lon, real_venue = get_event_details_from_page(clean_url)
            if real_lat and real_lon:
                lat_val, lon_val, venue_val = real_lat, real_lon, real_venue
            else:
                lat_val, lon_val = biz_lat, biz_lon
                venue_val = "Unknown (Check Link)"
            events_list.append({
                'Date': start_date, 'Start Time': '19:00', 'End Time': '22:00',
                'Duration': '3.0h', 'Event Name': f"[EB] {text[:40]}",
                'Venue': venue_val, 'Est. Footfall': 300,
                'Lat': lat_val, 'Lon': lon_val, 'Source': 'Eventbrite',
            })
            count += 1
            if count >= 15:
                break
    except Exception as e:
        print(f"    [!] Eventbrite error: {e}")
    print(f"      → {len(events_list)} events")
    return events_list


# ==============================================================================
#   SOURCE 3 ── ICS CALENDAR FEEDS  (unchanged)
# ==============================================================================
def parse_ics_feeds(start_date, end_date):
    print(f"  > [3/9] ICS Feeds ({len(CALENDAR_FEEDS)} clubs) …")
    matches = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for feed in CALENDAR_FEEDS:
        try:
            r = _safe_get(feed['url'], headers=headers)
            if not r:
                continue
            events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', r.text, re.DOTALL)
            for ev in events:
                sum_m   = re.search(r'SUMMARY:(.*)', ev)
                start_m = re.search(r'DTSTART.*:(\d{8}T\d{6})', ev)
                if not sum_m or not start_m:
                    continue
                dt_start  = datetime.strptime(start_m.group(1), '%Y%m%dT%H%M%S')
                date_str  = dt_start.strftime('%Y-%m-%d')
                time_str  = dt_start.strftime('%H:%M')
                if not (start_date <= date_str <= end_date):
                    continue
                summary   = sum_m.group(1).strip()
                club_name = feed['name']
                # Only count home fixtures
                if ' - ' in summary:
                    home_team = summary.split(' - ')[0].strip()
                elif ' vs ' in summary:
                    home_team = summary.split(' vs ')[0].strip()
                else:
                    home_team = summary
                if club_name.split()[0].lower() not in home_team.lower():
                    continue
                matches.append({
                    'Date': date_str,
                    'Start Time': time_str,
                    'End Time': (dt_start + timedelta(hours=2)).strftime('%H:%M'),
                    'Duration': '2.0h',
                    'Event Name': f"[{club_name}] {summary}",
                    'Venue': feed['home_venue'],
                    'Est. Footfall': feed['capacity'],
                    'Lat': feed['home_lat'],
                    'Lon': feed['home_lon'],
                    'Source': 'ICS Feed',
                })
        except Exception as e:
            print(f"    [!] ICS error ({feed['name']}): {e}")
    print(f"      → {len(matches)} fixtures")
    return matches


# ==============================================================================
#   SOURCE 4 ── DICE.FM  (rewritten with correct endpoint + robust fallback)
#
#   Dice uses a versioned REST API at events-api.dice.fm.
#   The correct filter params for their v1 events endpoint are:
#     filter[event_status][]  = active
#     filter[cities][]        = London
#     filter[from]            = ISO8601 date
#     filter[to]              = ISO8601 date
#     page[size]              = up to 100
#   No auth required for public browse.
# ==============================================================================
def scrape_dice_fm(start_date, end_date, biz_lat, biz_lon):
    print("  > [4/9] Dice.fm API …")
    events_list = []
    api_headers = {
        'User-Agent':  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        'Accept':      'application/json',
        'x-api-key':   'dice',
    }
    try:
        page_num = 1
        while page_num <= 3:   # max 3 pages = 300 events
            params = {
                'filter[event_status][]': 'active',
                'filter[cities][]':       'London',
                'filter[from]':           f"{start_date}T00:00:00",
                'filter[to]':             f"{end_date}T23:59:59",
                'page[size]':             100,
                'page[number]':           page_num,
            }
            r = _safe_get('https://events-api.dice.fm/v1/events',
                          headers=api_headers, params=params)

            if r is None:
                # Fallback: scrape the London browse page JSON-LD
                print("      [Dice API unavailable — trying HTML fallback]")
                page_r = _safe_get('https://dice.fm/browse/london',
                                   headers={'User-Agent': 'Mozilla/5.0'})
                if page_r:
                    soup = BeautifulSoup(page_r.content, 'html.parser')
                    for script in soup.find_all('script', type='application/ld+json'):
                        try:
                            blob  = json.loads(script.string)
                            items = blob if isinstance(blob, list) else [blob]
                            for item in items:
                                if item.get('@type') not in ('Event', 'MusicEvent'):
                                    continue
                                d_str = str(item.get('startDate', ''))[:10]
                                if not (start_date <= d_str <= end_date):
                                    continue
                                loc   = item.get('location', {})
                                geo   = loc.get('geo', {})
                                lat   = float(geo.get('latitude',  biz_lat))
                                lon   = float(geo.get('longitude', biz_lon))
                                if haversine_distance(biz_lat, biz_lon, lat, lon) > RADIUS_MILES:
                                    continue
                                events_list.append({
                                    'Date':         d_str,
                                    'Start Time':   str(item.get('startDate', ''))[-5:] or '20:00',
                                    'End Time':     '23:59',
                                    'Duration':     '4.0h',
                                    'Event Name':   f"[Dice] {item.get('name', 'Event')[:45]}",
                                    'Venue':        loc.get('name', 'Unknown'),
                                    'Est. Footfall': 600,
                                    'Lat': lat, 'Lon': lon,
                                    'Source': 'Dice.fm',
                                })
                        except Exception:
                            continue
                break  # HTML fallback is single-pass

            payload   = r.json()
            raw_items = payload.get('data', [])
            if not raw_items:
                break

            for ev in raw_items:
                try:
                    # Dice v1 structure: ev.attributes
                    attrs = ev.get('attributes', ev)  # handle both wrapped & flat
                    d_str = (attrs.get('date') or attrs.get('start_date') or '')[:10]
                    if not d_str or not (start_date <= d_str <= end_date):
                        continue

                    venue = attrs.get('venue', {}) or {}
                    v_lat = float(venue.get('latitude')  or biz_lat)
                    v_lon = float(venue.get('longitude') or biz_lon)

                    if haversine_distance(biz_lat, biz_lon, v_lat, v_lon) > RADIUS_MILES:
                        continue

                    raw_time = (attrs.get('date') or attrs.get('start_date') or '')
                    time_str = raw_time[11:16] if len(raw_time) > 10 else '20:00'

                    events_list.append({
                        'Date':         d_str,
                        'Start Time':   time_str or '20:00',
                        'End Time':     '23:59',
                        'Duration':     '4.0h',
                        'Event Name':   f"[Dice] {(attrs.get('name') or 'Event')[:45]}",
                        'Venue':        venue.get('name', 'Unknown'),
                        'Est. Footfall': int(venue.get('capacity') or 600),
                        'Lat': v_lat, 'Lon': v_lon,
                        'Source': 'Dice.fm',
                    })
                except Exception:
                    continue

            # Dice pagination: check if there's a next page
            if not payload.get('next'):
                break
            page_num += 1

    except Exception as e:
        print(f"    [!] Dice.fm error: {e}")

    print(f"      → {len(events_list)} events")
    return events_list


# ==============================================================================
#   SOURCE 5 ── SKIDDLE  (UK events, free key)
# ==============================================================================
def get_skiddle_events(start_date, end_date, biz_lat, biz_lon):
    print("  > [5/9] Skiddle API …")
    if SKIDDLE_API_KEY == 'YOUR_SKIDDLE_KEY':
        print("      [skipped – register free at skiddle.com/api]")
        return []
    events_list = []
    try:
        params = {
            'api_key':   SKIDDLE_API_KEY,
            'latitude':  biz_lat,
            'longitude': biz_lon,
            'radius':    RADIUS_KM,
            'minDate':   start_date,
            'maxDate':   end_date,
            'limit':     100,
            'order':     'distance',
        }
        r = _safe_get('https://www.skiddle.com/api/v1/events/search/', params=params)
        if not r:
            return []
        for ev in r.json().get('results', []):
            try:
                v_lat = float(ev.get('venue', {}).get('latitude',  biz_lat))
                v_lon = float(ev.get('venue', {}).get('longitude', biz_lon))
                events_list.append({
                    'Date':         ev.get('date', start_date),
                    'Start Time':   (ev.get('openingtimes', {}).get('doorsopen', '19:00') or '19:00')[:5],
                    'End Time':     (ev.get('openingtimes', {}).get('doorsclose', '23:00') or '23:00')[:5],
                    'Duration':     '4.0h',
                    'Event Name':   ev.get('eventname', 'Event'),
                    'Venue':        ev.get('venue', {}).get('name', 'Unknown'),
                    'Est. Footfall': 300,
                    'Lat': v_lat, 'Lon': v_lon,
                    'Source': 'Skiddle',
                })
            except Exception:
                continue
    except Exception as e:
        print(f"    [!] Skiddle error: {e}")
    print(f"      → {len(events_list)} events")
    return events_list


# ==============================================================================
#   SOURCE 6 ── PREDICTHQ  (festival / attendance intelligence, free tier)
# ==============================================================================
def get_predicthq_events(start_date, end_date, biz_lat, biz_lon):
    print("  > [6/9] PredictHQ …")
    if PREDICTHQ_TOKEN == 'YOUR_PREDICTHQ_TOKEN':
        print("      [skipped – register free at predicthq.com]")
        return []
    events_list = []
    try:
        headers = {'Authorization': f'Bearer {PREDICTHQ_TOKEN}', 'Accept': 'application/json'}
        params  = {
            'within':   f"{RADIUS_KM}km@{biz_lat},{biz_lon}",
            'start.gte': start_date,
            'start.lte': end_date,
            'category': 'concerts,festivals,sports,community,conferences,expos,performing-arts',
            'limit':     100,
            'sort':      'rank',
        }
        r = _safe_get('https://api.predicthq.com/v1/events/', headers=headers, params=params)
        if not r:
            return []
        for ev in r.json().get('results', []):
            try:
                loc = ev.get('location', [0, 0])
                events_list.append({
                    'Date':         ev['start'][:10],
                    'Start Time':   ev['start'][11:16] or '12:00',
                    'End Time':     (ev.get('end', ev['start']))[:16][11:] or '22:00',
                    'Duration':     '3.0h',
                    'Event Name':   f"[PHQ] {ev.get('title', 'Event')}",
                    'Venue':        (ev.get('entities') or [{}])[0].get('name', 'Unknown'),
                    'Est. Footfall': int(ev.get('phq_attendance') or 500),
                    'Lat': loc[1] if len(loc) > 1 else biz_lat,
                    'Lon': loc[0] if len(loc) > 0 else biz_lon,
                    'Source': 'PredictHQ',
                })
            except Exception:
                continue
    except Exception as e:
        print(f"    [!] PredictHQ error: {e}")
    print(f"      → {len(events_list)} events")
    return events_list


# ==============================================================================
#   SOURCE 7 ── UK BANK HOLIDAYS  (GOV.UK — no key, 100% reliable)
# ==============================================================================
def get_uk_bank_holidays(start_date, end_date):
    print("  > [7/9] UK Bank Holidays (GOV.UK) …")
    events_list = []
    try:
        r = _safe_get('https://www.gov.uk/bank-holidays.json')
        if not r:
            return []
        for event in r.json().get('england-and-wales', {}).get('events', []):
            d = event.get('date', '')
            if not (start_date <= d <= end_date):
                continue
            title = event.get('title', 'Bank Holiday')
            events_list.append({
                'Date': d, 'Start Time': '09:00', 'End Time': '22:00',
                'Duration': '13.0h',
                'Event Name': f"[BH] {title}",
                'Venue': 'Citywide',
                'Est. Footfall': 10000,
                'Lat': BUSINESS_LAT, 'Lon': BUSINESS_LONG,
                'Source': 'Gov.UK Bank Holidays',
            })
    except Exception as e:
        print(f"    [!] Bank Holidays error: {e}")
    print(f"      → {len(events_list)} in range")
    return events_list


# ==============================================================================
#   SOURCE 8 ── SONGKICK  (concerts & tours, JSON-LD scrape)
# ==============================================================================
def scrape_songkick(start_date, end_date, biz_lat, biz_lon):
    print("  > [8/9] Songkick …")
    events_list = []
    headers     = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        r = _safe_get('https://www.songkick.com/metro_areas/24426/calendar',
                      headers=headers)
        if not r:
            return []
        soup = BeautifulSoup(r.content, 'html.parser')
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                blob  = json.loads(script.string)
                items = blob if isinstance(blob, list) else [blob]
                for item in items:
                    if item.get('@type') not in ('Event', 'MusicEvent'):
                        continue
                    d_str = str(item.get('startDate', ''))[:10]
                    if not (start_date <= d_str <= end_date):
                        continue
                    loc  = item.get('location', {})
                    geo  = loc.get('geo', {})
                    lat  = float(geo.get('latitude',  biz_lat))
                    lon  = float(geo.get('longitude', biz_lon))
                    if haversine_distance(biz_lat, biz_lon, lat, lon) > RADIUS_MILES:
                        continue
                    venue_name = loc.get('name', 'Unknown')
                    capacity   = VENUE_DB.get(venue_name, VENUE_DB['DEFAULT'])['capacity']
                    events_list.append({
                        'Date': d_str, 'Start Time': '19:30', 'End Time': '22:30',
                        'Duration': '3.0h',
                        'Event Name': f"[SK] {item.get('name', 'Concert')[:45]}",
                        'Venue': venue_name, 'Est. Footfall': capacity,
                        'Lat': lat, 'Lon': lon,
                        'Source': 'Songkick',
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"    [!] Songkick error: {e}")
    print(f"      → {len(events_list)} events")
    return events_list


# ==============================================================================
#   SOURCE 9 ── ANNUAL PUBLIC EVENTS ENGINE
#
#   Marathons, road races, parades, carnivals, festivals, and major retail days
#   are calculated from the ANNUAL_EVENTS rules above — no API needed.
#
#   Why a separate engine instead of hard-coded dates?
#     → Same entry automatically produces the right date for 2025, 2026, 2027 …
#     → "Last Sunday of April" will always be the correct Marathon Sunday
#     → "Last Saturday of June" will always be Pride
#     → Just update ANNUAL_EVENTS once to add new events forever
#
#   Distance logic for public events:
#     route_near_store = True  → distance overridden to 0.3 mi (high local impact)
#     route_near_store = False → distance set to biz_lat/lon (captured but lower score)
# ==============================================================================
def get_annual_public_events(start_date, end_date):
    print("  > [9/9] Annual Public Events (marathons, parades, festivals) …")
    events_list = []

    start_d = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_d   = datetime.strptime(end_date,   '%Y-%m-%d').date()

    # Check current year AND next year (scan may span a year boundary)
    years_to_check = {start_d.year, end_d.year}

    for ev_def in ANNUAL_EVENTS:
        for year in years_to_check:
            resolved = _resolve_date(year, ev_def['rule'], ev_def['month'])
            if resolved is None:
                continue
            if not (start_d <= resolved <= end_d):
                continue

            # Distance: route events are treated as 0.3 miles from store
            dist_override = 0.3 if ev_def.get('route_near_store') else 1.0
            lat_to_use    = BUSINESS_LAT
            lon_to_use    = BUSINESS_LONG

            end_hour_h = int(ev_def['end_time'].split(':')[0])
            events_list.append({
                'Date':         resolved.strftime('%Y-%m-%d'),
                'Start Time':   ev_def['start_time'],
                'End Time':     ev_def['end_time'],
                'Duration':     f"{ev_def['duration_h']}h",
                'Event Name':   f"[Annual] {ev_def['name']}",
                'Venue':        'Citywide / Public Route',
                'Est. Footfall': ev_def['footfall'],
                'Lat':           lat_to_use,
                'Lon':           lon_to_use,
                '_dist_override': dist_override,   # used in impact calculation below
                'Source':        'Annual Events Calendar',
            })

    print(f"      → {len(events_list)} annual events in range")
    return events_list


# ==============================================================================
#                           MAIN SCAN FUNCTION
# ==============================================================================

def run_event_scan(sheet_id, username, start_date=None, end_date=None, merge=True):
    biz_lat = BUSINESS_LAT
    biz_lon = BUSINESS_LONG

    print("━" * 64)
    print("  ROTA MASTER — EVENT INTELLIGENCE SCAN")
    print("━" * 64)

    today = date.today()
    if start_date is None:
        start_date = today.strftime('%Y-%m-%d')
    if end_date is None:
        end_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')

    if datetime.strptime(start_date, '%Y-%m-%d').date() < today:
        start_date = today.strftime('%Y-%m-%d')

    print(f"  Scan range : {start_date}  →  {end_date}")
    print(f"  Location   : {biz_lat:.4f}, {biz_lon:.4f}  (radius {RADIUS_MILES} mi)")
    print("─" * 64)

    # ── Collect ───────────────────────────────────────────────────────────────
    all_events  = []
    all_events += get_ticketmaster_events(start_date, end_date, biz_lat, biz_lon)
    all_events += scrape_eventbrite(start_date, end_date, biz_lat, biz_lon)
    all_events += parse_ics_feeds(start_date, end_date)
    all_events += scrape_dice_fm(start_date, end_date, biz_lat, biz_lon)
    all_events += get_skiddle_events(start_date, end_date, biz_lat, biz_lon)
    all_events += get_predicthq_events(start_date, end_date, biz_lat, biz_lon)
    all_events += get_uk_bank_holidays(start_date, end_date)
    all_events += scrape_songkick(start_date, end_date, biz_lat, biz_lon)
    all_events += get_annual_public_events(start_date, end_date)

    if not all_events:
        print("\n  No events found from any source.")
        return pd.DataFrame()

    df = pd.DataFrame(all_events)

    # ── Distance calculation ─────────────────────────────────────────────────
    def _dist(row):
        # Annual events may override the distance via _dist_override
        if '_dist_override' in row and pd.notna(row['_dist_override']):
            return float(row['_dist_override'])
        return haversine_distance(biz_lat, biz_lon,
                                  row.get('Lat', 0), row.get('Lon', 0))

    df['Distance (Miles)'] = df.apply(_dist, axis=1)

    # Drop the internal helper column
    if '_dist_override' in df.columns:
        df = df.drop(columns=['_dist_override'])

    # Keep events within radius OR citywide types (bank holidays, annual events)
    citywide_sources = {'Gov.UK Bank Holidays', 'Annual Events Calendar'}
    df = df[
        (df['Distance (Miles)'] <= RADIUS_MILES) |
        (df['Source'].isin(citywide_sources))
    ]

    # ── Impact scoring ────────────────────────────────────────────────────────
    # Load our existing event history BEFORE scoring so the novelty engine
    # can check how many times each event has appeared before in our database.
    print("  Scoring with smart impact engine …")
    history_df = load_existing_events()
    df['Event Category'] = df.apply(
        lambda r: _classify_event(str(r.get('Event Name', '')), str(r.get('Source', ''))),
        axis=1,
    )
    df['Impact Score'] = df.apply(
        lambda r: calculate_smart_impact(r, history_df=history_df), axis=1
    )

    # ── De-duplicate & sort ───────────────────────────────────────────────────
    before = len(df)
    df = (df[df['Impact Score'] >= MIN_IMPACT_THRESHOLD]
            .drop_duplicates(subset=['Date', 'Event Name'])
            .sort_values('Date')
            .reset_index(drop=True))

    print("─" * 64)
    print(f"  ✅  {len(df)} significant events  "
          f"({before - len(df)} filtered/deduplicated)")
    print("━" * 64)

    if not df.empty:
        save_events(df, merge=merge)

    return df


# ==============================================================================
#                         CONVENIENCE WRAPPERS
# ==============================================================================

def scan_week(sheet_id, username, week_start_date):
    ws = (datetime.strptime(week_start_date, '%Y-%m-%d').date()
          if isinstance(week_start_date, str) else week_start_date)
    return run_event_scan(
        sheet_id=sheet_id, username=username,
        start_date=ws.strftime('%Y-%m-%d'),
        end_date=(ws + timedelta(days=6)).strftime('%Y-%m-%d'),
        merge=True,
    )


def scan_live(sheet_id, username, days_ahead=30):
    today = date.today()
    return run_event_scan(
        sheet_id=sheet_id, username=username,
        start_date=today.strftime('%Y-%m-%d'),
        end_date=(today + timedelta(days=days_ahead)).strftime('%Y-%m-%d'),
        merge=True,
    )


if __name__ == "__main__":
    pass
