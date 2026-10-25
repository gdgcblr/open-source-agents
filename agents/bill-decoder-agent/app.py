"""
Web page for bill-decoder-agent.

Run locally:
    streamlit run app.py
"""

import datetime
import html
import logging
import os
import re
import threading
import time

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google.genai import types
from pydantic import BaseModel

from bill_terms import TERM_NOTES
from main import generate_with_fallback
from guardrails import (
    INJECTION_RULE,
    charges_add_up,
    check_file,
    date_rule,
    parse_amount,
    parse_date,
    suspicious_dates,
)

load_dotenv()

# Usage limits that protect the shared Gemini API quota on a public deployment.
MAX_BILLS_PER_VISITOR = 5
COOLDOWN_SECONDS = 20
MAX_BILLS_PER_DAY = 60  # across all visitors (free tier: ~20 per model per day)

# On Streamlit Community Cloud the key comes from the app's Secrets settings.
if not os.getenv("GEMINI_API_KEY"):
    try:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass

LANGUAGES = ["English", "ಕನ್ನಡ Kannada", "हिन्दी Hindi", "தமிழ் Tamil", "తెలుగు Telugu", "മലയാളം Malayalam"]


# ---------- Structured answer from Gemini ----------

class Charge(BaseModel):
    name: str
    amount: str
    explanation: str
    info: str


class RedFlag(BaseModel):
    title: str
    detail: str


class Term(BaseModel):
    term: str
    meaning: str


class Usage(BaseModel):
    units_used: str
    unit_name: str
    previous_reading: str
    current_reading: str
    reading_type: str
    daily_average: str
    compared_to_last_period: str


class SectionHelp(BaseModel):
    at_a_glance: str
    actions: str
    red_flags: str
    usage: str
    charges: str
    subsidies: str
    payment: str
    tips: str


class MonthUsage(BaseModel):
    period: str
    units: float


class BillReport(BaseModel):
    is_bill: bool
    bill_type: str
    provider: str
    plan_or_tariff: str
    bill_date: str
    billing_period: str
    total_amount: str
    due_date: str
    amount_after_due_date: str
    summary: str
    action_steps: list[str]
    usage: Usage
    usage_history: list[MonthUsage]
    charges: list[Charge]
    subsidies: list[Charge]
    red_flags: list[RedFlag]
    last_payment: str
    payment_options: list[str]
    glossary: list[Term]
    tips: list[str]
    section_help: SectionHelp


WEB_PROMPT = """You are a friendly assistant that explains Indian utility bills
(electricity, water, gas, mobile, broadband) to ordinary people of all ages.

Read the attached bill and fill in the JSON fields. Write every text value in
{language}, using short, simple sentences. Keep amounts in the form printed on the
bill, e.g. "₹ 145.00".

- is_bill: false if the file is not a utility bill (then leave other fields empty).
- plan_or_tariff: the tariff category or plan printed (e.g. "LT-2a Domestic", "Postpaid 399").
- bill_date: the date the bill was issued.
- amount_after_due_date: the amount to pay if paid late, if printed.
- summary: 2-3 sentences saying what the person needs to know.
- action_steps: 2-4 clear things the person should do now, most important first
  (e.g. "Pay ₹ 820 before 15/11/2026", "Ask BESCOM why the reading is estimated").
- usage: units used and their unit name (kWh/units, litres/KL, GB, minutes),
  previous and current meter readings, reading_type ("Actual" or "Estimated" if
  printed), daily_average (units per day, calculate from units and days if both are
  printed), and compared_to_last_period (one sentence, only if previous usage is printed).
- usage_history: past periods' usage if the bill prints a history table or graph,
  oldest first, using numbers only. Empty list if not printed.
- charges: every individual line item with its amount and a one-line plain
  explanation of what it is on this bill. Include credits, subsidies and arrears as
  negative amounts. Do not include subtotal or total lines, so the charges add up to
  total_amount.
- charges[].info: 3-4 short sentences for a person who has never seen this term:
  (1) what it means in everyday words, (2) why the company charges it, and
  (3) whether the person can reduce or avoid it, and how. No jargon.
- subsidies: government schemes, discounts or rebates applied (e.g. Gruha Jyothi),
  with amount, a short explanation, and info (same rules as charges[].info, but
  explain who gives it and how to keep getting it). Empty list if none.
- red_flags: late fees, interest, arrears, estimated meter readings, usage spikes,
  unknown charges, calculation mistakes or pending deposits. Empty list if none.
- last_payment: the previous payment amount and date, if printed.
- payment_options: ways to pay printed on the bill (website, app, UPI, office).
- glossary: 3-6 technical words or abbreviations printed on this bill (e.g. FPPCA,
  kWh, Arrears, ASD) with a one-line simple meaning.
- tips: 2 or 3 practical money-saving tips for this bill type.
- section_help: for each section, 1-2 simple sentences telling a first-time reader
  what that section of the report shows and why it matters, written for this bill
  type (e.g. for a mobile bill, usage means data in GB and minutes).

The meaning of terms (info, glossary, section_help) may come from the reference
notes below or general knowledge. Everything else must come from the bill.

Only use information printed on the bill. Write "Not shown" when a value is missing
or unreadable instead of guessing.
""" + TERM_NOTES + INJECTION_RULE


