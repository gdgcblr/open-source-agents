"""Deterministic scam-forensics tools used by the Scam Shield agents.

Every function here is pure Python (no LLM calls), so the tools are fast, free,
unit-testable, and double as the offline fallback when Gemini is unavailable.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

# Brand keyword -> official registered domains. A hostname that mentions the
# brand but is not one of these domains is treated as impersonation.
OFFICIAL_DOMAINS: dict[str, list[str]] = {
    "sbi": ["sbi.co.in", "onlinesbi.sbi", "sbi.bank.in", "sbicard.com"],
    "hdfc": ["hdfcbank.com", "hdfc.com", "hdfc.bank.in"],
    "icici": ["icicibank.com", "icici.bank.in"],
    "axisbank": ["axisbank.com", "axis.bank.in"],
    "kotak": ["kotak.com", "kotak.bank.in"],
    "paytm": ["paytm.com", "paytmbank.com"],
    "phonepe": ["phonepe.com"],
    "gpay": ["pay.google.com", "google.com"],
    "amazon": ["amazon.in", "amazon.com"],
    "flipkart": ["flipkart.com"],
    "indiapost": ["indiapost.gov.in"],
    "incometax": ["incometax.gov.in"],
    "uidai": ["uidai.gov.in"],
    "aadhaar": ["uidai.gov.in"],
    "epfo": ["epfindia.gov.in"],
    "irctc": ["irctc.co.in"],
    "npci": ["npci.org.in"],
    "whatsapp": ["whatsapp.com"],
    "netflix": ["netflix.com"],
    "fedex": ["fedex.com"],
    "dhl": ["dhl.com"],
}

URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "rb.gy", "is.gd", "goo.gl", "ow.ly",
    "shorturl.at", "tiny.cc", "rebrand.ly", "t.ly", "s.id", "v.gd", "shorte.st",
    "bitly.com", "t.co", "lnkd.in", "surl.li", "tinu.be",
}

SUSPICIOUS_TLDS = {
    "xyz", "top", "club", "online", "site", "icu", "buzz", "live", "shop",
    "click", "link", "info", "vip", "cyou", "rest", "work", "support",
    "monster", "cfd", "sbs", "lol", "quest", "win", "loan", "bond",
}

# Second-level labels under which the registrable domain has three parts
# (e.g. sbi.co.in, indiapost.gov.in).
_SECOND_LEVEL = {"co", "gov", "ac", "org", "net", "nic", "edu", "res", "bank", "com"}

# Homoglyph normalisation applied before lookalike comparison.
_HOMOGLYPHS = [("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("3", "e"),
               ("5", "s"), ("4", "a"), ("7", "t"), ("8", "b")]

_URL_RE = re.compile(
    r"(?:https?://[^\s<>\"']+)"
    r"|(?<![@\w.-])(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
_UPI_RE = re.compile(r"(?<![\w.-])[\w.-]{2,64}@[a-zA-Z]{2,32}(?![.\w])")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")

# Each category: (weight, phrases). Phrases are matched case-insensitively as
# substrings. A few Hindi, Hinglish and Kannada phrases are included because
# Indian scam messages frequently mix scripts.
SCAM_PATTERNS: dict[str, tuple[int, list[str]]] = {
    "urgency_pressure": (15, [
        "urgent", "immediately", "within 24 hours", "within 2 hours", "today itself",
        "last warning", "final notice", "act now", "expire today", "expires today",
        "turant", "तुरंत", "ತಕ್ಷಣ", "last date today", "before midnight", "jaldi", "fauran",
    ]),
    "account_block_kyc": (30, [
        "kyc", "account will be blocked", "account has been blocked", "account suspended",
        "will be suspended", "deactivated", "pan card update", "update your pan",
        "aadhaar update", "account will be closed", "खाता बंद", "ಖಾತೆ ಬ್ಲಾಕ್",
        "khata band", "account band", "khata block", "account block ho",
    ]),
    "prize_lottery": (30, [
        "you have won", "you've won", "lottery", "lucky draw", "lucky winner",
        "claim your prize", "claim your reward", "kbc", "won a car", "gift voucher",
        "selected as winner", "redeem your points", "reward points will expire",
    ]),
    "job_task_scam": (30, [
        "work from home", "part time job", "part-time job", "daily income", "earn rs",
        "earn ₹", "like youtube videos", "rate hotels", "telegram task", "prepaid task",
        "per day salary", "no experience needed", "earn daily",
    ]),
    "parcel_delivery": (25, [
        "parcel", "customs", "delivery failed", "address incomplete", "package is on hold",
        "shipment on hold", "redelivery", "courier", "undelivered",
    ]),
    "utility_disconnection": (30, [
        "electricity will be disconnected", "power will be disconnected",
        "electricity connection will be", "bill not updated", "previous month bill was not",
        "electricity officer", "बिजली", "ವಿದ್ಯುತ್",
        "bijli connection", "bijli kaat", "connection kaat", "kaat diya jayega",
        "kaat di jayegi", "kat jayega", "kat jayegi",
    ]),
    "authority_threat": (35, [
        "digital arrest", "cbi", "narcotics", "money laundering", "arrest warrant",
        "cyber police", "your sim will be blocked", "number will be disconnected",
        "trai", "drugs found", "court notice", "ed officer",
    ]),
    "loan_offer": (20, [
        "pre-approved loan", "pre approved loan", "instant loan", "loan approved",
        "loan sanctioned", "no cibil",
    ]),
    "refund_tax": (25, [
        "income tax refund", "refund of rs", "refund of ₹", "tax refund", "refund approved",
        "excess payment refund",
    ]),
    "family_impersonation": (25, [
        "hi mum", "hi mom", "hi dad", "lost my phone", "send money urgently", "in hospital", "had an accident",
    ]),
    "investment_scam": (30, [
        "guaranteed returns", "guaranteed profit", "double your money", "stock tips",
        "ipo allotment", "100% profit", "crypto investment", "usdt", "trading group",
    ]),
}

PAYMENT_SIGNALS: dict[str, tuple[int, list[str]]] = {
    "asks_for_otp": (40, ["share the otp", "share otp", "send the otp", "send otp",
                          "tell the otp", "otp received", "provide otp", "ओटीपी",
                          "otp bata", "otp bhej"]),
    "asks_for_upi_pin": (45, ["upi pin", "enter your pin", "enter pin to receive",
                              "pin to receive"]),
    "receive_money_trap": (35, ["scan to receive", "scan the qr to receive",
                                "accept the collect request", "collect request",
                                "approve the request to receive"]),
    "asks_card_or_bank_details": (35, ["cvv", "card number", "debit card details",
                                       "net banking password", "ifsc", "account number"]),
    "upfront_fee": (30, ["processing fee", "registration fee", "release fee",
                         "small fee", "pay rs", "pay ₹", "advance payment", "security deposit"]),
    "remote_access_app": (45, ["anydesk", "teamviewer", "quicksupport", "rustdesk",
                               "screen share", "screen sharing"]),
    "apk_install": (45, [".apk", "install this app", "download the app from this link"]),
    "gift_card_or_crypto": (30, ["gift card", "google play card", "bitcoin", "usdt", "crypto wallet"]),
}

# "Do not share your OTP" is advice, not a request: these clauses are removed
# before looking for OTP, PIN or card-detail requests.
_NEGATED_ASK_RE = re.compile(
    r"\b(?:do not|don't|dont|never|not to)\s+(?:share|send|tell|disclose|give)\b[^.!?\n]*",
    re.IGNORECASE,
)
# A refund reported as already credited is a receipt, not a lure.
_REFUND_DONE_RE = re.compile(
    r"\b(?:has been|have been|was|is|got)\s+(?:credited|refunded)\b|\bcredited (?:to|in|into) your\b",
    re.IGNORECASE,
)
# Family impersonation: a "new number" combined with a request for money.
_NEW_NUMBER_RE = re.compile(
    r"\bnew (?:phone |mobile )?number\b|\bchanged my number\b|\bnaya number\b|नया नंबर",
    re.IGNORECASE,
)
_MONEY_ASK_RE = re.compile(
    r"\b(?:send|transfer|need|pay|lend)\b.{0,40}?\b(?:money|rs|inr|amount|bill|fees?)\b"
    r"|₹|\bpaise\b|\bpaisa\b|\bbhej|पैसे",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _phrase_hits(phrases: list[str], lowered: str) -> list[str]:
    """Phrases found in the lower-cased text. Short ASCII words such as 'trai'
    or 'cbi' must match whole words, so 'train' does not count as 'trai'."""
    return [p for p in phrases
            if (re.search(rf"\b{re.escape(p)}\b", lowered)
                if len(p) <= 4 and p.isascii() and p.isalpha() else p in lowered)]


def _registered_domain(host: str) -> str:
    labels = host.lower().strip(".").split(".")
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _normalise(label: str) -> str:
    label = label.lower()
    for src, dst in _HOMOGLYPHS:
        label = label.replace(src, dst)
    return label.replace("-", "")


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _is_official(host: str) -> bool:
    host = host.lower()
    return any(host == d or host.endswith("." + d)
               for domains in OFFICIAL_DOMAINS.values() for d in domains)


def _find_urls(text: str) -> list[str]:
    urls = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!?)]}'\"")
        # Skip things like "e.g" or "a.m" that are not real domains.
        host = urllib.parse.urlsplit(url if "://" in url else "http://" + url).hostname or ""
        if "." in host and len(host) > 4 and url not in urls:
            urls.append(url)
    return urls


def _unshorten(url: str, timeout: float = 3.0, max_hops: int = 5) -> list[str]:
    """Follow redirects, but only ever contact known URL-shortener hosts.

    The final (possibly malicious) destination is never requested, which keeps
    the server safe from SSRF and avoids "visiting" the scam page.
    """

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    chain = []
    current = url if "://" in url else "https://" + url
    for _ in range(max_hops):
        parts = urllib.parse.urlsplit(current)
        host = (parts.hostname or "").lower()
        if host not in URL_SHORTENERS or parts.scheme not in ("http", "https"):
            break
        try:
            if not all(ipaddress.ip_address(info[4][0]).is_global
                       for info in socket.getaddrinfo(host, None)):
                break
            request = urllib.request.Request(current, method="HEAD",
                                             headers={"User-Agent": "ScamShield/1.0"})
            response = opener.open(request, timeout=timeout)
            location = response.headers.get("Location")
        except urllib.error.HTTPError as err:  # 3xx arrives here because redirects are disabled
            location = err.headers.get("Location") if 300 <= err.code < 400 else None
        except (OSError, ValueError):
            break
        if not location:
            break
        current = urllib.parse.urljoin(current, location)
        chain.append(current)
    return chain


# --------------------------------------------------------------------------
# Tools exposed to the agents
# --------------------------------------------------------------------------


def analyze_links(text: str, follow_shorteners: bool = True) -> dict:
    """Finds every link in a message and checks it for phishing signs.

    Checks for URL shorteners (and reveals their real destination), fake brand
    domains such as 'sbi-kyc-update.xyz', lookalike spellings such as
    'paytrn.com', raw IP addresses, punycode, risky top-level domains and
    plain-HTTP links.

    Args:
        text: The full message text (or text read from a screenshot).
        follow_shorteners: Whether to reveal where shortened links lead.

    Returns:
        A dict with 'links' (per-link findings) and 'risk_points' (0-100).
    """
    results = []
    total = 0
    for url in _find_urls(text)[:10]:
        flags: list[str] = []
        points = 0
        destination = None
        full = url if "://" in url else "http://" + url
        parts = urllib.parse.urlsplit(full)
        host = (parts.hostname or "").lower()

        if host in URL_SHORTENERS:
            flags.append("Shortened link hides the real website")
            points += 15
            if follow_shorteners:
                chain = _unshorten(url)
                if chain:
                    destination = chain[-1]
                    parts = urllib.parse.urlsplit(destination)
                    host = (parts.hostname or "").lower()

        registered = _registered_domain(host) if host else ""
        official = _is_official(host)

        try:
            ipaddress.ip_address(host)
            flags.append("Link uses a raw IP address instead of a website name")
            points += 35
        except ValueError:
            pass
        if host.startswith("xn--") or ".xn--" in host or any(ord(c) > 127 for c in host):
            flags.append("Domain uses look-alike international characters (punycode)")
            points += 35
        tld = host.rsplit(".", 1)[-1] if "." in host else ""
        if tld in SUSPICIOUS_TLDS:
            flags.append(f"Uses a high-risk domain ending '.{tld}' common in scams")
            points += 20
        if not official:
            unglyphed = host
            for src, dst in _HOMOGLYPHS:
                unglyphed = unglyphed.replace(src, dst)
            labels = re.split(r"[.\-]", host) + re.split(r"[.\-]", unglyphed)
            for brand, domains in OFFICIAL_DOMAINS.items():
                if any(lbl == brand or (len(brand) >= 4 and brand in lbl) for lbl in labels if lbl):
                    flags.append(f"Pretends to be '{brand}' but the real site is {domains[0]}")
                    points += 45
                    break
            else:
                first = _normalise(registered.split(".")[0]) if registered else ""
                for brand, domains in OFFICIAL_DOMAINS.items():
                    real = _normalise(domains[0].split(".")[0])
                    # Not an official domain, yet (after undoing homoglyphs) it spells
                    # a brand or is one typo away from it: paytrn.com, amaz0n.in.
                    if first and len(real) >= 4 and _levenshtein(first, real) <= 1:
                        flags.append(f"Lookalike spelling of {domains[0]}")
                        points += 45
                        break
        if host.count(".") >= 4:
            flags.append("Unusually many sub-domains (a common disguise)")
            points += 10
        if "@" in parts.netloc:
            flags.append("Link contains '@', which can hide the real destination")
            points += 30
        if parts.scheme == "http" and "://" in (destination or url) and not official:
            flags.append("Not a secure (https) link")
            points += 5

        results.append({
            "link": url,
            "real_destination": destination,
            "domain": registered,
            "is_known_official_domain": official,
            "flags": flags,
        })
        total += points
    return {"links": results, "risk_points": min(total, 100)}


def detect_payment_requests(text: str) -> dict:
    """Detects money-related traps: UPI IDs, OTP/PIN requests, fake 'receive
    money' QR codes, card details, upfront fees, remote-access apps and APKs.

    Args:
        text: The full message text (or text read from a screenshot).

    Returns:
        A dict with found 'upi_ids', 'phone_numbers', matched 'signals' and
        'risk_points' (0-100).
    """
    lowered = _NEGATED_ASK_RE.sub(" ", text).lower()
    signals = []
    total = 0
    for name, (weight, phrases) in PAYMENT_SIGNALS.items():
        hits = _phrase_hits(phrases, lowered)
        if hits:
            signals.append({"signal": name, "evidence": hits[:3]})
            total += weight
    upi_ids = [m for m in _UPI_RE.findall(text)][:5]
    phones = [re.sub(r"[\s-]", "", m) for m in _PHONE_RE.findall(text)][:5]
    # A UPI ID alone is normal (debit alerts name the payee); it only adds risk
    # alongside an actual request for money, a PIN or an OTP.
    if upi_ids and signals:
        total += 15
    return {
        "upi_ids": upi_ids,
        "phone_numbers": phones,
        "signals": signals,
        "risk_points": min(total, 100),
    }


def scan_scam_patterns(text: str) -> dict:
    """Matches the message against known Indian scam playbooks: fake KYC,
    lottery/prize, job/task, parcel, electricity disconnection, 'digital
    arrest'/police threats, loans, tax refunds, family impersonation and
    investment scams. Also detects pressure tactics.

    Args:
        text: The full message text (or text read from a screenshot).

    Returns:
        A dict with matched 'categories' (with evidence) and 'risk_points'.
    """
    lowered = text.lower()
    categories = []
    total = 0
    for name, (weight, phrases) in SCAM_PATTERNS.items():
        if name == "refund_tax" and _REFUND_DONE_RE.search(text):
            continue
        hits = _phrase_hits(phrases, lowered)
        if hits:
            categories.append({"category": name, "evidence": hits[:3]})
            total += weight
    new_number = _NEW_NUMBER_RE.search(text)
    money_ask = _MONEY_ASK_RE.search(text)
    if new_number and money_ask:
        categories.append({"category": "new_number_money_request",
                           "evidence": [new_number.group(0), money_ask.group(0)]})
        total += 40
    return {"categories": categories, "risk_points": min(total, 100)}


def rules_verdict(text: str, follow_shorteners: bool = True) -> dict:
    """Combines all tools into a verdict without any LLM (offline fallback)."""
    links = analyze_links(text, follow_shorteners=follow_shorteners)
    payment = detect_payment_requests(text)
    patterns = scan_scam_patterns(text)
    score = min(links["risk_points"] + payment["risk_points"] + patterns["risk_points"], 100)
    # Two independent weak signals together are much stronger than either alone.
    if sum(1 for r in (links, payment, patterns) if r["risk_points"] > 0) >= 2:
        score = min(score + 10, 100)
    verdict = "scam" if score >= 60 else "suspicious" if score >= 25 else "safe"

    red_flags = [f for link in links["links"] for f in link["flags"]]
    red_flags += [s["signal"].replace("_", " ") for s in payment["signals"]]
    red_flags += [c["category"].replace("_", " ") for c in patterns["categories"]]
    return {
        "verdict": verdict,
        "risk_score": score,
        "red_flags": list(dict.fromkeys(red_flags))[:8],
        "details": {"links": links, "payment": payment, "patterns": patterns},
    }
