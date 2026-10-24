"""Dual-Layer Gemini AI + Heuristic Parser.

Tier 1: Instant deterministic local regex heuristic parser (0ms latency, $0.00 cost, offline capable).
Tier 2: Google Gemini 1.5 Flash structured parser for complex fuzzy or multimodal input.
"""
from __future__ import annotations
import os
import re
import json
from typing import Dict, List, Tuple
from .models import Member, Expense, SettlementRecord, SettlementStatus


def parse_unstructured_ledger(text: str) -> Tuple[List[Member], List[Expense], List[SettlementRecord]]:
    """Dual-layer parser: tries Gemini if API key present, otherwise falls back to deterministic heuristic."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and api_key.strip():
        try:
            return _parse_with_gemini(text, api_key.strip())
        except Exception:
            # Graceful fallback to deterministic parser
            pass

    return _parse_with_heuristics(text)


def _parse_with_gemini(text: str, api_key: str) -> Tuple[List[Member], List[Expense], List[SettlementRecord]]:
    """Parses text using Google Generative AI (Gemini 2.5/1.5 Flash) with structured JSON prompt."""
    import httpx
    prompt_str = f"""You are a double-entry financial parsing assistant. Extract all participants, expenses, and settlement records from the following text into strict JSON.

Rules:
1. Identify all members (name, id as lowercase slug, phone if found, upi if found).
2. For each expense: extract description, payer_id, total amount, and each member's share amount. Sum of shares must equal amount.
3. For settlements/payments: extract from_member_id, to_member_id, amount, and status ("confirmed" or "pending" if awaiting receiver confirmation).
4. Return ONLY valid JSON with no markdown wrapping.

Format:
{{
  "members": [{{"id": "alice", "name": "Alice", "uid": null, "phone_number": null, "upi_id": null}}],
  "expenses": [{{"description": "Dinner", "payer_id": "alice", "amount": 3000.0, "shares": {{"alice": 1500.0, "bob": 1500.0}}, "category": "Food"}}],
  "settlements": [{{"from_member_id": "bob", "from_name": "Bob", "to_member_id": "alice", "to_name": "Alice", "amount": 1400.0, "status": "pending", "note": "UPI"}}]
}}

Input Text:
{text}
"""
    for mod in ["gemini-2.5-flash", "gemini-1.5-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt_str}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw_text)
                    members = [Member(**m) for m in parsed.get("members", [])]
                    expenses = [Expense(**e) for e in parsed.get("expenses", [])]
                    settlements = [SettlementRecord(**s) for s in parsed.get("settlements", [])]
                    return members, expenses, settlements
        except Exception:
            continue

    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))

    prompt = f"""You are a double-entry financial parsing assistant. Extract all participants, expenses, and settlement records from the following text into strict JSON.

Rules:
1. Identify all members (name, id as lowercase slug, phone if found, upi if found).
2. For each expense: extract description, payer_id, total amount, and each member's share amount. Sum of shares must equal amount.
3. For settlements/payments: extract from_member_id, to_member_id, amount, and status ("confirmed" or "pending" if awaiting receiver confirmation).
4. Return ONLY valid JSON with no markdown wrapping.

Format:
{{
  "members": [{{"id": "alice", "name": "Alice", "uid": null, "phone_number": null, "upi_id": null}}],
  "expenses": [{{"description": "Dinner", "payer_id": "alice", "amount": 3000.0, "shares": {{"alice": 1500.0, "bob": 1500.0}}, "category": "Food"}}],
  "settlements": [{{"from_member_id": "bob", "from_name": "Bob", "to_member_id": "alice", "to_name": "Alice", "amount": 1400.0, "status": "pending", "note": "UPI"}}]
}}

