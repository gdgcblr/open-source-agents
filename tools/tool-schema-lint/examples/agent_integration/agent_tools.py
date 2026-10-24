"""Tool definitions of a small trip-planner agent, written the way most agents define them.

The list uses the OpenAI Chat Completions format with `strict: true`, and is written to
also be valid for Gemini: optional values are nullable via `anyOf` (not a type array) and
enums are strings. `test_agent_tools.py` keeps it that way.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": (
                "Search one-way flights between two airports on a given date. Use it when the user "
                "wants to travel and has named an origin, a destination, and a date. Returns up to "
                "ten options sorted by price, each with airline, departure time, and fare in INR."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "IATA airport code, e.g. BLR"},
                    "destination": {"type": "string", "description": "IATA airport code, e.g. DEL"},
                    "date": {"type": "string", "format": "date", "description": "Travel date, YYYY-MM-DD"},
                    "cabin": {
                        "type": "string",
                        "enum": ["economy", "premium_economy", "business"],
                        "description": "Cabin class to search",
                    },
                    "max_stops": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "Maximum number of stops, or null for any",
                    },
                },
                "required": ["origin", "destination", "date", "cabin", "max_stops"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": (
                "Get the daily weather forecast for a city for the next few days. Use it to warn the "
                "user about rain or extreme heat on their travel dates. Returns one entry per day "
                "with the high, low, and chance of rain."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. Bengaluru"},
                    "days": {
                        "type": "string",
                        "enum": ["1", "3", "7"],
                        "description": "Number of forecast days to return",
                    },
                },
                "required": ["city", "days"],
                "additionalProperties": False,
            },
        },
    },
]
