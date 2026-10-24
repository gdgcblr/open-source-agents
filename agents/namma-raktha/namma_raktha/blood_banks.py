"""
Curated 24/7 Bengaluru Blood Banks and Component Separation Centers.
Includes zones, contact hotlines, metro proximity, and real-world Bengaluru traffic advisories.
"""

from typing import List
from .models import BangaloreZone, BloodBank


BENGALURU_BLOOD_BANKS: List[BloodBank] = [
    # East Bengaluru
    BloodBank(
        name="Rotary TTK Blood Centre (BMST)",
        zone=BangaloreZone.EAST,
        area="Indiranagar",
        address="New Thippasandra Main Road, HAL 3rd Stage, Indiranagar, Bengaluru - 560075",
        phone="+91 80 2528 6077 / +91 80 2528 7903",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Rotary+TTK+Blood+Bank+Indiranagar+Bengaluru",
        metro_proximity="~1.8 km from Indiranagar Metro Station (Purple Line)",
        peak_traffic_advisory="Avoid 100ft Road during 5:30-8:30 PM. Approach via Old Airport Road or Suranjandas Road."
    ),
    BloodBank(
        name="Manipal Hospital Blood Centre",
        zone=BangaloreZone.EAST,
        area="HAL Old Airport Road",
        address="98, HAL Old Airport Road, Kodihalli, Bengaluru - 560017",
        phone="+91 80 2502 4444 / +91 80 2502 3344",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Manipal+Hospital+Old+Airport+Road+Bengaluru",
        metro_proximity="~3.5 km from Indiranagar Metro (Purple Line) or direct bus from Domlur",
        peak_traffic_advisory="Domlur flyover & Kodihalli choke during evening hours. Use inner Leela Palace bypass."
    ),
    BloodBank(
        name="Vydehi Hospital Blood Centre",
        zone=BangaloreZone.EAST,
        area="Whitefield",
        address="82, EPIP Area, Whitefield, Bengaluru - 560066",
        phone="+91 80 4906 9000 / +91 80 2841 3381",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Vydehi+Hospital+Whitefield+Bengaluru",
        metro_proximity="Direct access via Nallurhalli / Sri Sathya Sai Hospital Metro (Purple Line)",
        peak_traffic_advisory="Hope Farm & ITPL main road traffic heavy. Use Purple Line Metro for quickest transit."
    ),

    # South Bengaluru
    BloodBank(
        name="Rashtrotthana Blood Centre",
        zone=BangaloreZone.SOUTH,
        area="Jayanagar",
        address="#7, Rashtrotthana Parishat, Near Ashoka Pillar, Jayanagar 1st Block, Bengaluru - 560011",
        phone="+91 80 2663 7841 / +91 80 2664 5314",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Rashtrotthana+Blood+Centre+Jayanagar+Bengaluru",
        metro_proximity="~1.2 km from South End Circle Metro Station (Green Line)",
        peak_traffic_advisory="Smooth access via Lalbagh Fort Road. Ashoka Pillar circle has mild morning congestion."
    ),
    BloodBank(
        name="NIMHANS Blood Centre",
        zone=BangaloreZone.SOUTH,
        area="Hosur Road / Dairy Circle",
        address="National Institute of Mental Health and Neuro Sciences, Hosur Road, Bengaluru - 560029",
        phone="+91 80 2699 5155 / +91 80 2699 5156",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="NIMHANS+Blood+Bank+Hosur+Road+Bengaluru",
        metro_proximity="Underground Dairy Circle Metro Station (Pink Line) / ~3 km from Lalbagh (Green Line)",
        peak_traffic_advisory="Dairy Circle bottleneck can cause 20-30 min delays. Use Wilson Garden interior route."
    ),
    BloodBank(
        name="Kidwai Memorial Institute of Oncology Blood Bank",
        zone=BangaloreZone.SOUTH,
        area="Hosur Road / Dr. M.H. Marigowda Road",
        address="Dr. M.H. Marigowda Road, Near Dairy Circle, Bengaluru - 560029",
        phone="+91 80 2609 4000 / +91 80 2609 4118",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Kidwai+Memorial+Blood+Bank+Bengaluru",
        metro_proximity="~1 km from Dairy Circle / 2.5 km from South End Circle (Green Line)",
        peak_traffic_advisory="Critical platelet center for oncology. High demand for SDP apheresis units."
    ),
    BloodBank(
        name="Sri Jayadeva Institute of Cardiovascular Sciences",
        zone=BangaloreZone.SOUTH,
        area="Bannerghatta Road / Jayanagar 9th Block",
        address="Bannerghatta Main Road, 9th Block, Jayanagar, Bengaluru - 560069",
        phone="+91 80 2297 7400 / +91 80 2297 7289",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Jayadeva+Hospital+Bannerghatta+Road+Bengaluru",
        metro_proximity="Directly accessible via Jayadeva Interchange Metro Station (Green & Yellow Lines)",
        peak_traffic_advisory="Jayadeva junction traffic has eased with the multi-level flyover; fast access via metro."
    ),
    BloodBank(
        name="Narayana Health City Blood Centre",
        zone=BangaloreZone.SOUTH,
        area="Electronic City / Bommasandra",
        address="258/A, Bommasandra Industrial Area, Anekal Taluk, Bengaluru - 560099",
        phone="+91 80 7122 2222 / +91 80 2783 5000",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Narayana+Health+City+Blood+Bank+Bommasandra+Bengaluru",
        metro_proximity="Accessible via Bommasandra Metro Station (Yellow Line)",
        peak_traffic_advisory="Use Electronic City Elevated Tollway to bypass Silk Board/Hosur Road surface traffic."
    ),

    # Central Bengaluru
    BloodBank(
        name="Victoria Hospital Blood Centre (BMCRI)",
        zone=BangaloreZone.CENTRAL,
        area="K.R. Market / Fort",
        address="Bangalore Medical College & Research Institute, Fort, K.R. Market, Bengaluru - 560002",
        phone="+91 80 2670 1150 / +91 80 2670 0451",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Victoria+Hospital+Blood+Bank+KR+Market+Bengaluru",
        metro_proximity="~400 meters from Krishna Rajendra Market Metro Station (Green Line)",
        peak_traffic_advisory="KR Market surface traffic is dense. HIGHLY RECOMMENDED to arrive via Green Line Metro."
    ),
    BloodBank(
        name="Indian Red Cross Society Karnataka Blood Centre",
        zone=BangaloreZone.CENTRAL,
        area="Race Course Road",
        address="#26, Red Cross Bhavan, 1st Floor, Race Course Road, Bengaluru - 560001",
        phone="+91 80 2226 8445 / +91 80 2226 4205",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Indian+Red+Cross+Society+Race+Course+Road+Bengaluru",
        metro_proximity="~1.2 km from Sir M. Visveshwaraya / Vidhana Soudha Metro (Purple Line)",
        peak_traffic_advisory="Central location with broad roads. Good connectivity from Majestic and Cantonment."
    ),
    BloodBank(
        name="Bowring & Lady Curzon Hospital Blood Bank",
        zone=BangaloreZone.CENTRAL,
        area="Shivajinagar",
        address="Hospital Road, Near Shivaji Nagar Bus Stand, Tasker Town, Bengaluru - 560001",
        phone="+91 80 2559 1362 / +91 80 2559 1325",
        is_24x7=True,
        has_apheresis=False,
        google_maps_query="Bowring+Hospital+Shivajinagar+Bengaluru",
        metro_proximity="~1.5 km from MG Road Metro (Purple Line) or Shivaji Nagar bus hub",
        peak_traffic_advisory="Shivajinagar commercial market traffic slow after 6 PM. Approach from Cantonment side."
    ),

    # North Bengaluru
    BloodBank(
        name="Aster CMI Hospital Blood Centre",
        zone=BangaloreZone.NORTH,
        area="Hebbal",
        address="#43/2, New Airport Road, NH 44, Sahakar Nagar, Hebbal, Bengaluru - 560092",
        phone="+91 80 4344 4444 / +91 80 4344 4555",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Aster+CMI+Hospital+Hebbal+Bengaluru",
        metro_proximity="Airport feeder corridor; Kodigehalli / Hebbal suburban link",
        peak_traffic_advisory="Hebbal Flyover merges can be very congested (8:30-11 AM & 6-9 PM). Use service road."
    ),
    BloodBank(
        name="M.S. Ramaiah Memorial Hospital Blood Centre",
        zone=BangaloreZone.NORTH,
        area="Mathikere / MSR Nagar",
        address="MSR Nagar, MSRIT Post, Mathikere, Bengaluru - 560054",
        phone="+91 80 2360 8888 / +91 80 2360 9999",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="MS+Ramaiah+Memorial+Hospital+Blood+Bank+Bengaluru",
        metro_proximity="~2.5 km from Sandal Soap Factory / Yeshwanthpur Metro (Green Line)",
        peak_traffic_advisory="Mathikere 80ft road has medium traffic. Accessible from BEL circle and Yeshwanthpur."
    ),

    # West Bengaluru
    BloodBank(
        name="K.C. General Hospital Blood Bank",
        zone=BangaloreZone.WEST,
        area="Malleshwaram",
        address="5th Cross Road, Malleshwaram, Bengaluru - 560003",
        phone="+91 80 2334 2371 / +91 80 2334 1771",
        is_24x7=True,
        has_apheresis=False,
        google_maps_query="KC+General+Hospital+Malleshwaram+Bengaluru",
        metro_proximity="~1.2 km from Sampige Road Metro Station (Green Line)",
        peak_traffic_advisory="Malleshwaram 8th Cross market hours cause traffic slowdowns; use Margosa Road."
    ),
    BloodBank(
        name="Fortis Hospital Blood Centre",
        zone=BangaloreZone.WEST,
        area="Rajajinagar",
        address="111, West of Chord Road, Opp. Rajajinagar 1st Block, Bengaluru - 560086",
        phone="+91 80 4330 0000 / +91 80 4330 0100",
        is_24x7=True,
        has_apheresis=True,
        google_maps_query="Fortis+Hospital+Rajajinagar+Bengaluru",
        metro_proximity="~600 meters from Mahalakshmi Metro Station (Green Line)",
        peak_traffic_advisory="West of Chord Road has moderate flow; very convenient Green Line metro walk."
    )
]


def match_blood_banks(zone: BangaloreZone, needs_apheresis: bool = False, max_results: int = 5) -> List[BloodBank]:
    """
    Returns prioritized blood banks based on patient zone, apheresis capability, and emergency proximity.
    """
    # 1. Match primary zone
    primary = [b for b in BENGALURU_BLOOD_BANKS if b.zone == zone]
    others = [b for b in BENGALURU_BLOOD_BANKS if b.zone != zone]

    # Prioritize apheresis if component is SDP
    if needs_apheresis:
        primary = sorted(primary, key=lambda b: not b.has_apheresis)
        others = sorted(others, key=lambda b: not b.has_apheresis)

    ordered = primary + others
    return ordered[:max_results]
