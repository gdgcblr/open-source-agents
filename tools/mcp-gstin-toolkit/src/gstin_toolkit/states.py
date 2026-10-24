"""GST state codes and helpers for matching free-text state names to them."""

import re

# Official GST state/UT codes (first two digits of a GSTIN).
STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

# Spellings and abbreviations seen in real-world feeds, mapped to a GST state code.
_ALIASES = {
    "jk": "01", "j&k": "01", "jammu & kashmir": "01",
    "hp": "02",
    "pb": "03",
    "ch": "04",
    "uk": "05", "uttaranchal": "05",
    "hr": "06",
    "dl": "07", "new delhi": "07", "nct of delhi": "07",
    "rj": "08",
    "up": "09",
    "br": "10",
    "sk": "11",
    "ar": "12",
    "nl": "13",
    "mn": "14",
    "mz": "15",
    "tr": "16",
    "ml": "17",
    "as": "18",
    "wb": "19",
    "jh": "20",
    "od": "21", "or": "21", "orissa": "21",
    "cg": "22", "ct": "22", "chattisgarh": "22",
    "mp": "23",
    "gj": "24",
    "dd": "25",
    "dn": "26", "dnh": "26", "dadra and nagar haveli": "26",
    "mh": "27",
    "ka": "29",
    "ga": "30",
    "ld": "31",
    "kl": "32",
    "tn": "33",
    "py": "34", "pondicherry": "34",
    "an": "35", "andaman & nicobar": "35",
    "ts": "36", "tg": "36",
    "ap": "37",
    "la": "38",
}


def _key(name: str) -> str:
    name = name.strip().lower().replace("&", " and ")
    name = re.sub(r"[^a-z ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


_LOOKUP = {_key(v): k for k, v in STATE_CODES.items()}
_LOOKUP.update({_key(k): v for k, v in _ALIASES.items()})
# "Andhra Pradesh" should resolve to the current code, not the pre-2014 one.
_LOOKUP[_key("Andhra Pradesh")] = "37"


def state_code_for(name: str) -> str | None:
    """Return the GST state code for a free-text state name, or None if unknown."""
    if not name:
        return None
    name = name.strip()
    if name.isdigit() and name.zfill(2) in STATE_CODES:
        return name.zfill(2)
    return _LOOKUP.get(_key(name))


def codes_match(code_a: str, code_b: str) -> bool:
    """Compare state codes, treating old/new Andhra Pradesh and the merged UTs as equal."""
    equivalent = [{"28", "37"}, {"25", "26"}]
    if code_a == code_b:
        return True
    return any({code_a, code_b} <= group for group in equivalent)
