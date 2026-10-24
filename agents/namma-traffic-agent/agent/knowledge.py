"""
bengaluru_knowledge.py - Bengaluru Transit & Traffic Knowledge Base
Curated geospatial, BMTC bus, Namma Metro, and weather dataset for Bengaluru (Bangalore).
"""

from typing import Dict, List, Any

# Major Bengaluru Hubs & Locations with coordinates and primary transit modes
BENGALURU_HUBS: Dict[str, Dict[str, Any]] = {
    "koramangala": {
        "display_name": "Koramangala",
        "zone": "South-East",
        "coords": (12.9352, 77.6245),
        "nearest_metro": ("South End Circle" , "Green", 4.5),
        "bus_stop": "Sony World Junction / Koramangala TTMC",
        "corridors": ["Hosur Road", "Intermediate Ring Road", "Sarjapur Road"],
        "tech_parks": ["Prestige Technostar", "Sony Signal Hub"]
    },
    "indiranagar": {
        "display_name": "Indiranagar",
        "zone": "East",
        "coords": (12.9719, 77.6412),
        "nearest_metro": ("Indiranagar", "Purple", 0.0),
        "bus_stop": "CMH Road / Indiranagar 100ft Road",
        "corridors": ["100 Feet Road", "Old Airport Road", "CMH Road"],
        "tech_parks": ["Bagmane Tech Park"]
    },
    "whitefield": {
        "display_name": "Whitefield",
        "zone": "East Suburb",
        "coords": (12.9698, 77.7500),
        "nearest_metro": ("Whitefield (Kadugodi)", "Purple", 0.0),
        "bus_stop": "ITPL / Hope Farm Channasandra",
        "corridors": ["ITPL Main Road", "Varthur Road", "Whitefield Main Road"],
        "tech_parks": ["ITPL", "EPIP Zone", "Prestige Shantiniketan"]
    },
    "hsr_layout": {
        "display_name": "HSR Layout",
        "zone": "South-East",
        "coords": (12.9121, 77.6446),
        "nearest_metro": ("Central Silk Board", "Yellow", 1.8),
        "bus_stop": "HSR BDA Complex / Silk Board",
        "corridors": ["Outer Ring Road", "Hosur Road", "27th Main"],
        "tech_parks": ["HSR Sector 1 Startups Hub"]
    },
    "bellandur": {
        "display_name": "Bellandur / ORR",
        "zone": "Outer Ring Road East",
        "coords": (12.9304, 77.6784),
        "nearest_metro": ("Baiyappanahalli", "Purple", 7.5),
        "bus_stop": "Ecospace Bus Stop / Bellandur Gate",
        "corridors": ["Outer Ring Road (ORR)", "Sarjapur Road"],
        "tech_parks": ["Ecospace", "EcoWorld", "Cessna Business Park"]
    },
    "marathahalli": {
        "display_name": "Marathahalli",
        "zone": "East",
        "coords": (12.9591, 77.6974),
        "nearest_metro": ("KR Puram", "Purple", 4.2),
        "bus_stop": "Marathahalli Bridge / Multiplex",
        "corridors": ["Outer Ring Road", "Old Airport Road", "Varthur Road"],
        "tech_parks": ["Prestige Tech Park", "Kalyani Tech Park"]
    },
    "electronic_city": {
        "display_name": "Electronic City",
        "zone": "South Suburb",
        "coords": (12.8452, 77.6602),
        "nearest_metro": ("Electronic City", "Yellow", 0.0),
        "bus_stop": "Infosys Toll Gate / Wipro Gate 1",
        "corridors": ["Hosur Road", "NICE Road", "Electronic City Elevated Expressway"],
        "tech_parks": ["Infosys Campus", "Wipro Campus", "Cyber Park"]
    },
    "hebbal": {
        "display_name": "Hebbal",
        "zone": "North",
        "coords": (13.0358, 77.5970),
        "nearest_metro": ("Yeshwantpur", "Green", 5.0),
        "bus_stop": "Hebbal Flyover Bus Stop",
        "corridors": ["Bellary Road (NH 44)", "Outer Ring Road"],
        "tech_parks": ["Manyata Tech Park", "Kirloskar Tech Park"]
    },
    "manyata": {
        "display_name": "Manyata Tech Park / Nagavara",
        "zone": "North-East",
        "coords": (13.0450, 77.6200),
        "nearest_metro": ("Baiyappanahalli", "Purple", 7.0),
        "bus_stop": "Manyata Tech Park Gate 1 / 2",
        "corridors": ["Outer Ring Road (North)", "Thanisandra Main Road"],
        "tech_parks": ["Manyata Embassy Business Park"]
    },
    "majestic": {
        "display_name": "Majestic (KSR / Kempegowda)",
        "zone": "Central",
        "coords": (12.9774, 77.5708),
        "nearest_metro": ("Nadaprabhu Kempegowda Majestic", "Interchange (Purple/Green)", 0.0),
        "bus_stop": "Kempegowda Bus Station (BMTC Platform 1-30)",
        "corridors": ["Subhash Nagar", "KG Road", "Dhanvantri Road"],
        "tech_parks": ["City Railway Station", "KSRTC / BMTC Central Terminus"]
    },
    "mg_road": {
        "display_name": "MG Road / CBD",
        "zone": "Central",
        "coords": (12.9756, 77.6066),
        "nearest_metro": ("MG Road", "Purple", 0.0),
        "bus_stop": "Anil Kumble Circle / Brigade Road",
        "corridors": ["MG Road", "Brigade Road", "Residency Road"],
        "tech_parks": ["UB City", "Raheja Towers"]
    },
    "airport": {
        "display_name": "Kempegowda International Airport (BLR)",
        "zone": "Far North",
        "coords": (13.1986, 77.7066),
        "nearest_metro": ("Yeshwantpur", "Green", 28.0),
        "bus_stop": "Terminal 1 & Terminal 2 Vayu Vajra Bay",
        "corridors": ["Bellary Road / Airport Expressway (NH 44)", "SH 104 (Bagalur)"],
        "tech_parks": ["KIA Logistics Park", "Aerotropolis"]
    },
    "jp_nagar": {
        "display_name": "JP Nagar",
        "zone": "South",
        "coords": (12.9063, 77.5857),
        "nearest_metro": ("JP Nagar", "Green", 0.0),
        "bus_stop": "JP Nagar 6th Phase / Banashankari TTMC",
        "corridors": ["Bannerghatta Road", "Outer Ring Road (South)", "Kanakapura Road"],
        "tech_parks": ["Kalyani Magnum"]
    },
    "banashankari": {
        "display_name": "Banashankari",
        "zone": "South-West",
        "coords": (12.9255, 77.5468),
        "nearest_metro": ("Banashankari", "Green", 0.0),
        "bus_stop": "Banashankari TTMC",
        "corridors": ["Outer Ring Road", "Kanakapura Road"],
        "tech_parks": ["South Bengaluru Commercial Hub"]
    }
}