@st.cache_resource
def daily_usage() -> dict:
    """App-wide counter shared by all visitors: {"date": ..., "count": ..., "lock": ...}."""
    return {"date": datetime.date.today(), "count": 0, "lock": threading.Lock()}


def usage_problem() -> str | None:
    """Return a message if this request should be blocked by a usage limit."""
    state = st.session_state
    if state.get("bills_used", 0) >= MAX_BILLS_PER_VISITOR:
        return f"You have reached the limit of {MAX_BILLS_PER_VISITOR} bills for this visit. Please come back later."
    wait = COOLDOWN_SECONDS - (time.time() - state.get("last_request", 0))
    if wait > 0:
        return f"Please wait {int(wait) + 1} seconds before decoding another bill."
    usage = daily_usage()
    with usage["lock"]:
        if usage["date"] != datetime.date.today():
            usage["date"], usage["count"] = datetime.date.today(), 0
        if usage["count"] >= MAX_BILLS_PER_DAY:
            return "This free demo has reached its daily limit. Please try again tomorrow."
    return None


def record_usage() -> None:
    st.session_state["bills_used"] = st.session_state.get("bills_used", 0) + 1
    st.session_state["last_request"] = time.time()
    usage = daily_usage()
    with usage["lock"]:
        usage["count"] += 1


def decode_bill_report(file_bytes: bytes, mime_type: str, language: str) -> BillReport:
    response = generate_with_fallback(
        [
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            WEB_PROMPT.format(language=language) + date_rule(datetime.date.today()),
        ],
        types.GenerateContentConfig(response_mime_type="application/json", response_schema=BillReport),
    )
    return response.parsed




# ---------- Page style (dark mode, large text for all ages) ----------

st.set_page_config(page_title="Bill Decoder", page_icon="🧾", layout="centered")