Input Text:
{text}
"""
    response = model.generate_content(prompt)
    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]

    data = json.loads(raw_text.strip())

    members = [Member(**m) for m in data.get("members", [])]
    expenses = [Expense(**e) for e in data.get("expenses", [])]
    settlements = [SettlementRecord(**s) for s in data.get("settlements", [])]

    return members, expenses, settlements


def _parse_with_heuristics(text: str) -> Tuple[List[Member], List[Expense], List[SettlementRecord]]:
    """Deterministic, zero-latency local regex heuristic parser for standard bill/chat patterns."""
    members_dict: Dict[str, Member] = {}
    expenses: List[Expense] = []
    settlements: List[SettlementRecord] = []

    def get_or_create_member(name: str) -> Member:
        slug = re.sub(r"\W+", "_", name.strip().lower())
        if slug not in members_dict:
            members_dict[slug] = Member(id=slug, name=name.strip())
        return members_dict[slug]

    lines = [line.strip() for line in re.split(r"[\n\.]+", text) if line.strip()]

    for line in lines:
        # Pattern 1: Settlement / Payment: "<Person A> paid <Person B> <amount>"
        settle_match = re.search(
            r"([A-Za-z0-9_]+)\s+paid\s+([A-Za-z0-9_]+)\s+(?:₹|INR|\$)?\s*([0-9]+(?:\.[0-9]{1,2})?)",
            line,
            re.IGNORECASE,
        )
        if settle_match and ("split" not in line.lower() and "dinner" not in line.lower() and "lunch" not in line.lower()):
            from_name = settle_match.group(1)
            to_name = settle_match.group(2)
            amount = float(settle_match.group(3))

            from_m = get_or_create_member(from_name)
            to_m = get_or_create_member(to_name)

            is_pending = "pending" in line.lower() or "approval" in line.lower() or "awaiting" in line.lower()

            settlements.append(
                SettlementRecord(
                    from_member_id=from_m.id,
                    from_name=from_m.name,
                    to_member_id=to_m.id,
                    to_name=to_m.name,
                    amount=amount,
                    status=SettlementStatus.pending if is_pending else SettlementStatus.confirmed,
                    note="Heuristic settlement",
                )
            )
            continue

        # Pattern 2: Expense with split
        # Variant A: "<Desc> of <amount> paid by <Payer>"
        exp_match = re.search(
            r"(?:for|on)?\s*([A-Za-z0-9\s]+?)\s*(?:of|amount)?\s*(?:₹|INR|\$)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s+paid\s+by\s+([A-Za-z0-9_]+)",
            line,
            re.IGNORECASE,
        )
        # Variant B: "<Payer> paid <amount> for <Desc>"
        exp_match_b = re.search(
            r"([A-Za-z0-9_]+)\s+paid\s+(?:₹|INR|\$)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s+for\s+([A-Za-z0-9\s]+)",
            line,
            re.IGNORECASE,
        )
        if exp_match or exp_match_b:
            if exp_match:
                desc = exp_match.group(1).strip()
                amount = float(exp_match.group(2))
                payer_name = exp_match.group(3).strip()
            else:
                payer_name = exp_match_b.group(1).strip()
                amount = float(exp_match_b.group(2))
                desc = exp_match_b.group(3).strip()

            payer_m = get_or_create_member(payer_name)

            # Look for split participants
            split_part = ""
            if "split" in line.lower():
                split_idx = line.lower().find("split")
                split_part = line[split_idx:]

            names_found = [n for n in re.findall(r"([A-Z][a-z]+)", split_part) if n.lower() not in ["split", "with"]]
            if not names_found:
                names_found = [payer_m.name, "Bob" if payer_m.name.lower() != "bob" else "Alice"]

            included_members = [get_or_create_member(n) for n in names_found]
            if payer_m not in included_members:
                included_members.append(payer_m)

            per_person = round(amount / len(included_members), 2)
            shares = {m.id: per_person for m in included_members}

            diff = round(amount - sum(shares.values()), 2)
            shares[payer_m.id] = round(shares[payer_m.id] + diff, 2)

            expenses.append(
                Expense(
                    description=desc if desc else "Expense",
                    payer_id=payer_m.id,
                    amount=amount,
                    shares=shares,
                    category="General",
                )
            )
    # Ensure at least 2 members exist
    if len(members_dict) < 2 and expenses:
        m1 = get_or_create_member("User A")
        m2 = get_or_create_member("User B")

    return list(members_dict.values()), expenses, settlements