# BMTC Bus Network & Schedules with Intermediate Stops
BMTC_BUS_ROUTES: List[Dict[str, Any]] = [
    {
        "route_no": "500-D",
        "route_name": "Hebbal ⇄ Central Silk Board (via ORR)",
        "service_type": "AC Vajra Volvo & Ordinary",
        "corridor": "Outer Ring Road (ORR)",
        "connects": ["hebbal", "manyata", "marathahalli", "bellandur", "hsr_layout", "koramangala"],
        "frequency_minutes": 5,
        "fare_ordinary_inr": 25,
        "fare_ac_vajra_inr": 45,
        "highlights": "Dedicated ORR bus lane; runs every 5 mins during peak hours.",
        "stops": [
            "Central Silk Board", "HSR Layout BDA Complex", "HSR Sector 2", "Agara Junction",
            "Iblur Gate", "Bellandur Gate", "Ecospace Tech Park", "Devarabisanahalli",
            "Kadubeesanahalli", "Marathahalli Bridge", "Karthik Nagar", "Doddanekundi",
            "Mahadevapura", "Tin Factory / KR Puram", "Kasturi Nagar", "Ramamurthy Nagar",
            "Babusapalya", "Kalyan Nagar", "Hennur Cross", "Nagavara Junction",
            "Manyata Tech Park Gate 1", "Hebbal Flyover"
        ]
    },
    {
        "route_no": "500-CA",
        "route_name": "Banashankari / Silk Board ⇄ ITPL / Whitefield (via ORR)",
        "service_type": "AC Vajra Volvo & Ordinary",
        "corridor": "Outer Ring Road to Whitefield",
        "connects": ["banashankari", "jp_nagar", "koramangala", "hsr_layout", "bellandur", "marathahalli", "whitefield"],
        "frequency_minutes": 7,
        "fare_ordinary_inr": 30,
        "fare_ac_vajra_inr": 50,
        "highlights": "Direct tech connection from South Bangalore to ITPL.",
        "stops": [
            "Banashankari TTMC", "Sangam Circle", "Jayadeva Hospital", "BTM Layout Water Tank",
            "Central Silk Board", "HSR Layout Sector 2", "Agara Junction", "Bellandur Gate",
            "Ecospace", "Devarabisanahalli", "Kadubeesanahalli", "Marathahalli Multiplex",
            "Kundalahalli Gate", "CMRIT College", "Graphite India", "ITPL Main Gate", "Hope Farm Whitefield"
        ]
    },
    {
        "route_no": "KIA-9",
        "route_name": "Kempegowda Bus Station (Majestic) ⇄ BLR Airport",
        "service_type": "Vayu Vajra Premium AC",
        "corridor": "Bellary Road Expressway",
        "connects": ["majestic", "hebbal", "airport"],
        "frequency_minutes": 15,
        "fare_ordinary_inr": 120,
        "fare_ac_vajra_inr": 260,
        "highlights": "Luggage assistance, free Wi-Fi, air-conditioned airport express.",
        "stops": [
            "Kempegowda Bus Station (Majestic)", "Anand Rao Circle", "Cauvery Theater",
            "Mekhri Circle", "Hebbal Flyover", "Kodigehalli Gate", "Jakkur Cross",
            "Allalasandra / Yelahanka Bypass", "Kogilu Cross", "Bagalur Cross", "Chikkajala",
            "Trumpet Interchange", "Terminal 1 (BLR Airport)", "Terminal 2 (BLR Airport)"
        ]
    },
    {
        "route_no": "KIA-8",
        "route_name": "Electronic City ⇄ BLR Airport (via Silk Board & Hebbal)",
        "service_type": "Vayu Vajra Premium AC",
        "corridor": "Hosur Road to Airport Expressway",
        "connects": ["electronic_city", "hsr_layout", "marathahalli", "hebbal", "airport"],
        "frequency_minutes": 25,
        "fare_ordinary_inr": 150,
        "fare_ac_vajra_inr": 310,
        "highlights": "Direct airport connector from South tech campuses.",
        "stops": [
            "Electronic City Toll Gate", "Hosa Road", "Kudlu Gate", "Bommanahalli",
            "Central Silk Board", "Agara Junction", "Bellandur", "Marathahalli Bridge",
            "Tin Factory", "Kalyan Nagar", "Hebbal Flyover", "Yelahanka", "Trumpet Interchange", "Airport Terminals"
        ]
    },
    {
        "route_no": "335-E",
        "route_name": "Kempegowda Bus Station (Majestic) ⇄ Kadugodi / Whitefield",
        "service_type": "AC Vajra Volvo",
        "corridor": "Old Airport Road & Varthur",
        "connects": ["majestic", "mg_road", "indiranagar", "marathahalli", "whitefield"],
        "frequency_minutes": 10,
        "fare_ordinary_inr": 25,
        "fare_ac_vajra_inr": 45,
        "highlights": "Connects CBD to Indiranagar and Whitefield via Old Airport Road.",
        "stops": [
            "Kempegowda Bus Station", "Corporation", "Richmond Circle", "Mayo Hall / MG Road",
            "Trinity Circle", "Domlur Flyover", "Manipal Hospital", "HAL Main Gate",
            "Marathahalli Bridge", "Kundalahalli Gate", "Varthur Kodi", "Whitefield Post Office", "Kadugodi Bus Stand"
        ]
    },
    {
        "route_no": "356-C",
        "route_name": "Kempegowda Bus Station (Majestic) ⇄ Electronic City Wipro Gate",
        "service_type": "AC Vajra Volvo & Ordinary",
        "corridor": "Hosur Road Elevated Tollway",
        "connects": ["majestic", "koramangala", "hsr_layout", "electronic_city"],
        "frequency_minutes": 8,
        "fare_ordinary_inr": 25,
        "fare_ac_vajra_inr": 40,
        "highlights": "Takes Electronic City elevated tollway to skip Silk Board crawl.",
        "stops": [
            "Kempegowda Bus Station", "Town Hall", "Lalbagh Main Gate", "Dairy Circle",
            "St. John's Hospital", "Koramangala Water Tank", "Central Silk Board", "Roopena Agrahara",
            "Bommanahalli", "Kudlu Gate", "Hosa Road", "Electronic City Toll Gate", "Wipro Gate 1"
        ]
    },
    {
        "route_no": "G-4",
        "route_name": "Brigade Road / MG Road ⇄ Bannerghatta National Park (Big10)",
        "service_type": "Suvarna Ordinary & AC",
        "corridor": "Bannerghatta Road",
        "connects": ["mg_road", "koramangala", "jp_nagar"],
        "frequency_minutes": 10,
        "fare_ordinary_inr": 20,
        "fare_ac_vajra_inr": 35,
        "highlights": "Big10 arterial bus service with high frequency.",
        "stops": [
            "Brigade Road Junction", "Hosur Road", "Adugodi Police Quarters", "Forum Mall / Dairy Circle",
            "Jayadeva Hospital", "Vega City Mall", "Gopalan Mall", "Meenakshi Temple", "Gottigere", "Bannerghatta National Park"
        ]
    }
]