st.markdown(
    """
    <style>
    :root {
        --bg: #0f1117;
        --surface: #1a1d29;
        --surface-2: #232736;
        --border: #2f3445;
        --text: #f3f4f6;
        --muted: #b4bac8;
        --blue: #3b82f6;
        --blue-dark: #1e40af;
        --red: #f87171;
        --green: #4ade80;
        --amber: #fbbf24;
    }

    /* Bigger base text so it is easy to read for everyone */
    html { font-size: 18px; }
    .stApp { background: var(--bg); color: var(--text); }
    .block-container { max-width: 760px; padding-top: 1.5rem; padding-bottom: 3rem; }
    p, li, label, .stMarkdown { line-height: 1.6; }

    /* Header */
    .hero {
        background: linear-gradient(135deg, #1e3a8a 0%, #4c1d95 100%);
        border: 1px solid #3b4a8a; border-radius: 22px;
        padding: 28px 26px 22px; margin-bottom: 28px;
        box-shadow: 0 12px 30px rgba(0,0,0,.45);
    }
    .hero h1 { color: #fff; font-size: 2.3rem; margin: 0 0 8px; padding: 0; }
    .hero p { color: #dbe4ff; font-size: 1.15rem; margin: 0 0 16px; }
    .badge {
        display: inline-block; background: rgba(255,255,255,.14); color: #fff;
        border-radius: 999px; padding: 6px 14px; margin: 0 8px 8px 0; font-size: .9rem;
    }

    /* Numbered steps */
    .step { display: flex; align-items: center; gap: 12px; margin: 22px 0 6px; }
    .step .num {
        flex: none; width: 40px; height: 40px; border-radius: 50%;
        background: var(--blue); color: #fff; font-weight: 800; font-size: 1.15rem;
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 4px 0 var(--blue-dark);
    }
    .step .title { font-size: 1.3rem; font-weight: 700; color: var(--text); }
    .hint { color: var(--muted); font-size: .95rem; margin: 0 0 10px 52px; }

    /* Upload box */
    [data-testid="stFileUploaderDropzone"] {
        background: var(--surface); border: 2px dashed var(--blue);
        border-radius: 16px; padding: 26px 18px;
    }
    [data-testid="stFileUploaderDropzone"]:hover { background: var(--surface-2); }

    /* Language choices as big tappable pills */
    div[role="radiogroup"] { gap: 10px; flex-wrap: wrap; }
    div[role="radiogroup"] > label {
        background: var(--surface); border: 2px solid var(--border);
        border-radius: 14px; padding: 10px 16px; margin: 0 !important;
        cursor: pointer; transition: border-color .15s, background .15s;
    }
    div[role="radiogroup"] > label:hover { border-color: var(--blue); }
    div[role="radiogroup"] > label:has(input:checked) {
        border-color: var(--blue); background: rgba(59,130,246,.18);
    }

    /* 3D buttons: raised, lift on hover, press down on click */
    .stButton > button, .stDownloadButton > button {
        width: 100%; min-height: 64px; font-size: 1.25rem; font-weight: 800;
        border-radius: 16px; border: none; color: #fff;
        background: linear-gradient(180deg, #60a5fa 0%, #2563eb 100%);
        box-shadow: 0 7px 0 var(--blue-dark), 0 12px 24px rgba(0,0,0,.5);
        transform: translateY(0);
        transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        color: #fff; border: none; filter: brightness(1.1);
        transform: translateY(-3px);
        box-shadow: 0 10px 0 var(--blue-dark), 0 18px 30px rgba(0,0,0,.55);
    }
    .stButton > button:active, .stDownloadButton > button:active {
        transform: translateY(6px);
        box-shadow: 0 1px 0 var(--blue-dark), 0 4px 8px rgba(0,0,0,.4);
    }
    .stButton > button:focus-visible, .stDownloadButton > button:focus-visible {
        outline: 3px solid var(--amber); outline-offset: 4px;
    }
    .stButton > button:disabled {
        background: var(--surface-2); color: #8a90a0;
        box-shadow: 0 5px 0 #11131b; transform: none; filter: none; cursor: not-allowed;
    }
    .stDownloadButton > button {
        background: linear-gradient(180deg, #4ade80 0%, #16a34a 100%);
        box-shadow: 0 7px 0 #14532d, 0 12px 24px rgba(0,0,0,.5);
    }
    .stDownloadButton > button:hover { box-shadow: 0 10px 0 #14532d, 0 18px 30px rgba(0,0,0,.55); }
    .stDownloadButton > button:active { box-shadow: 0 1px 0 #14532d, 0 4px 8px rgba(0,0,0,.4); }

    /* Result cards */
    .section { font-size: 1.45rem; font-weight: 800; margin: 30px 0 12px; color: var(--text); }
    .summary {
        background: rgba(59,130,246,.14); border: 1px solid rgba(59,130,246,.45);
        border-radius: 16px; padding: 16px 18px; font-size: 1.1rem; margin-bottom: 14px;
    }
    .card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 16px; padding: 16px 18px; margin-bottom: 12px;
    }
    .card .label { font-size: .85rem; color: var(--muted); font-weight: 600; letter-spacing: .03em; }
    .card .value { font-size: 1.4rem; font-weight: 800; margin-top: 4px; color: var(--text); }
    .card.big { border: 2px solid var(--blue); background: rgba(59,130,246,.10); }
    .card.big .value { font-size: 1.8rem; }
    .charge { display: flex; justify-content: space-between; gap: 14px; align-items: baseline; }
    .charge .name { font-weight: 700; font-size: 1.1rem; }
    .charge .amt { font-weight: 800; font-size: 1.15rem; white-space: nowrap; color: #93c5fd; }
    .why { color: var(--muted); font-size: 1rem; margin-top: 4px; }
    .flag { border-left: 6px solid var(--red); background: rgba(248,113,113,.10); }
    .flag .name { color: #fecaca; font-size: 1.1rem; }
    .tip, .ok { border-left: 6px solid var(--green); background: rgba(74,222,128,.08); font-size: 1.05rem; }
    .footer { color: var(--muted); font-size: .9rem; text-align: center; margin-top: 30px; }

    /* Due-date countdown banner */
    .due {
        border-radius: 16px; padding: 16px 18px; margin: 4px 0 16px;
        font-size: 1.2rem; font-weight: 800; display: flex; align-items: center; gap: 12px;
    }
    .due.ok   { background: rgba(74,222,128,.12); border: 2px solid var(--green); color: #bbf7d0; }
    .due.soon { background: rgba(251,191,36,.12); border: 2px solid var(--amber); color: #fde68a; }
    .due.late { background: rgba(248,113,113,.14); border: 2px solid var(--red); color: #fecaca; }
    .due .icon { font-size: 1.6rem; }
    .due .sub { display: block; font-size: .95rem; font-weight: 500; opacity: .9; }

    /* "What to do now" checklist */
    .todo { counter-reset: todo; }
    .todo .item {
        display: flex; gap: 14px; align-items: flex-start; font-size: 1.1rem;
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 14px; padding: 14px 16px; margin-bottom: 10px;
    }
    .todo .item::before {
        counter-increment: todo; content: counter(todo);
        flex: none; width: 32px; height: 32px; border-radius: 50%;
        background: var(--green); color: #052e16; font-weight: 800;
        display: flex; align-items: center; justify-content: center;
    }

    /* Friendly message card */
    .notice {
        display: flex; gap: 14px; align-items: center; margin: 18px 0;
        background: var(--surface); border: 1px solid var(--border);
        border-left: 6px solid var(--amber); border-radius: 14px; padding: 14px 16px;
        font-size: 1.05rem;
    }
    .notice .icon { font-size: 1.6rem; }
    .notice .sub { display: block; color: var(--muted); font-size: .95rem; margin-top: 2px; }

    /* Usage numbers */
    .stat .value { font-size: 1.6rem; }
    .stat .unit { font-size: 1rem; color: var(--muted); font-weight: 600; margin-left: 4px; }
    .note { color: var(--muted); font-size: .95rem; margin: 2px 0 12px; }
    .warn-card { border-left: 6px solid var(--amber); background: rgba(251,191,36,.10); }
    .subsidy { border-left: 6px solid var(--green); }
    .subsidy .amt { color: var(--green); }

    /* "What does this mean?" info buttons (native <details>, works with keyboard) */
    details.info { margin-top: 10px; }
    details.info summary {
        display: inline-flex; align-items: center; gap: 6px; min-height: 40px;
        list-style: none; cursor: pointer; user-select: none;
        color: #bfdbfe; font-weight: 700; font-size: .95rem;
        padding: 6px 14px; border: 1.5px solid rgba(59,130,246,.6); border-radius: 999px;
        transition: background .15s, border-color .15s;
    }
    details.info summary::-webkit-details-marker { display: none; }
    details.info summary:hover { background: rgba(59,130,246,.18); border-color: var(--blue); }
    details.info summary:focus-visible { outline: 3px solid var(--amber); outline-offset: 3px; }
    details.info[open] summary { background: rgba(59,130,246,.22); border-color: var(--blue); }
    details.info .body {
        margin-top: 10px; padding: 14px 16px; border-radius: 12px;
        background: var(--surface-2); border: 1px solid var(--border);
        color: var(--text); font-size: 1.02rem; line-height: 1.65;
    }
    .section-wrap { margin: 30px 0 12px; }
    .section-wrap .section { margin: 0; }
    .section-wrap details.info { margin-top: 6px; }

    /* Glossary */
    .term { font-weight: 800; color: #93c5fd; font-size: 1.05rem; }

    /* Phones */
    @media (max-width: 640px) {
        html { font-size: 17px; }
        .hero h1 { font-size: 1.9rem; }
        .hint { margin-left: 0; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def shown(value: str) -> bool:
    """False when the AI left a field empty or wrote "Not shown"."""
    return bool(value and value.strip()) and "not shown" not in value.lower()


def info_box(text: str, label: str = "ℹ️ What does this mean?") -> str:
    """A tap-to-open explanation. Returns '' when there is nothing to explain."""
    if not shown(text):
        return ""
    return f'<details class="info"><summary>{label}</summary><div class="body">{html.escape(text)}</div></details>'


def section(title: str, help_text: str = "") -> None:
    """Section heading with an optional 'What is this section?' button below it."""
    st.markdown(
        f'<div class="section-wrap"><div class="section">{title}</div>'
        f'{info_box(help_text, "ℹ️ What is this section?")}</div>',
        unsafe_allow_html=True,
    )


def charge_card(c: Charge, extra_class: str = "") -> None:
    st.markdown(
        f'<div class="card {extra_class}"><div class="charge"><span class="name">{html.escape(c.name)}</span>'
        f'<span class="amt">{html.escape(c.amount)}</span></div>'
        f'<div class="why">{html.escape(c.explanation)}</div>{info_box(c.info)}</div>',
        unsafe_allow_html=True,
    )


def notice(icon: str, title: str, hint: str = "") -> None:
    """A small, friendly message card used instead of raw error text."""
    sub = f'<span class="sub">{html.escape(hint)}</span>' if hint else ""
    st.markdown(
        f'<div class="notice"><span class="icon">{icon}</span>'
        f'<span><b>{html.escape(title)}</b>{sub}</span></div>',
        unsafe_allow_html=True,
    )


def friendly_error(e: Exception) -> tuple[str, str, str]:
    """Turn any error into (icon, title, hint) a non-technical person can understand."""
    code = getattr(e, "code", None)
    if code == 429:
        match = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?", str(e))
        minutes = (int(match.group(1) or 0) * 60 + int(match.group(2) or 0)) if match else 0
        hint = f"Please try again in about {minutes} minutes." if minutes else "Please try again later or tomorrow."
        return "📅", "Today's free limit is used up", hint
    if code == 503:
        return "⏳", "The AI is busy right now", "Please wait a minute and press the button again."
    if code in (400, 401, 403):
        return "🔧", "The app is not set up correctly", "Please let the app owner know."
    return "😕", "Something went wrong", "Please try again in a minute. If it keeps happening, try a clearer photo."


def card(label: str, value: str, extra_class: str = "") -> str:
    return (
        f'<div class="card {extra_class}"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(value)}</div></div>'
    )


def step(number: int, title: str, hint: str) -> None:
    st.markdown(
        f'<div class="step"><span class="num">{number}</span><span class="title">{title}</span></div>'
        f'<div class="hint">{hint}</div>',
        unsafe_allow_html=True,
    )


# ---------- Header ----------

st.markdown(
    """
    <div class="hero">
      <h1>🧾 Bill Decoder</h1>
      <p>Don't understand your bill? Upload a photo. We explain every charge in
      simple words and warn you about anything unusual.</p>
      <span class="badge">📷 Photo or PDF</span>
      <span class="badge">🗣️ 6 Indian languages</span>
      <span class="badge">🚩 Finds hidden charges</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- Input ----------

step(1, "Upload your bill", "Electricity, water, gas, mobile or broadband. Take the photo in good light and show the whole bill.")
uploaded = st.file_uploader(
    "Upload your bill",
    type=["jpg", "jpeg", "png", "webp", "pdf"],
    label_visibility="collapsed",
)

if uploaded and uploaded.type.startswith("image/"):
    with st.expander("👀 Check your photo"):
        st.image(uploaded, width="stretch")

step(2, "Choose your language", "The explanation will be written in this language.")
language_choice = st.radio(
    "Language", LANGUAGES, horizontal=True, label_visibility="collapsed"
)
language = language_choice.split()[-1]

step(3, "Get your explanation", "It takes about 10–30 seconds.")
decode = st.button(
    "✨ Explain my bill" if uploaded else "⬆️ Upload a bill first",
    type="primary",
    disabled=uploaded is None,
)

# ---------- Result ----------

if decode and uploaded:
    if not os.getenv("GEMINI_API_KEY"):
        logging.error("GEMINI_API_KEY is not set. Add it to .env (local) or the app's Secrets (cloud).")
        notice("🔧", "The app is not set up correctly", "Please let the app owner know.")
        st.stop()
    problem = check_file(uploaded.type, uploaded.size)
    if problem:
        notice("📄", problem, "Please upload a JPG, PNG, WEBP or PDF under 10 MB.")
        st.stop()
    problem = usage_problem()
    if problem:
        notice("⏳", problem)
        st.stop()

    record_usage()
    with st.spinner("🔍 Reading your bill… please wait"):
        try:
            report = decode_bill_report(uploaded.getvalue(), uploaded.type, language)
        except Exception as e:  # never show raw error text to users
            logging.exception("Bill decoding failed")
            notice(*friendly_error(e))
            st.stop()

    if report is None:
        notice("😕", "We could not read this bill", "Please try a clearer photo in good light.")
        st.stop()
    if not report.is_bill:
        notice("🤔", "This doesn't look like a bill", "Please upload a photo or PDF of an electricity, water, gas, mobile or broadband bill.")
        st.stop()

    today = datetime.date.today()
    odd = suspicious_dates([report.bill_date, report.due_date, report.billing_period], today)

    # 1. The most important facts first
    help_ = report.section_help
    section("📋 Your bill at a glance", help_.at_a_glance)
    if report.summary:
        st.markdown(f'<div class="summary">{html.escape(report.summary)}</div>', unsafe_allow_html=True)

    # Due-date countdown, calculated from today's date
    due = parse_date(report.due_date)
    total = parse_amount(report.total_amount)
    if total is not None and total <= 0:
        st.markdown(
            '<div class="due ok"><span class="icon">🎉</span><span>Nothing to pay this time'
            '<span class="sub">Your balance is zero or in credit.</span></span></div>',
            unsafe_allow_html=True,
        )
    elif due and report.due_date not in odd:
        days = (due - today).days
        if days < 0:
            css, icon, text = "late", "⛔", f"Overdue by {-days} day{'s' if days != -1 else ''}"
            sub = "Pay as soon as possible to avoid extra late fees."
        elif days <= 5:
            css, icon, text = "soon", "⏰", "Due today" if days == 0 else f"Due in {days} day{'s' if days != 1 else ''}"
            sub = "Pay soon to avoid a late fee."
        else:
            css, icon, text = "ok", "✅", f"{days} days left to pay"
            sub = f"Pay before {report.due_date}."
        st.markdown(
            f'<div class="due {css}"><span class="icon">{icon}</span><span>{text}'
            f'<span class="sub">{html.escape(sub)}</span></span></div>',
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2)
    c1.markdown(card("💵 AMOUNT TO PAY", report.total_amount, "big"), unsafe_allow_html=True)
    c2.markdown(card("📅 PAY BEFORE", report.due_date, "big"), unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    c3.markdown(card("🏢 BILL FROM", f"{report.provider} · {report.bill_type}"), unsafe_allow_html=True)
    c4.markdown(card("🗓️ BILLING PERIOD", report.billing_period), unsafe_allow_html=True)
    c5, c6 = st.columns(2)
    c5.markdown(card("🧾 BILL DATE", report.bill_date), unsafe_allow_html=True)
    c6.markdown(card("📑 PLAN / TARIFF", report.plan_or_tariff), unsafe_allow_html=True)
    if shown(report.amount_after_due_date):
        st.markdown(card("⚠️ IF YOU PAY LATE", report.amount_after_due_date, "warn-card"), unsafe_allow_html=True)

    # Date check: catches a misread year (e.g. a 2026 bill read as 2023)
    if odd:
        st.warning(
            f"📆 Some dates look unusual ({', '.join(odd)}). If your bill is more recent, "
            "the photo may be unclear. Please check the dates on your paper bill."
        )

    # Math check: the AI can misread numbers, so verify the charges add up.
    # Subsidies listed only in the subsidies section are deductions too.
    charge_names = {c.name.strip().lower() for c in report.charges}
    amounts = [c.amount for c in report.charges] + [
        "-" + s.amount.replace("-", "") for s in report.subsidies if s.name.strip().lower() not in charge_names
    ]
    if charges_add_up(amounts, report.total_amount) is False:
        st.warning(
            "🧮 The charges we read don't add up to the total. The photo may be unclear, "
            "so please double-check the amounts on your paper bill."
        )

    # 2. What to do now
    if report.action_steps:
        section("✅ What you should do now", help_.actions)
        items = "".join(f'<div class="item">{html.escape(s)}</div>' for s in report.action_steps)
        st.markdown(f'<div class="todo">{items}</div>', unsafe_allow_html=True)

    # 3. Warnings, so nobody misses them
    section(f"🚩 Things to check ({len(report.red_flags)})", help_.red_flags)
    if report.red_flags:
        for f in report.red_flags:
            st.markdown(
                f'<div class="card flag"><div class="name"><b>⚠️ {html.escape(f.title)}</b></div>'
                f'<div class="why">{html.escape(f.detail)}</div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown('<div class="card ok">✅ Nothing unusual found. Your bill looks normal.</div>', unsafe_allow_html=True)

    # 4. Usage and meter readings
    u = report.usage
    if shown(u.units_used):
        section("⚡ How much you used", help_.usage)
        unit = html.escape(u.unit_name) if shown(u.unit_name) else ""
        s1, s2 = st.columns(2)
        s1.markdown(
            f'<div class="card stat"><div class="label">TOTAL USED</div>'
            f'<div class="value">{html.escape(u.units_used)}<span class="unit">{unit}</span></div></div>',
            unsafe_allow_html=True,
        )
        s2.markdown(
            f'<div class="card stat"><div class="label">PER DAY (AVERAGE)</div>'
            f'<div class="value">{html.escape(u.daily_average)}<span class="unit">{unit}</span></div></div>',
            unsafe_allow_html=True,
        )
        if shown(u.previous_reading) or shown(u.current_reading):
            r1, r2, r3 = st.columns(3)
            r1.markdown(card("PREVIOUS READING", u.previous_reading), unsafe_allow_html=True)
            r2.markdown(card("CURRENT READING", u.current_reading), unsafe_allow_html=True)
            estimated = "estim" in u.reading_type.lower()
            r3.markdown(
                card("READING TYPE", ("⚠️ " if estimated else "✅ ") + u.reading_type, "warn-card" if estimated else ""),
                unsafe_allow_html=True,
            )
        if shown(u.compared_to_last_period):
            st.markdown(f'<div class="note">📊 {html.escape(u.compared_to_last_period)}</div>', unsafe_allow_html=True)

    # Usage history chart, only when the bill prints past months
    if len(report.usage_history) >= 2:
        unit_label = u.unit_name if shown(u.unit_name) else "Units"
        section(f"📈 Your usage in past months ({html.escape(unit_label)})")
        df = pd.DataFrame([{"Period": m.period, unit_label: m.units} for m in report.usage_history])
        chart = (
            alt.Chart(df)
            .mark_bar(color="#3b82f6", cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=28)
            .encode(
                x=alt.X("Period:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelColor="#b4bac8", labelFontSize=13)),
                y=alt.Y(f"{unit_label}:Q", title=None, axis=alt.Axis(labelColor="#b4bac8", gridColor="#2f3445", domain=False, ticks=False, labelFontSize=13)),
                tooltip=[alt.Tooltip("Period:N"), alt.Tooltip(f"{unit_label}:Q")],
            )
            .properties(height=240, background="transparent")
            .configure_view(stroke=None)
        )
        st.altair_chart(chart, width="stretch")
        with st.expander("Show as a table"):
            st.dataframe(df, hide_index=True, width="stretch")

    # 5. Every charge explained
    section(f"💰 What you are paying for ({len(report.charges)})", help_.charges)
    for c in report.charges:
        charge_card(c)

    # 6. Subsidies and discounts
    if report.subsidies:
        section("🎁 Discounts and subsidies you got", help_.subsidies)
        for s in report.subsidies:
            charge_card(s, "subsidy")

    # 7. Payment details
    if shown(report.last_payment) or report.payment_options:
        section("💳 Payment details", help_.payment)
        if shown(report.last_payment):
            st.markdown(card("LAST PAYMENT RECEIVED", report.last_payment), unsafe_allow_html=True)
        if report.payment_options:
            ways = "".join(f"<li>{html.escape(p)}</li>" for p in report.payment_options)
            st.markdown(f'<div class="card"><div class="label">WAYS TO PAY</div><ul>{ways}</ul></div>', unsafe_allow_html=True)

    # 8. Tips
    section("💡 Ways to save money", help_.tips)
    for t in report.tips:
        st.markdown(f'<div class="card tip">💡 {html.escape(t)}</div>', unsafe_allow_html=True)

    # 9. Words on the bill explained
    if report.glossary:
        with st.expander(f"📖 Words on your bill explained ({len(report.glossary)})"):
            for g in report.glossary:
                st.markdown(
                    f'<div class="card"><span class="term">{html.escape(g.term)}</span>'
                    f'<div class="why">{html.escape(g.meaning)}</div></div>',
                    unsafe_allow_html=True,
                )

    # Plain-text copy the user can save or share
    lines = [
        f"Bill: {report.bill_type} ({report.provider})",
        f"Plan / tariff: {report.plan_or_tariff}",
        f"Bill date: {report.bill_date}",
        f"Period: {report.billing_period}",
        f"Amount to pay: {report.total_amount}",
        f"Due date: {report.due_date}",
        f"If paid late: {report.amount_after_due_date}",
        "",
        "What to do now:",
        *[f"- {s}" for s in report.action_steps],
        "",
        "Things to check:",
        *([f"- {f.title}: {f.detail}" for f in report.red_flags] or ["- None"]),
        "",
        f"Usage: {u.units_used} {u.unit_name} (reading: {u.reading_type})",
        "",
        "Charges:",
        *[f"- {c.name}: {c.amount} — {c.explanation}\n    What it means: {c.info}" for c in report.charges],
        "",
        "Subsidies:",
        *([f"- {s.name}: {s.amount} — {s.explanation}" for s in report.subsidies] or ["- None"]),
        "",
        "Tips:",
        *[f"- {t}" for t in report.tips],
    ]
    st.write("")
    st.download_button(
        "⬇️ Save this explanation",
        "\n".join(lines),
        file_name="bill-explanation.txt",
        width="stretch",
    )

st.markdown(
    '<div class="footer">🔒 Your bill is sent to Google Gemini to be read and is not stored by this app.<br>'
    "This is for information only, not financial advice.</div>",
    unsafe_allow_html=True,
)
