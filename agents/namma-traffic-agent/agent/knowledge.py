"""
bengaluru_knowledge.py - Bengaluru Transit & Traffic Knowledge Base
Curated geospatial and transit dataset for Bengaluru (Bangalore) traffic intelligence.
"""

from typing import Dict, List, Any

# Major Bengaluru Hubs & Locations with coordinates and primary transit modes
BENGALURU_HUBS: Dict[str, Dict[str, Any]] = {
    "koramangala": {
        "display_name": "Koramangala",
        "zone": "South-East",
        "coords": (12.9352, 77.6245),
        "nearest_metro": ("South End Circle" , "Green", 4.5),
        "corridors": ["Hosur Road", "Intermediate Ring Road", "Sarjapur Road"],
        "tech_parks": ["Prestige Technostar", "Sony Signal Hub"]
    },
    "indiranagar": {
        "display_name": "Indiranagar",
        "zone": "East",
        "coords": (12.9719, 77.6412),
        "nearest_metro": ("Indiranagar", "Purple", 0.0),
        "corridors": ["100 Feet Road", "Old Airport Road", "CMH Road"],
        "tech_parks": ["Bagmane Tech Park"]
    },
    "whitefield": {
        "display_name": "Whitefield",
        "zone": "East Suburb",
        "coords": (12.9698, 77.7500),
        "nearest_metro": ("Whitefield (Kadugodi)", "Purple", 0.0),
        "corridors": ["ITPL Main Road", "Varthur Road", "Whitefield Main Road"],
        "tech_parks": ["ITPL", "EPIP Zone", "Prestige Shantiniketan"]
    },
    "hsr_layout": {
        "display_name": "HSR Layout",
        "zone": "South-East",
        "coords": (12.9121, 77.6446),
        "nearest_metro": ("Central Silk Board", "Yellow", 1.8),
        "corridors": ["Outer Ring Road", "Hosur Road", "27th Main"],
        "tech_parks": ["HSR Sector 1 Startups Hub"]
    },
    "bellandur": {
        "display_name": "Bellandur / ORR",
        "zone": "Outer Ring Road East",
        "coords": (12.9304, 77.6784),
        "nearest_metro": ("Baiyappanahalli", "Purple", 7.5),
        "corridors": ["Outer Ring Road (ORR)", "Sarjapur Road"],
        "tech_parks": ["Ecospace", "EcoWorld", "Cessna Business Park"]
    },
    "marathahalli": {
        "display_name": "Marathahalli",
        "zone": "East",
        "coords": (12.9591, 77.6974),
        "nearest_metro": ("KR Puram", "Purple", 4.2),
        "corridors": ["Outer Ring Road", "Old Airport Road", "Varthur Road"],
        "tech_parks": ["Prestige Tech Park", "Kalyani Tech Park"]
    },
    "electronic_city": {
        "display_name": "Electronic City",
        "zone": "South Suburb",
        "coords": (12.8452, 77.6602),
        "nearest_metro": ("Electronic City", "Yellow", 0.0),
        "corridors": ["Hosur Road", "NICE Road", "Electronic City Elevated Expressway"],
        "tech_parks": ["Infosys Campus", "Wipro Campus", "Cyber Park"]
    },
    "hebbal": {
        "display_name": "Hebbal",
        "zone": "North",
        "coords": (13.0358, 77.5970),
        "nearest_metro": ("Yeshwantpur", "Green", 5.0),
        "corridors": ["Bellary Road (NH 44)", "Outer Ring Road"],
        "tech_parks": ["Manyata Tech Park", "Kirloskar Tech Park"]
    },
    "manyata": {
        "display_name": "Manyata Tech Park / Nagavara",
        "zone": "North-East",
        "coords": (13.0450, 77.6200),
        "nearest_metro": ("Baiyappanahalli", "Purple", 7.0),
        "corridors": ["Outer Ring Road (North)", "Thanisandra Main Road"],
        "tech_parks": ["Manyata Embassy Business Park"]
    },
    "majestic": {
        "display_name": "Majestic (KSR / Kempegowda)",
        "zone": "Central",
        "coords": (12.9774, 77.5708),
        "nearest_metro": ("Nadaprabhu Kempegowda Majestic", "Interchange (Purple/Green)", 0.0),
        "corridors": ["Subhash Nagar", "KG Road", "Dhanvantri Road"],
        "tech_parks": ["City Railway Station", "KSRTC / BMTC Central Terminus"]
    },
    "mg_road": {
        "display_name": "MG Road / CBD",
        "zone": "Central",
        "coords": (12.9756, 77.6066),
        "nearest_metro": ("MG Road", "Purple", 0.0),
        "corridors": ["MG Road", "Brigade Road", "Residency Road"],
        "tech_parks": ["UB City", "Raheja Towers"]
    },
    "airport": {
        "display_name": "Kempegowda International Airport (BLR)",
        "zone": "Far North",
        "coords": (13.1986, 77.7066),
        "nearest_metro": ("Yeshwantpur", "Green", 28.0),
        "corridors": ["Bellary Road / Airport Expressway (NH 44)", "SH 104 (Bagalur)"],
        "tech_parks": ["KIA Logistics Park", "Aerotropolis"]
    },
    "jp_nagar": {
        "display_name": "JP Nagar",
        "zone": "South",
        "coords": (12.9063, 77.5857),
        "nearest_metro": ("JP Nagar", "Green", 0.0),
        "corridors": ["Bannerghatta Road", "Outer Ring Road (South)", "Kanakapura Road"],
        "tech_parks": ["Kalyani Magnum"]
    },
    "banashankari": {
        "display_name": "Banashankari",
        "zone": "South-West",
        "coords": (12.9255, 77.5468),
        "nearest_metro": ("Banashankari", "Green", 0.0),
        "corridors": ["Outer Ring Road", "Kanakapura Road"],
        "tech_parks": ["South Bengaluru Commercial Hub"]
    }
}

