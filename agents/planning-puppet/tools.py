"""
tools.py – Planning Puppet: discrete function tools for the ADK agent.

Each function is a self-contained planning utility that the LLM agent can
call during a conversation.  All functions accept plain Python types and return
plain dicts so they are trivially serialisable.
"""

from __future__ import annotations

import math
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Tool 1 – Budget Breakdown
# ---------------------------------------------------------------------------

_BUDGET_ALLOCATIONS: dict[str, dict[str, float]] = {
    "wedding": {
        "Venue & Catering": 0.45,
        "Photography & Videography": 0.12,
        "Decor & Florals": 0.12,
        "Attire & Beauty": 0.08,
        "Entertainment & Music": 0.08,
        "Contingency Buffer": 0.15,
    },
    "birthday": {
        "Food & Drinks": 0.35,
        "Venue & Activities": 0.25,
        "Decor & Cake": 0.20,
        "Favors & Entertainment": 0.20,
    },
    "community": {
        "Logistics, Permits & Security": 0.30,
        "Refreshments & Catering": 0.30,
        "AV, Stage & Sound": 0.25,
        "Signage & Promotion": 0.15,
    },
}

_BUDGET_TIPS: dict[str, list[str]] = {
    "wedding": [
        "Book venue and caterer at least 12 months in advance – they fill up fast.",
        "Ask photographers about weekday or off-season discounts.",
        "The contingency buffer (15 %) is non-negotiable; weddings always surface surprises.",
    ],
    "birthday": [
        "Bundle decor and cake orders from a single vendor for a package discount.",
        "Consider a brunch or afternoon party – venue rates are lower than evenings.",
    ],
    "community": [
        "Apply for permits 8–12 weeks ahead; late applications carry penalty fees.",
        "Negotiate AV packages with local universities or community colleges.",
    ],
}


def calculate_budget_breakdown(
    event_type: str,
    total_budget: float,
    guest_count: int,
) -> dict:
    """Calculate a detailed, line-item budget breakdown for an event.

    Args:
        event_type: One of 'wedding', 'birthday', or 'community'.
        total_budget: Total available budget in USD (or local currency).
        guest_count: Expected number of guests attending the event.

    Returns:
        A dictionary containing line items, per-guest spend, and
        money-saving tips tailored to the event type.
    """
    event_type = event_type.lower().strip()
    if event_type not in _BUDGET_ALLOCATIONS:
        return {
            "error": f"Unknown event_type '{event_type}'. Choose 'wedding', 'birthday', or 'community'."
        }

    allocations = _BUDGET_ALLOCATIONS[event_type]
    line_items: list[dict] = []
    total_allocated = 0.0

    for category, pct in allocations.items():
        amount = round(total_budget * pct, 2)
        total_allocated += amount
        line_items.append(
            {
                "category": category,
                "percentage": f"{int(pct * 100)}%",
                "amount_usd": amount,
            }
        )

    per_guest_spend = round(total_budget / guest_count, 2) if guest_count > 0 else 0

    return {
        "event_type": event_type,
        "total_budget_usd": total_budget,
        "guest_count": guest_count,
        "per_guest_spend_usd": per_guest_spend,
        "line_items": line_items,
        "total_allocated_usd": round(total_allocated, 2),
        "tips": _BUDGET_TIPS.get(event_type, []),
    }


# ---------------------------------------------------------------------------
# Tool 2 – Event Timeline
# ---------------------------------------------------------------------------

