"""Small country-name normalizer for spotting inconsistent spellings in feeds."""

import re

# Common variants mapped to ISO 3166-1 alpha-2. Anything not listed falls back to
# a case/punctuation-insensitive key, so "India" and "INDIA " still group together.
_ALIASES = {
    "AE": ["uae", "u a e", "united arab emirates", "emirates", "ae", "are"],
    "GB": ["uk", "u k", "united kingdom", "great britain", "britain", "england", "gb", "gbr"],
    "US": ["us", "u s", "usa", "u s a", "united states", "united states of america", "america"],
    "IN": ["in", "ind", "india", "bharat"],
    "SG": ["sg", "sgp", "singapore"],
    "SA": ["sa", "ksa", "saudi arabia", "kingdom of saudi arabia"],
    "QA": ["qa", "qat", "qatar"],
    "OM": ["om", "omn", "oman"],
    "DE": ["de", "deu", "germany", "deutschland"],
    "NL": ["nl", "nld", "netherlands", "the netherlands", "holland"],
    "HK": ["hk", "hkg", "hong kong"],
    "KR": ["kr", "kor", "south korea", "korea", "republic of korea"],
    "TH": ["th", "tha", "thailand"],
    "MY": ["my", "mys", "malaysia"],
}

_LOOKUP = {alias: code for code, aliases in _ALIASES.items() for alias in aliases}


def _key(name: str) -> str:
    name = re.sub(r"[^a-z ]", " ", str(name).lower())
    return re.sub(r"\s+", " ", name).strip()


def canonical_country(name: str) -> str:
    key = _key(name)
    return _LOOKUP.get(key, key)