# Accurate Coordinates for Key Metro Stations & Bus Stops for Map Visualizations
METRO_STATION_COORDS: Dict[str, tuple] = {
    # Purple Line
    "Whitefield (Kadugodi)": (12.9960, 77.7600),
    "Channasandra": (12.9920, 77.7560),
    "Kadugodi Tree Park": (12.9890, 77.7530),
    "Hopefarm Channasandra": (12.9860, 77.7500),
    "Hoodi": (12.9910, 77.7170),
    "Garudachar Palya": (12.9940, 77.7020),
    "Singayyanapalya": (12.9960, 77.6890),
    "KR Puram": (12.9972, 77.6756),
    "Benniganahalli": (12.9940, 77.6620),
    "Baiyappanahalli": (12.9910, 77.6520),
    "Swami Vivekananda Road": (12.9860, 77.6440),
    "Indiranagar": (12.9780, 77.6380),
    "Halasuru": (12.9760, 77.6270),
    "Trinity": (12.9730, 77.6170),
    "MG Road": (12.9756, 77.6066),
    "Cubbon Park": (12.9810, 77.5970),
    "Dr. BR Ambedkar Vidhana Soudha": (12.9790, 77.5920),
    "Sir M Visvesvaraya Central College": (12.9770, 77.5840),
    "Nadaprabhu Kempegowda Majestic": (12.9774, 77.5708),
    "City Railway Station": (12.9770, 77.5670),
    "Magadi Road": (12.9750, 77.5550),
    "Hosahalli": (12.9740, 77.5450),
    "Vijayanagar": (12.9690, 77.5370),
    "Attiguppe": (12.9620, 77.5330),
    "Deepanjali Nagar": (12.9520, 77.5300),
    "Mysuru Road": (12.9480, 77.5180),
    "Kengeri": (12.9090, 77.4780),
    "Challaghatta": (12.9080, 77.4850),
    # Green Line
    "Madavara": (13.0640, 77.4850),
    "Nagasandra": (13.0480, 77.4990),
    "Dasarahalli": (13.0430, 77.5120),
    "Jalahalli": (13.0390, 77.5200),
    "Peenya": (13.0330, 77.5250),
    "Goraguntepalya": (13.0280, 77.5410),
    "Yeshwantpur": (13.0230, 77.5500),
    "Sandal Soap Factory": (13.0150, 77.5530),
    "Rajajinagar": (12.9980, 77.5550),
    "Chickpete": (12.9700, 77.5740),
    "Krishna Rajendra Market": (12.9630, 77.5750),
    "National College": (12.9510, 77.5730),
    "Lalbagh": (12.9460, 77.5800),
    "South End Circle": (12.9370, 77.5800),
    "Jayanagar": (12.9300, 77.5800),
    "Rashtreeya Vidyalaya Road": (12.9210, 77.5800),
    "Banashankari": (12.9150, 77.5730),
    "JP Nagar": (12.9063, 77.5857),
    "Silk Institute": (12.8620, 77.5250),
    # Yellow Line
    "Jayadeva Hospital": (12.9180, 77.5980),
    "BTM Layout": (12.9160, 77.6100),
    "Central Silk Board": (12.9172, 77.6228),
    "Bommanahalli": (12.9030, 77.6260),
    "Electronic City": (12.8452, 77.6602),
    "Bommasandra": (12.8160, 77.6920)
}