# Notorious Bengaluru Bottlenecks & Choke Points
CHOKEPOINTS: Dict[str, Dict[str, Any]] = {
    "silk_board": {
        "name": "Central Silk Board Junction",
        "base_delay_minutes": 35,
        "peak_congestion_index": 9.6,  # out of 10
        "affected_routes": [("koramangala", "electronic_city"), ("hsr_layout", "electronic_city"), ("koramangala", "bellandur"), ("hsr_layout", "bellandur")],
        "reason": "Epicenter connecting ORR, Hosur Road, BTM, and HSR; heavy construction for metro interchange.",
        "best_workaround": "Use Madiwala market internal bypass or BTM 29th Main for South Bengaluru; take Yellow Line metro once accessible."
    },
    "tin_factory": {
        "name": "Tin Factory / KR Puram Hanging Bridge",
        "base_delay_minutes": 30,
        "peak_congestion_index": 9.3,
        "affected_routes": [("indiranagar", "whitefield"), ("hebbal", "whitefield"), ("manyata", "whitefield"), ("indiranagar", "marathahalli")],
        "reason": "Severe bottleneck where Old Madras Road merges with ORR; high volume of BMTC buses and interstate private carriers.",
        "best_workaround": "Take Purple Line Metro all the way to KR Puram or Kadugodi/Whitefield directly."
    },
    "hebbal_flyover": {
        "name": "Hebbal Flyover Junction",
        "base_delay_minutes": 25,
        "peak_congestion_index": 8.9,
        "affected_routes": [("majestic", "airport"), ("mg_road", "airport"), ("indiranagar", "airport"), ("manyata", "hebbal")],
        "reason": "Merge point of Bellary Road (airport expressway) and North Outer Ring Road; heavy airport transit combined with Manyata tech commuter surge.",
        "best_workaround": "Use Bagalur / Hennur-KIAL road for airport; travel before 4:30 PM or after 8:30 PM."
    },
    "ecospace_orr": {
        "name": "Ecospace / Bellandur ORR Stretch",
        "base_delay_minutes": 35,
        "peak_congestion_index": 9.4,
        "affected_routes": [("hsr_layout", "bellandur"), ("koramangala", "marathahalli"), ("bellandur", "marathahalli")],
        "reason": "Dense concentration of 150k+ IT workers exiting simultaneously between 5:30 PM and 8:30 PM onto single service roads.",
        "best_workaround": "Stagger departure times: leave before 4:00 PM or after 8:15 PM; utilize internal tech park transit buses."
    },
    "marathahalli_bridge": {
        "name": "Marathahalli Multiplex / Bridge Junction",
        "base_delay_minutes": 20,
        "peak_congestion_index": 8.7,
        "affected_routes": [("indiranagar", "whitefield"), ("bellandur", "whitefield"), ("marathahalli", "whitefield")],
        "reason": "Intersecting traffic from Old Airport Road, Varthur Road, and Outer Ring Road under a narrow railway bridge.",
        "best_workaround": "Opt for Kundalahalli Gate underpass or Purple Line Metro (Baiyappanahalli -> Whitefield)."
    },
    "sony_world_signal": {
        "name": "Sony World Signal (Koramangala 80ft & 100ft Junction)",
        "base_delay_minutes": 18,
        "peak_congestion_index": 8.1,
        "affected_routes": [("koramangala", "indiranagar"), ("hsr_layout", "koramangala")],
        "reason": "High density dining and startup district with intense cross-traffic and street parking.",
        "best_workaround": "Use Intermediate Ring Road (IRR) directly towards Domlur."
    },
    "goraguntepalya": {
        "name": "Goraguntepalya / Yeshwantpur Junction",
        "base_delay_minutes": 25,
        "peak_congestion_index": 8.6,
        "affected_routes": [("majestic", "hebbal"), ("banashankari", "hebbal")],
        "reason": "Tumkur Road flyover landing, Peenya industrial cargo traffic, and Green Line metro feeder intersection.",
        "best_workaround": "Take Green Line Metro directly to Yeshwantpur or Goraguntepalya station."
    }
}