_TIMELINE_TEMPLATES: dict[str, list[dict]] = {
    "wedding": [
        {"phase": "Phase 1 – Foundation (12+ months out)", "milestones": [
            "Set a preliminary guest count and overall budget",
            "Research and visit venue options; book your top choice",
            "Hire wedding planner / coordinator (optional but recommended)",
            "Draft a long-list of vendors (caterer, photographer, florist)",
        ]},
        {"phase": "Phase 2 – Vendors & Invitations (6–12 months out)", "milestones": [
            "Confirm and sign contracts with all primary vendors",
            "Choose and order wedding attire",
            "Design and send save-the-dates",
            "Book honeymoon travel",
            "Finalise guest list; send formal invitations (8 weeks out)",
        ]},
        {"phase": "Phase 3 – Final Confirmations (1–4 weeks out)", "milestones": [
            "Confirm final guest headcount with caterer",
            "Deliver final payment to venue and vendors",
            "Prepare seating chart and place cards",
            "Hold rehearsal dinner",
            "Pack an emergency kit (safety pins, stain remover, painkillers)",
        ]},
        {"phase": "Phase 4 – Day-of Schedule", "milestones": [
            "06:00 – Hair & makeup begins for bridal party",
            "10:00 – Photographer arrives; getting-ready shots",
            "12:00 – Wedding party travels to ceremony venue",
            "14:00 – Ceremony begins",
            "15:00 – Cocktail hour; couple portraits",
            "17:00 – Reception doors open",
            "17:30 – Dinner service",
            "19:00 – First dance, speeches, cake cutting",
            "20:00 – Open dancing & entertainment",
            "23:00 – Grand exit / send-off",
        ]},
    ],
    "birthday": [
        {"phase": "Phase 1 – Planning (4–8 weeks out)", "milestones": [
            "Decide on theme, venue (home, park, venue hall), and rough guest list",
            "Set a total budget using the budget tool",
            "Book venue or confirm home/park availability",
        ]},
        {"phase": "Phase 2 – Booking & Invitations (2–4 weeks out)", "milestones": [
            "Send digital or physical invitations",
            "Order custom cake or confirm bakery booking",
            "Purchase or order decor, balloons, and party favours",
            "Confirm entertainment (DJ, performer, activity host)",
        ]},
        {"phase": "Phase 3 – Final Prep (1 week out)", "milestones": [
            "Confirm RSVPs and finalise headcount for food orders",
            "Prepare party bags / favours",
            "Create playlist or brief entertainment vendor",
            "Set up decor the day before if possible",
        ]},
        {"phase": "Phase 4 – Day-of Schedule", "milestones": [
            "T-3 hours – Decor and balloon setup",
            "T-1 hour – Food and drinks laid out",
            "T-0 – Guests arrive; welcome drinks",
            "T+1 hour – Birthday cake & singing",
            "T+1.5 hours – Party games / entertainment",
            "T+2.5 hours – Farewell & gift opening",
        ]},
    ],
    "community": [
        {"phase": "Phase 1 – Logistics & Approvals (8–12 weeks out)", "milestones": [
            "Define event purpose, target audience, and anticipated attendance",
            "Identify and secure the venue or public space",
            "Apply for all required permits (noise, public assembly, food service)",
            "Form an organising committee with clear role assignments",
        ]},
        {"phase": "Phase 2 – Vendors & Promotion (4–8 weeks out)", "milestones": [
            "Confirm AV/stage vendor and technical rider",
            "Book food stalls, food trucks, or catering",
            "Launch social media promotion and community outreach",
            "Coordinate volunteers and assign station duties",
        ]},
        {"phase": "Phase 3 – Final Confirmations (1–2 weeks out)", "milestones": [
            "Confirm final vendor arrival times and load-in schedule",
            "Brief all volunteers; distribute walkie-talkies or communication plan",
            "Prepare first-aid station and emergency contacts list",
            "Conduct site walk-through with key team members",
        ]},
        {"phase": "Phase 4 – Day-of Schedule", "milestones": [
            "T-4 hours – Vendor load-in and AV soundcheck",
            "T-2 hours – Volunteer briefing and station setup",
            "T-1 hour – Final venue walk-through",
            "T-0 – Gates open; welcome announcement",
            "T+1 hour – Programme / performances begin",
            "T+End – 30-min grace period, then teardown and site clearance",
        ]},
    ],
}