# Accurate Coordinates for Key Bus Stops for Map Visualizations
BUS_STOP_COORDS: Dict[str, tuple] = {
    "Central Silk Board": (12.9172, 77.6228),
    "HSR Layout BDA Complex": (12.9116, 77.6388),
    "HSR Layout Sector 2": (12.9140, 77.6500),
    "HSR Sector 2": (12.9140, 77.6500),
    "Agara Junction": (12.9230, 77.6540),
    "Iblur Gate": (12.9265, 77.6680),
    "Bellandur Gate": (12.9280, 77.6740),
    "Bellandur": (12.9280, 77.6740),
    "Ecospace Tech Park": (12.9260, 77.6830),
    "Ecospace": (12.9260, 77.6830),
    "Devarabisanahalli": (12.9320, 77.6910),
    "Kadubeesanahalli": (12.9350, 77.6890),
    "Marathahalli Bridge": (12.9591, 77.6974),
    "Marathahalli Multiplex": (12.9591, 77.6974),
    "Karthik Nagar": (12.9720, 77.7010),
    "Doddanekundi": (12.9780, 77.7020),
    "Mahadevapura": (12.9890, 77.6950),
    "Tin Factory / KR Puram": (12.9972, 77.6756),
    "Tin Factory": (12.9972, 77.6756),
    "Kasturi Nagar": (13.0030, 77.6620),
    "Ramamurthy Nagar": (13.0120, 77.6640),
    "Babusapalya": (13.0200, 77.6520),
    "Kalyan Nagar": (13.0250, 77.6440),
    "Hennur Cross": (13.0290, 77.6360),
    "Nagavara Junction": (13.0380, 77.6250),
    "Manyata Tech Park Gate 1": (13.0450, 77.6200),
    "Hebbal Flyover": (13.0358, 77.5970),
    "Banashankari TTMC": (12.9255, 77.5468),
    "Jayadeva Hospital": (12.9180, 77.5980),
    "Kundalahalli Gate": (12.9660, 77.7120),
    "Graphite India": (12.9790, 77.7220),
    "ITPL Main Gate": (12.9860, 77.7380),
    "Hope Farm Whitefield": (12.9860, 77.7500),
    "Kempegowda Bus Station (Majestic)": (12.9774, 77.5708),
    "Kempegowda Bus Station": (12.9774, 77.5708),
    "Mekhri Circle": (13.0080, 77.5850),
    "Yelahanka Bypass": (13.1000, 77.5960),
    "Terminal 1 (BLR Airport)": (13.1986, 77.7066),
    "Terminal 2 (BLR Airport)": (13.1986, 77.7066),
    "Domlur Flyover": (12.9610, 77.6380),
    "Manipal Hospital": (12.9590, 77.6480),
    "HAL Main Gate": (12.9570, 77.6640),
    "Electronic City Toll Gate": (12.8480, 77.6680),
    "Wipro Gate 1": (12.8452, 77.6602)
}

