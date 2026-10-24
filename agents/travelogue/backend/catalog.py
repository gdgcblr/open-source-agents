"""Workshop fixtures. Seasonal notes need verification before live publication."""

COUNTRIES = [
    {"code": "JP", "name": "Japan", "flag": "JP", "subtitle": "Between old worlds and new", "color": "#d09384", "source": "https://www.japan.travel/en/", "places": [
        ("kyoto", "Kyoto", "Temples, quiet lanes & little rituals", "March–May · October–November", 135.768, 35.012, "temples"),
        ("tokyo", "Tokyo", "Neon nights & neighborhood discoveries", "March–May · October–November", 139.692, 35.689, "city"),
        ("fuji", "Mount Fuji", "A mountain that stays with you", "July–August for climbing; verify access", 138.727, 35.361, "mountain")
    ]},
    {"code": "IN", "name": "India", "flag": "IN", "subtitle": "A thousand stories, one journey", "color": "#d3aa70", "source": "https://www.incredibleindia.gov.in/", "places": [
        ("udaipur", "Udaipur", "Lake light & palaces in pastel", "October–March", 73.683, 24.585, "palace"),
        ("jaipur", "Jaipur", "Pink walls & golden afternoons", "October–March", 75.787, 26.912, "palace"),
        ("munnar", "Munnar", "Slow mornings above the tea gardens", "October–March", 77.062, 10.089, "mountain")
    ]},
    {"code": "IT", "name": "Italy", "flag": "IT", "subtitle": "Take the scenic way home", "color": "#89a997", "source": "https://www.italia.it/en", "places": [
        ("rome", "Rome", "Ancient streets & unhurried lunches", "April–May · September–October", 12.496, 41.903, "city"),
        ("florence", "Florence", "Art around every corner", "April–June · September–October", 11.255, 43.769, "palace"),
        ("amalfi", "Amalfi Coast", "Cliffside colors & the open sea", "May–June · September", 14.603, 40.634, "coast")
    ]},
    {"code": "FR", "name": "France", "flag": "FR", "subtitle": "Make room for a little wonder", "color": "#92a4c1", "source": "https://www.france.fr/en/", "places": [
        ("paris", "Paris", "Long walks & small patisseries", "April–June · September–October", 2.352, 48.857, "city"),
        ("provence", "Provence", "Hilltop villages & summer color", "June–July for lavender; varies locally", 5.37, 43.30, "mountain"),
        ("nice", "Nice", "Salt air on the French Riviera", "May–June · September", 7.262, 43.711, "coast")
    ]},
    {"code": "TH", "name": "Thailand", "flag": "TH", "subtitle": "A softer kind of adventure", "color": "#b6ae7e", "source": "https://www.tourismthailand.org/", "places": [
        ("bangkok", "Bangkok", "Golden temples & river evenings", "November–February", 100.502, 13.756, "temples"),
        ("chiang-mai", "Chiang Mai", "Mountain air & old city mornings", "November–February; check air quality", 98.985, 18.789, "mountain"),
        ("krabi", "Krabi", "Limestone silhouettes & blue water", "November–April; verify local conditions", 98.907, 8.086, "coast")
    ]}
]

PLACES = {}
for country in COUNTRIES:
    records = []
    for ident, name, description, season, lon, lat, scene in country["places"]:
        place = dict(id=ident, name=name, description=description, season=season,
                     lon=lon, lat=lat, scene=scene, country=country["code"],
                     color=country["color"], source=country["source"],
                     evidence_status="curated_unverified", image=f"/art/{scene}.svg")
        records.append(place)
        PLACES[ident] = place
    country["places"] = records

SEED_ENTRIES = [
    dict(id="memory-kyoto", country="JP", place_id="kyoto", title="The art of getting a little lost",
         visited_on="2026-04-12", body="We took the wrong turn after breakfast and found a lane lined with tiny gardens. An old shopkeeper pointed us toward the river. We never made it to the temple on our list. Somehow, it was the best day of the trip.\n\nA reminder to leave a little room in every itinerary for the unexpected.", published=False, tags="Slow travel,Little moments"),
    dict(id="memory-udaipur", country="IN", place_id="udaipur", title="A city painted in lake light",
         visited_on="2026-02-08", body="The city woke slowly. We sat by the lake while the first light turned the buildings gold. No agenda, just chai and a view we didn't want to leave.\n\nI brought home a notebook, a handful of photographs, and a promise to come back.", published=False, tags="Architecture,Golden hour"),
    dict(id="memory-amalfi", country="IT", place_id="amalfi", title="Somewhere between sea and sky",
         visited_on="2025-09-19", body="A winding road, a very small bus, and a sea that kept changing its shade of blue. We stopped for lunch longer than we'd planned.\n\nSome places ask you to slow down. This was one of them.", published=False, tags="Coastal days,Food")
]