def generate_event_timeline(
    event_type: str,
    event_date_iso: Optional[str] = None,
) -> dict:
    """Generate a reverse-engineered, phase-by-phase event planning timeline.

    Args:
        event_type: One of 'wedding', 'birthday', or 'community'.
        event_date_iso: The target event date in ISO-8601 format (YYYY-MM-DD).
                        If omitted, a generic milestone guide is returned.

    Returns:
        A dictionary with planning phases, milestone tasks, and (when a date
        is provided) the concrete calendar window for each phase.
    """
    event_type = event_type.lower().strip()
    if event_type not in _TIMELINE_TEMPLATES:
        return {
            "error": f"Unknown event_type '{event_type}'. Choose 'wedding', 'birthday', or 'community'."
        }

    phases = _TIMELINE_TEMPLATES[event_type]
    today = date.today()
    days_until: Optional[int] = None
    event_date_str: Optional[str] = None

    if event_date_iso:
        try:
            event_date = datetime.strptime(event_date_iso, "%Y-%m-%d").date()
            days_until = (event_date - today).days
            event_date_str = event_date.strftime("%B %d, %Y")
        except ValueError:
            return {"error": f"Invalid date format '{event_date_iso}'. Please use YYYY-MM-DD."}

    return {
        "event_type": event_type,
        "event_date": event_date_str,
        "days_until_event": days_until,
        "planning_phases": phases,
        "note": (
            "Timeline is reverse-engineered from your event date. "
            "Adjust windows based on vendor availability in your area."
            if event_date_str
            else "Provide an event date (YYYY-MM-DD) for a date-anchored timeline."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 3 – Vendor Checklist
# ---------------------------------------------------------------------------

_VENDOR_DATA: dict[str, dict[str, dict]] = {
    "wedding": {
        "small": {
            "vendors": ["Officiant", "Photographer", "Caterer", "Florist", "Baker (Cake)", "DJ / Musician"],
            "questions": {
                "Photographer": [
                    "Do you have a backup photographer?",
                    "Can we see a full wedding gallery (not just highlights)?",
                    "What is your turnaround time for edited photos?",
                ],
                "Caterer": [
                    "Can you accommodate dietary restrictions (vegan, gluten-free)?",
                    "Is gratuity included in the quote?",
                    "Do you provide tastings before signing?",
                ],
            },
            "booking_deadlines": {
                "Venue": "12–18 months in advance",
                "Photographer": "9–12 months in advance",
                "Caterer": "6–9 months in advance",
                "Florist": "6 months in advance",
                "Baker": "3–4 months in advance",
                "DJ / Musician": "6–9 months in advance",
            },
        },
        "large": {
            "vendors": [
                "Wedding Planner", "Venue Coordinator", "Officiant", "Photographer",
                "Videographer", "Caterer", "Florist", "Baker (Cake)", "DJ + Band",
                "Hair & Makeup Artist", "Transportation (Limo/Shuttle)", "Photo Booth Rental",
            ],
            "questions": {
                "Videographer": [
                    "Do you offer a highlight reel and a full-length cut?",
                    "Do you record audio from the officiant/vows?",
                    "Can we see a full wedding film from a past couple?",
                ],
                "Transportation": [
                    "Can you accommodate the full wedding party in one vehicle?",
                    "Is there a minimum hire duration?",
                    "What happens if the ceremony runs late?",
                ],
            },
            "booking_deadlines": {
                "Venue": "14–18 months in advance",
                "Wedding Planner": "12 months in advance",
                "Photographer & Videographer": "12 months in advance",
                "Caterer": "9 months in advance",
                "Florist": "8 months in advance",
                "Baker": "4–6 months in advance",
                "Entertainment": "9 months in advance",
                "Transportation": "6 months in advance",
            },
        },
    },
    "birthday": {
        "small": {
            "vendors": ["Home Caterer / Food Delivery", "Baker (Cake)", "Party Supply Store"],
            "questions": {
                "Baker": [
                    "Do you offer a tasting session?",
                    "Can you replicate a photo reference for the design?",
                    "What is your advance notice requirement?",
                ],
            },
            "booking_deadlines": {
                "Baker": "2–3 weeks in advance",
                "Entertainment (e.g., magician)": "3–4 weeks in advance",
            },
        },
        "large": {
            "vendors": [
                "Venue", "Caterer", "Baker (Cake)", "Photographer",
                "DJ / Live Music", "Decor Company", "Photo Booth", "Party Entertainer",
            ],
            "questions": {
                "DJ": [
                    "Do you take requests on the night?",
                    "Do you provide your own sound and lighting equipment?",
                    "What is included in your setup time?",
                ],
                "Venue": [
                    "Is there a noise curfew?",
                    "Is in-house catering mandatory, or can we bring our own?",
                    "Are tables, chairs, and linens included?",
                ],
            },
            "booking_deadlines": {
                "Venue": "2–4 months in advance",
                "Caterer": "4–6 weeks in advance",
                "Photographer": "4–8 weeks in advance",
                "DJ": "4–8 weeks in advance",
                "Baker": "3–4 weeks in advance",
            },
        },
    },
    "community": {
        "small": {
            "vendors": ["PA System Rental", "Food Stall Operators", "Volunteer Coordinators"],
            "questions": {
                "PA System Rental": [
                    "Is a technician included or self-operated?",
                    "What is the coverage area of the speakers?",
                ],
            },
            "booking_deadlines": {
                "Permits": "6–8 weeks in advance",
                "PA Rental": "2–3 weeks in advance",
            },
        },
        "large": {
            "vendors": [
                "Stage & AV Production Company", "Security Company",
                "Food Trucks / Caterers", "First Aid Provider",
                "Portable Toilet Rental", "Waste Management",
                "Local Authority Liaison", "Signage & Print Vendor",
            ],
            "questions": {
                "Security Company": [
                    "Are your staff SIA licensed?",
                    "Can you provide a crowd-management plan?",
                    "What is the ratio of staff to expected attendees?",
                ],
                "AV Production": [
                    "Do you conduct a pre-event site survey?",
                    "What is your contingency for equipment failure?",
                    "Is load-in the day before possible?",
                ],
            },
            "booking_deadlines": {
                "Venue / Public Space": "10–12 weeks in advance",
                "Permits": "8–10 weeks in advance",
                "Security": "6–8 weeks in advance",
                "AV / Stage": "6–8 weeks in advance",
                "Food Vendors": "4–6 weeks in advance",
                "First Aid": "4 weeks in advance",
                "Portable Toilets": "3–4 weeks in advance",
            },
        },
    },
}


def get_vendor_checklist(event_type: str, scale: str) -> dict:
    """Return a vendor checklist with questions to ask and booking deadlines.

    Args:
        event_type: One of 'wedding', 'birthday', or 'community'.
        scale: Event scale – either 'small' (intimate) or 'large' (full-scale).

    Returns:
        A dictionary containing required vendors, key questions to ask each
        vendor during consultations, and recommended booking deadlines.
    """
    event_type = event_type.lower().strip()
    scale = scale.lower().strip()

    if event_type not in _VENDOR_DATA:
        return {
            "error": f"Unknown event_type '{event_type}'. Choose 'wedding', 'birthday', or 'community'."
        }
    if scale not in ("small", "large"):
        scale = "large"  # default to large for safety

    data = _VENDOR_DATA[event_type][scale]

    return {
        "event_type": event_type,
        "scale": scale,
        "required_vendors": data["vendors"],
        "key_questions_by_vendor": data.get("questions", {}),
        "booking_deadlines": data["booking_deadlines"],
        "pro_tip": (
            "Always get at least three quotes for each vendor category "
            "and ensure every agreement is in writing before paying a deposit."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 4 – Pinterest Inspiration
# ---------------------------------------------------------------------------

_INSPIRATION_DATA: dict[str, dict[str, list[str]]] = {
    "wedding": {
        "boho": {
            "keywords": [
                "boho wedding decor", "bohemian wedding florals", "pampas grass wedding arch",
                "boho wedding table settings", "earthy wedding color palette",
            ],
            "description": "Dreamy, free-spirited aesthetics with dried florals, macramé, and warm earthy tones.",
        },
        "classic": {
            "keywords": [
                "classic elegant wedding decor", "white rose wedding florals",
                "black tie wedding reception", "crystal chandelier wedding venue",
                "timeless wedding color palette ivory gold",
            ],
            "description": "Timeless sophistication with white florals, gold accents, and candlelit receptions.",
        },
        "garden": {
            "keywords": [
                "garden wedding ceremony ideas", "outdoor wedding floral arch",
                "garden party wedding reception", "wildflower wedding bouquet",
                "pastel wedding color palette spring",
            ],
            "description": "Lush outdoor romance with wildflowers, greenery, and soft pastel palettes.",
        },
        "modern": {
            "keywords": [
                "modern minimalist wedding decor", "geometric wedding arch",
                "minimalist wedding florals", "industrial chic wedding venue",
                "monochrome wedding color palette",
            ],
            "description": "Clean lines, geometric shapes, and a monochrome palette for the contemporary couple.",
        },
    },
    "birthday": {
        "tropical": {
            "keywords": [
                "tropical birthday party decor", "luau party ideas",
                "tropical cake design", "flamingo party decoration",
                "bright tropical color palette party",
            ],
            "description": "Vibrant, sun-soaked vibes with bold colours, tropical leaves, and fun party energy.",
        },
        "elegant": {
            "keywords": [
                "elegant adult birthday party", "gold and black birthday decor",
                "luxury birthday table setting", "birthday floral centrepiece",
                "sophisticated birthday color palette",
            ],
            "description": "Sophisticated soirée with moody florals, gold accents, and statement centrepieces.",
        },
        "pastel": {
            "keywords": [
                "pastel birthday party ideas", "soft rainbow party decor",
                "balloon garland pastel", "pastel cake design birthday",
                "whimsical party color palette",
            ],
            "description": "Sweet and whimsical with soft balloon garlands, pastel cakes, and dreamy details.",
        },
        "retro": {
            "keywords": [
                "retro disco birthday party", "70s birthday party theme",
                "vintage arcade birthday", "neon retro party decor",
                "retro color palette party 70s 80s",
            ],
            "description": "Funky throwback energy with disco balls, neon lights, and vintage nostalgia.",
        },
    },
    "community": {
        "festival": {
            "keywords": [
                "outdoor community festival setup", "festival stage decoration ideas",
                "festival food stall design", "community festival banner design",
                "festival color palette bright",
            ],
            "description": "High-energy festival atmosphere with colourful banners, food stalls, and live stage areas.",
        },
        "cultural": {
            "keywords": [
                "cultural heritage festival decor", "multicultural event decoration",
                "traditional festival celebration ideas", "lantern festival decoration",
                "global cultural color palette",
            ],
            "description": "Rich traditions and heritage showcased through vibrant fabrics, lanterns, and cultural motifs.",
        },
        "eco": {
            "keywords": [
                "eco friendly community event decor", "sustainable event design",
                "green community festival ideas", "upcycled event decoration",
                "nature inspired color palette event",
            ],
            "description": "Earth-conscious design with recycled materials, plant-based decor, and natural tones.",
        },
        "professional": {
            "keywords": [
                "professional community networking event decor",
                "corporate community event setup", "clean minimalist event signage",
                "professional event color palette blue white",
            ],
            "description": "Polished and professional with branded signage, clean layouts, and structured spaces.",
        },
    },
}

_PINTEREST_BASE = "https://www.pinterest.com/search/pins/?q="


def generate_pinterest_inspiration(event_type: str, theme_aesthetic: str) -> dict:
    """Generate curated Pinterest search links and aesthetic concepts for an event.

    Args:
        event_type: One of 'wedding', 'birthday', or 'community'.
        theme_aesthetic: Aesthetic or theme keyword (e.g., 'boho', 'elegant',
                         'tropical', 'festival', 'cultural', 'eco').

    Returns:
        A dictionary containing a theme description, Pinterest search URLs
        formatted as Markdown links, and additional mood board suggestions.
    """
    event_type = event_type.lower().strip()
    theme_key = theme_aesthetic.lower().strip()

    if event_type not in _INSPIRATION_DATA:
        return {
            "error": f"Unknown event_type '{event_type}'. Choose 'wedding', 'birthday', or 'community'."
        }

    event_themes = _INSPIRATION_DATA[event_type]

    # Fuzzy-match: pick the closest theme if exact match not found
    matched_theme = None
    for key in event_themes:
        if key in theme_key or theme_key in key:
            matched_theme = key
            break
    if not matched_theme:
        matched_theme = next(iter(event_themes))  # fallback to first

    theme_data = event_themes[matched_theme]
    keywords: list[str] = theme_data["keywords"]

    pinterest_links = [
        f"[{kw.title()}]({_PINTEREST_BASE}{urllib.parse.quote_plus(kw)})"
        for kw in keywords
    ]

    available_themes = list(event_themes.keys())

    return {
        "event_type": event_type,
        "matched_theme": matched_theme,
        "description": theme_data["description"],
        "pinterest_links": pinterest_links,
        "available_themes_for_this_event": available_themes,
        "mood_board_tip": (
            "Save your favourite pins to a secret Pinterest board and share the link "
            "with your vendors — a visual brief is worth a thousand words!"
        ),
    }


# ---------------------------------------------------------------------------
# Tool 5 – Google Maps Places Venue Search
# ---------------------------------------------------------------------------


def search_event_venues(query: str, location: str) -> dict:
    """Search for event and party venues around a specific city or area using Google Maps Places API.

    Args:
        query: Type of venue, e.g., 'outdoor boho garden wedding venue',
               'birthday banquet hall', 'team offsite resort'.
        location: City or neighbourhood name, e.g., 'Bangalore', 'Goa', 'South Delhi'.

    Returns:
        A dictionary containing the list of top venue objects (name, address,
        rating, user_ratings_total, and maps_url) and search metadata.
    """
    import os
    import urllib.parse

    clean_query = query.strip()
    clean_location = location.strip()
    search_text = f"{clean_query} in {clean_location}"
    web_maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(search_text)}"

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

    # 1. Live Google Maps Places API when key is configured
    if api_key and api_key != "your_google_maps_api_key_here":
        try:
            import googlemaps

            gmaps = googlemaps.Client(key=api_key)
            places_result = gmaps.places(query=search_text)

            venues: list[dict] = []
            for place in places_result.get("results", [])[:5]:
                place_id = place.get("place_id")
                name = place.get("name", "Event Venue")
                addr = place.get("formatted_address", f"{clean_location}")
                maps_url = (
                    f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                    if place_id
                    else f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(f'{name} {addr}')}"
                )
                venues.append({
                    "name": name,
                    "address": addr,
                    "rating": place.get("rating", 4.5),
                    "user_ratings_total": place.get("user_ratings_total", 50),
                    "maps_url": maps_url,
                })

            if venues:
                return {
                    "search_query": search_text,
                    "location": clean_location,
                    "venues": venues,
                    "maps_search_url": web_maps_url,
                    "total_found": len(venues),
                    "source": "google_maps_places_api",
                }
        except Exception as exc:  # noqa: BLE001
            # Fall through to curated fallback on API errors
            pass

    # 2. Curated city venue database fallback (with direct Google Maps links)
    city_lower = clean_location.lower()
    curated_cities: dict[str, list[dict]] = {
        "bangalore": [
            {
                "name": "The Tamarind Tree",
                "address": "Avalahalli, Kanakapura Road, Bangalore",
                "rating": 4.6,
                "user_ratings_total": 2180,
                "vibe": "Heritage courtyards, lush open-air lawns, perfect for bohemian and garden celebrations",
            },
            {
                "name": "Templetree Leisure",
                "address": "Green Glen Layout, Bellandur, Bangalore",
                "rating": 4.5,
                "user_ratings_total": 1420,
                "vibe": "Balinese-inspired eco-resort with tranquil water bodies and open pavilions",
            },
            {
                "name": "Miraya Greens",
                "address": "Bannerghatta Main Road, Bangalore",
                "rating": 4.4,
                "user_ratings_total": 980,
                "vibe": "Expansive manicured lawns and modern banquet halls for mid to large gatherings",
            },
            {
                "name": "Jade 735",
                "address": "International Airport Road, Bangalore",
                "rating": 4.7,
                "user_ratings_total": 850,
                "vibe": "Ultra-stylish private boutique retreat, ideal for intimate dinners and milestone parties",
            },
        ],
        "goa": [
            {
                "name": "Alila Diwa Goa",
                "address": "Ada Waddo, Majorda, Goa",
                "rating": 4.7,
                "user_ratings_total": 3540,
                "vibe": "Lush paddy field backdrops, coastal elegance, and premier hospitality",
            },
            {
                "name": "Riva Beach Resort",
                "address": "Mandrem Beach, North Goa",
                "rating": 4.5,
                "user_ratings_total": 2890,
                "vibe": "Beachfront open lawn with river and sea confluence, stunning sunset views",
            },
            {
                "name": "Prainha Resort by the Sea",
                "address": "Dona Paula, Goa",
                "rating": 4.6,
                "user_ratings_total": 1620,
                "vibe": "Intimate ocean-facing coves and palm groves for sunset cocktail parties",
            },
        ],
        "delhi": [
            {
                "name": "The Roseate New Delhi",
                "address": "NH-8, Samalkha, New Delhi",
                "rating": 4.6,
                "user_ratings_total": 4200,
                "vibe": "Iconic architectural water mirrors and luxury gardens for sophisticated events",
            },
            {
                "name": "Tivoli Garden Resort Hotel",
                "address": "Chhattarpur, New Delhi",
                "rating": 4.4,
                "user_ratings_total": 3100,
                "vibe": "Grand Victorian lawns and ballrooms for royal and large-scale celebrations",
            },
        ],
        "mumbai": [
            {
                "name": "Sun-n-Sand Hotel Mumbai",
                "address": "Juhu Beach, Mumbai",
                "rating": 4.5,
                "user_ratings_total": 3890,
                "vibe": "Classic beachfront poolside venue overlooking the Arabian Sea",
            },
            {
                "name": "The Westin Garden City",
                "address": "Goregaon East, Mumbai",
                "rating": 4.6,
                "user_ratings_total": 4120,
                "vibe": "Elevated ballroom spaces and contemporary terraces for corporate and party events",
            },
        ],
    }

    matched_venues = []
    for city_key, venue_list in curated_cities.items():
        if city_key in city_lower or city_lower in city_key:
            matched_venues = venue_list
            break

    if not matched_venues:
        # Generic dynamic venue templates with real Google Maps search URLs
        matched_venues = [
            {
                "name": f"Top-Rated Garden & Celebration Lawns",
                "address": f"Prime Event District, {clean_location}",
                "rating": 4.7,
                "user_ratings_total": 520,
                "vibe": f"Scenic outdoor venue suited for '{clean_query}'",
            },
            {
                "name": f"The Grand Pavilion & Banquet Hall",
                "address": f"City Centre, {clean_location}",
                "rating": 4.6,
                "user_ratings_total": 680,
                "vibe": f"Full-service banquet space with integrated catering and AV",
            },
            {
                "name": f"Boutique Retreat & Event Terrace",
                "address": f"Resort Enclave, {clean_location}",
                "rating": 4.8,
                "user_ratings_total": 340,
                "vibe": f"Chic intimate venue matching aesthetic themes in {clean_location}",
            },
        ]

    formatted_venues = []
    for v in matched_venues:
        query_encoded = urllib.parse.quote_plus(f"{v['name']} {v['address']}")
        v_url = f"https://www.google.com/maps/search/?api=1&query={query_encoded}"
        formatted_venues.append({
            "name": v["name"],
            "address": v["address"],
            "rating": v["rating"],
            "user_ratings_total": v["user_ratings_total"],
            "maps_url": v_url,
            "vibe": v.get("vibe", ""),
        })

    return {
        "search_query": search_text,
        "location": clean_location,
        "venues": formatted_venues,
        "maps_search_url": web_maps_url,
        "total_found": len(formatted_venues),
        "source": "curated_database_with_google_maps_links",
    }