# Flood / Waterlogging Prone Spots in Monsoon Rains
MONSOON_WATERLOGGING_ZONES: List[Dict[str, Any]] = [
    {
        "location": "Kadubeesanahalli Underpass (ORR)",
        "severity": "High",
        "typical_water_depth": "1.5 - 2.5 ft during heavy rain",
        "advisory": "Avoid two-wheelers and low ground-clearance sedans. Divert via Panathur or Marathahalli main road."
    },
    {
        "location": "Okalipuram Underpass",
        "severity": "Critical",
        "typical_water_depth": "2 - 3 ft",
        "advisory": "Railway underbridge floods within 20 mins of heavy downpour. Use flyover toward Majestic."
    },
    {
        "location": "Hebbal Down-Ramp (Towards Airport)",
        "severity": "Medium",
        "typical_water_depth": "1 ft standing water",
        "advisory": "Severe hydroplaning risk; speeds drop to < 10 km/h."
    },
    {
        "location": "Silk Board Service Roads & U-turn",
        "severity": "High",
        "typical_water_depth": "1.5 ft",
        "advisory": "Service road submerged; stick strictly to the center lanes or elevated flyover."
    },
    {
        "location": "Panathur Railway Underbridge (RUB)",
        "severity": "Critical",
        "typical_water_depth": "Submerged during rains",
        "advisory": "Completely impassable during medium to heavy downpours. Avoid Bellandur-Balagere connector."
    }
]

# Namma Metro Line Station Lists and Direct Travel Times (minutes between adjacent stations ~ 2.0 min)
METRO_LINES = {
    "Purple": {
        "stations": [
            "Whitefield (Kadugodi)", "Channasandra", "Kadugodi Tree Park", "Hopefarm Channasandra",
            "Hoodi", "Garudachar Palya", "Singayyanapalya", "KR Puram", "Benniganahalli",
            "Baiyappanahalli", "Swami Vivekananda Road", "Indiranagar", "Halasuru", "Trinity",
            "MG Road", "Cubbon Park", "Dr. BR Ambedkar Vidhana Soudha", "Sir M Visvesvaraya Central College",
            "Nadaprabhu Kempegowda Majestic", "City Railway Station", "Magadi Road", "Hosahalli",
            "Vijayanagar", "Attiguppe", "Deepanjali Nagar", "Mysuru Road", "Pantharapalya",
            "Nayandahalli", "Rajarajeshwari Nagar", "Jnanabharathi", "Pattanagere", "Kengeri Bus Terminal",
            "Kengeri", "Challaghatta"
        ],
        "fare_max": 60
    },
    "Green": {
        "stations": [
            "Madavara", "Chikkabidarakallu", "Manjunathanagar", "Nagasandra", "Dasarahalli",
            "Jalahalli", "Peenya Industry", "Peenya", "Goraguntepalya", "Yeshwantpur",
            "Sandal Soap Factory", "Mahalakshmi", "Rajajinagar", "Kuvempu Road", "Srirampura",
            "Sampige Road", "Nadaprabhu Kempegowda Majestic", "Chickpete", "Krishna Rajendra Market",
            "National College", "Lalbagh", "South End Circle", "Jayanagar", "Rashtreeya Vidyalaya Road",
            "Banashankari", "Jaya Prakash Nagar", "Yelachenahalli", "Konanakunte Cross",
            "Doddakallasandra", "Vajarahalli", "Thalaghattapura", "Silk Institute"
        ],
        "fare_max": 60
    },
    "Yellow": {
        "stations": [
            "Rashtreeya Vidyalaya Road", "Ragigudda", "Jayadeva Hospital", "BTM Layout",
            "Central Silk Board", "Bommanahalli", "Hongasandra", "Kudlu Gate", "Singasandra",
            "Hosa Road", "Beratena Agrahara", "Electronic City", "Infosys Foundation Konappana Agrahara",
            "Huskur Road", "Hebbagodi", "Bommasandra"
        ],
        "fare_max": 50
    }
}