# Real-time Bengaluru Weather Status
BENGALURU_WEATHER_CURRENT = {
    "temperature_c": 26.5,
    "condition": "Cloudy with Intermittent Thunderstorms",
    "rainfall_mm": 18.2,
    "humidity_pct": 82,
    "wind_speed_kmh": 16,
    "monsoon_risk_level": "MODERATE TO HIGH (Yellow Alert)",
    "waterlogging_advisory": "Waterlogging active along ORR underpasses (Kadubeesanahalli) and Hebbal down-ramp.",
    "transit_impact": "Cab surge 1.6x-2.1x active; surface road speeds reduced by 35-45%; Namma Metro 100% unaffected."
}

# Notorious Bengaluru Bottlenecks & Choke Points
CHOKEPOINTS: Dict[str, Dict[str, Any]] = {
    "silk_board": {
        "name": "Central Silk Board Junction",
        "base_delay_minutes": 35,
        "peak_congestion_index": 9.6,
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

# Namma Metro Lines & Detailed Fare System
METRO_LINES = {
    "Purple": {
        "name": "Purple Line (East-West Corridor)",
        "color": "#9333ea",
        "fare_token_min": 10,
        "fare_token_max": 60,
        "smart_card_discount": 0.05,  # 5% discount on WhatsApp QR / Namma Metro Card
        "peak_headway_minutes": 4,
        "stations": [
            "Whitefield (Kadugodi)", "Channasandra", "Kadugodi Tree Park", "Hopefarm Channasandra",
            "Hoodi", "Garudachar Palya", "Singayyanapalya", "KR Puram", "Benniganahalli",
            "Baiyappanahalli", "Swami Vivekananda Road", "Indiranagar", "Halasuru", "Trinity",
            "MG Road", "Cubbon Park", "Dr. BR Ambedkar Vidhana Soudha", "Sir M Visvesvaraya Central College",
            "Nadaprabhu Kempegowda Majestic", "City Railway Station", "Magadi Road", "Hosahalli",
            "Vijayanagar", "Attiguppe", "Deepanjali Nagar", "Mysuru Road", "Pantharapalya",
            "Nayandahalli", "Rajarajeshwari Nagar", "Jnanabharathi", "Pattanagere", "Kengeri Bus Terminal",
            "Kengeri", "Challaghatta"
        ]
    },
    "Green": {
        "name": "Green Line (North-South Corridor)",
        "color": "#16a34a",
        "fare_token_min": 10,
        "fare_token_max": 60,
        "smart_card_discount": 0.05,
        "peak_headway_minutes": 5,
        "stations": [
            "Madavara", "Chikkabidarakallu", "Manjunathanagar", "Nagasandra", "Dasarahalli",
            "Jalahalli", "Peenya Industry", "Peenya", "Goraguntepalya", "Yeshwantpur",
            "Sandal Soap Factory", "Mahalakshmi", "Rajajinagar", "Kuvempu Road", "Srirampura",
            "Sampige Road", "Nadaprabhu Kempegowda Majestic", "Chickpete", "Krishna Rajendra Market",
            "National College", "Lalbagh", "South End Circle", "Jayanagar", "Rashtreeya Vidyalaya Road",
            "Banashankari", "Jaya Prakash Nagar", "Yelachenahalli", "Konanakunte Cross",
            "Doddakallasandra", "Vajarahalli", "Thalaghattapura", "Silk Institute"
        ]
    },
    "Yellow": {
        "name": "Yellow Line (RV Road to Bommasandra)",
        "color": "#ca8a04",
        "fare_token_min": 10,
        "fare_token_max": 50,
        "smart_card_discount": 0.05,
        "peak_headway_minutes": 6,
        "stations": [
            "Rashtreeya Vidyalaya Road", "Ragigudda", "Jayadeva Hospital", "BTM Layout",
            "Central Silk Board", "Bommanahalli", "Hongasandra", "Kudlu Gate", "Singasandra",
            "Hosa Road", "Beratena Agrahara", "Electronic City", "Infosys Foundation Konappana Agrahara",
            "Huskur Road", "Hebbagodi", "Bommasandra"
        ]
    }
}

# Active Bengaluru Road Construction, BBMP Road Repairs, & BMRCL Metro Work Zones
BENGALURU_ROAD_REPAIRS = [
    {
        "id": "CSB-METRO-01",
        "name": "Central Silk Board Interchange",
        "coords": (12.9172, 77.6228),
        "agency": "BMRCL / BBMP",
        "work_type": "Metro Blue Line Phase-2A Pier Work & Double-Decker Flyover Ramp",
        "severity": "CRITICAL",
        "lanes_affected": "3 lanes narrowed down to 1 lane on Hosur Road ramp",
        "delay_impact_mins": 35,
        "recommended_bypass": "Take Madiwala Market 16th Main Road inner corridor or Yellow Line Metro",
        "completion_target": "Q4 2026"
    },
    {
        "id": "ECO-BWSSB-02",
        "name": "Ecospace - Bellandur Outer Ring Road",
        "coords": (12.9260, 77.6830),
        "agency": "BWSSB",
        "work_type": "Cauvery Water Supply Stage V Pipeline Trenching & Road Digging",
        "severity": "HIGH",
        "lanes_affected": "Service road closed completely; left lane on main carriageway barricaded",
        "delay_impact_mins": 30,
        "recommended_bypass": "Use BMTC 500-D bus lane or bypass via Haralur Road towards Sarjapur",
        "completion_target": "Active Work Zone"
    },
    {
        "id": "KADU-BBMP-03",
        "name": "Kadubeesanahalli ORR Underpass",
        "coords": (12.9350, 77.6890),
        "agency": "BBMP Road Infrastructure",
        "work_type": "Stormwater Drain Culvert Desilting & Pavement Resurfacing",
        "severity": "MODERATE",
        "lanes_affected": "Slow crawl due to gravel and surface height difference; speed limited to 10 km/h",
        "delay_impact_mins": 20,
        "recommended_bypass": "Use surface-level roundabout above underpass or Marathahalli outer link",
        "completion_target": "Under Active Maintenance"
    },
    {
        "id": "MARATH-ROB-04",
        "name": "Marathahalli Railway Overbridge (ROB)",
        "coords": (12.9591, 77.6974),
        "agency": "BBMP / South Western Railway",
        "work_type": "Expansion Joint Replacement & Bituminous Concrete Resurfacing",
        "severity": "HIGH",
        "lanes_affected": "Single lane traffic movement over bridge towards Whitefield",
        "delay_impact_mins": 25,
        "recommended_bypass": "Kundalahalli Gate Underpass via Old Airport Road",
        "completion_target": "Night Maintenance Active"
    },
    {
        "id": "TIN-BMRCL-05",
        "name": "Tin Factory / Benniganahalli Junction",
        "coords": (12.9972, 77.6756),
        "agency": "BMRCL / BBMP",
        "work_type": "Pedestrian Skywalk Girder Erection & Kasturi Nagar Flyover Landing Remodeling",
        "severity": "CRITICAL",
        "lanes_affected": "Major lane merge bottleneck from Old Madras Road into ORR",
        "delay_impact_mins": 35,
        "recommended_bypass": "Use Namma Metro Purple Line from Baiyappanahalli direct to KR Puram/Whitefield",
        "completion_target": "Phase-2 Work"
    },
    {
        "id": "PEENYA-NHAI-06",
        "name": "Goraguntepalya / Peenya Elevated Corridor",
        "coords": (13.0280, 77.5350),
        "agency": "NHAI & BBMP",
        "work_type": "Pre-stressed Cable Tensioning & Flyover Pier Bearing Retrofitting",
        "severity": "HIGH",
        "lanes_affected": "Heavy goods vehicles diverted to surface level, creating heavy gridlock on 8th Mile",
        "delay_impact_mins": 30,
        "recommended_bypass": "Green Line Metro (Nagasandra to Majestic) bypassing Tumkur Road completely",
        "completion_target": "Ongoing Structural Retrofit"
    },
    {
        "id": "SONY-BBMP-07",
        "name": "Sony World Signal / Koramangala 100ft Road",
        "coords": (12.9352, 77.6245),
        "agency": "BBMP",
        "work_type": "White-Topping Concrete Curing & Stormwater Side Drain Widening",
        "severity": "MODERATE",
        "lanes_affected": "Southbound lane restricted; alternating one-way traffic management by BTP",
        "delay_impact_mins": 18,
        "recommended_bypass": "Use Intermediate Ring Road (Domlur-Koramangala link) or 80ft Road",
        "completion_target": "White-Topping Project"
    },
    {
        "id": "KUNDAL-GAIL-08",
        "name": "Kundalahalli to Hoodi Junction",
        "coords": (12.9730, 77.7180),
        "agency": "GAIL Gas & BESCOM",
        "work_type": "Underground Gas Pipeline Trenching & High-Tension Cable Ducting",
        "severity": "MODERATE",
        "lanes_affected": "Unpaved trenches on road shoulders, rough gravel surface",
        "delay_impact_mins": 20,
        "recommended_bypass": "Divert via ITPL Main Road or Hoodi Metro Station link",
        "completion_target": "Utility Shifting"
    }
]
