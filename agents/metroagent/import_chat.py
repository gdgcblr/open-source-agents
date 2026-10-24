
import json
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = DATA_DIR / "reports.json"

STATIONS = [
    "Majestic",
    "Nadaprabhu Kempegowda Station, Majestic",
    "Indiranagar",
    "MG Road",
    "Cubbon Park",
    "Baiyappanahalli",
    "Whitefield",
    "KR Puram",
    "Silk Institute",
    "Yelachenahalli",
    "Jayanagar",
    "J P Nagar",
    "Banashankari",
    "Yeshwanthpur",
    "Peenya",
    "Kengeri",
    "Challaghatta",
    "Nagasandra",
    "Vijayanagar",
    "Rajajinagar",
    "Lalbagh",
    "National College",
    "Trinity",
    "Halasuru",
    "Krantivira Sangolli Rayanna Railway Station",
]

def parse_message_timestamp(line):
    match = re.match(
        r"^\[?(\d{1,2}/\d{1,2}/\d{2,4}),?\s+"
        r"(\d{1,2}:\d{2}(?:\s?[APap][Mm])?)\]?\s+-\s+",
        line,
    )
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def extract_report(message):
    text = message.casefold()

    if not any(
        word in text
        for word in (
            "crowd", "packed", "empty", "busy", "rush",
            "standing", "seat", "coach", "bogie", "bogey",
            "platform", "interchange", "less crowded",
        )
    ):
        return None

    report = {
        "origin": "",
        "destination": "",
        "station": "",
        "direction": "",
        "interchange": "",
        "observed_time": "",
        "crowd_level": "unknown",
        "coach_position": "",
        "report_text": message.strip(),
    }

    for station in STATIONS:
        if station.casefold() in text:
            report["station"] = station
            break

    if any(term in text for term in ("very crowded", "packed", "overcrowded")):
        report["crowd_level"] = "very high"
    elif any(term in text for term in ("crowded", "heavy crowd", "rush hour")):
        report["crowd_level"] = "high"
    elif any(term in text for term in ("moderate crowd", "some crowd", "busy")):
        report["crowd_level"] = "moderate"
    elif any(term in text for term in ("empty", "not crowded", "less crowded")):
        report["crowd_level"] = "low"

    if any(term in text for term in ("front coach", "front bogie", "front compartment")):
        report["coach_position"] = "front"
    elif any(term in text for term in ("middle coach", "middle bogie", "middle compartment")):
        report["coach_position"] = "middle"
    elif any(term in text for term in ("rear coach", "last coach", "rear bogie")):
        report["coach_position"] = "rear"

    time_match = re.search(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        message,
    )
    if time_match:
        report["observed_time"] = (
            f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
        )

    return report


def main():
    if len(sys.argv) != 2:
        print(
            'Usage: python import_chat.py "path/to/WhatsApp Chat.txt"'
        )
        raise SystemExit(1)

    chat_file = Path(sys.argv[1])

    if not chat_file.is_file():
        print(f"Chat file not found: {chat_file}")
        raise SystemExit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    messages = []
    current_message = ""

    with chat_file.open("r", encoding="utf-8-sig") as file:
        for line in file:
            if parse_message_timestamp(line):
                if current_message:
                    messages.append(current_message)
                current_message = line.strip()
            elif current_message:
                current_message += "\n" + line.strip()

    if current_message:
        messages.append(current_message)

    reports = []

    for message in messages:
        timestamp = parse_message_timestamp(message)
        body = re.sub(
            r"^\[?\d{1,2}/\d{1,2}/\d{2,4},?\s+"
            r"\d{1,2}:\d{2}(?:\s?[APap][Mm])?\]?\s+-\s+",
            "",
            message,
        )

        if ": " in body:
            body = body.split(": ", 1)[1]

        report = extract_report(body)

        if report:
            report["message_timestamp"] = timestamp
            reports.append(report)

    existing = []
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(
                OUTPUT_FILE.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            existing = []

    if not isinstance(existing, list):
        existing = []

    existing.extend(reports)

    OUTPUT_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Imported {len(reports)} candidate reports.")
    print(f"Total records in dataset: {len(existing)}")
    print(f"Output: {OUTPUT_FILE}")
    print("Review every extracted report before using it.")


if __name__ == "__main__":
    main()
