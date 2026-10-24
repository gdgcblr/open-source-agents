"""RentRakshak Streamlit demo UI."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rentrakshak.db.database import init_db
from rentrakshak.models.schemas import AnonymousExperienceInput, RiskCategory, VacatingPostInput
from rentrakshak.services.checklist import build_rental_checklist, get_karnataka_rental_guidance
from rentrakshak.services.community import create_anonymous_experience, search_anonymous_experiences
from rentrakshak.services.safety_report import generate_rental_safety_report
from rentrakshak.services.demo_seed import seed_demo
from rentrakshak.services.vacating import create_vacating_post, search_available_rooms

RISK_LABELS = {
    RiskCategory.LOW.value: ("🟢", "Low concern"),
    RiskCategory.NEEDS_VERIFICATION.value: ("🟡", "Needs verification"),
    RiskCategory.HIGH.value: ("🟠", "High concern"),
    RiskCategory.CRITICAL.value: ("🔴", "Critical warning"),
}

st.set_page_config(
    page_title="RentRakshak",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Readable inputs on all themes (fixes invisible typed text)
st.markdown(
    """
    <style>
    .stTextArea textarea, .stTextInput input, .stNumberInput input {
        color: #111111 !important;
        background-color: #ffffff !important;
        -webkit-text-fill-color: #111111 !important;
    }
    .risk-banner {
        padding: 1rem 1.25rem;
        border-radius: 8px;
        background: #f0f4f8;
        border: 1px solid #c5d0dc;
        color: #111111;
        margin: 0.75rem 0 1rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_db()

if "listing_area" not in st.session_state:
    st.session_state.listing_area = ""
if "last_report" not in st.session_state:
    st.session_state.last_report = None
if "db_seeded_msg" not in st.session_state:
    st.session_state.db_seeded_msg = None


def _load_fixture(name: str) -> None:
    path = FIXTURES / name
    if not path.is_file():
        st.error(f"Missing fixture: {path}")
        return
    st.session_state.listing_area = path.read_text(encoding="utf-8")
    st.session_state.last_report = None


def _run_seed() -> None:
    try:
        db = seed_demo()
        st.session_state.db_seeded_msg = f"Demo data loaded at {db}"
    except Exception as exc:
        st.session_state.db_seeded_msg = f"Seed failed: {exc}"


with st.sidebar:
    st.header("RentRakshak")
    st.caption("Rent smarter. Stay safer.")
    page = st.radio(
        "Menu",
        [
            "Start here",
            "Check a listing",
            "Tenant stories",
            "Rooms vacating soon",
            "Before you sign",
            "About",
        ],
    )
    st.divider()
    if st.button("Load demo database", type="primary", use_container_width=True):
        _run_seed()
        st.rerun()
    if st.session_state.db_seeded_msg:
        if st.session_state.db_seeded_msg.startswith("Seed failed"):
            st.error(st.session_state.db_seeded_msg)
        else:
            st.success("Demo DB ready — try Koramangala / Whitefield")

st.title("RentRakshak")
st.caption("Before you pay a deposit, check the risks. Listings are **not** verified.")

if page == "Start here":
    st.markdown(
        """
        1. Sidebar → **Load demo database** (community + vacating samples)  
        2. **Check a listing** → **Load suspicious sample** → **Run check**  
        3. **Tenant stories** → locality `Koramangala`  
        4. **Rooms vacating soon** → locality `Whitefield`  

        No API key needed for listing checks.
        """
    )
    if st.button("Load demo database from here"):
        _run_seed()
        st.rerun()

elif page == "Check a listing":
    st.subheader("Analyze a listing")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Load suspicious sample", use_container_width=True):
            _load_fixture("suspicious_listing.txt")
            st.rerun()
    with b2:
        if st.button("Load normal sample", use_container_width=True):
            _load_fixture("clean_listing.txt")
            st.rerun()
    with b3:
        if st.button("Clear", use_container_width=True):
            st.session_state.listing_area = ""
            st.session_state.last_report = None
            st.rerun()

    listing = st.text_area(
        "Listing text",
        height=200,
        key="listing_area",
        placeholder="Paste property listing here…",
    )
    chat = st.text_area(
        "Landlord / broker chat (optional)",
        height=100,
        key="chat_area",
        placeholder="Optional WhatsApp transcript…",
    )
    locality = st.text_input("Locality hint (optional)", key="locality_hint")

    if st.button("Run check", type="primary"):
        if not (listing or "").strip():
            st.error("Paste or load a listing first.")
        else:
            report = generate_rental_safety_report(
                listing,
                (chat or "").strip() or None,
                locality_hint=(locality or "").strip() or None,
            )
            st.session_state.last_report = json.loads(
                json.dumps(report.model_dump(), default=str)
            )

    if st.session_state.last_report:
        rep = st.session_state.last_report
        icon, label = RISK_LABELS.get(
            rep["risk_category"],
            ("⚪", rep["risk_category"]),
        )
        st.markdown(
            f'<div class="risk-banner"><strong>{icon} {label}</strong><br/>'
            f'{rep.get("risk_reasoning", "")}</div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        prop = rep.get("property") or {}
        c1.metric("Red flags", len(rep.get("findings") or []))
        c2.metric("Locality", prop.get("locality") or "—")
        c3.metric(
            "Rent in text",
            f"₹{prop['monthly_rent_inr']}" if prop.get("monthly_rent_inr") else "—",
        )
        for f in rep.get("findings") or []:
            with st.expander(f"{f['rule_id']} — {f['severity']}", expanded=True):
                st.write(f["explanation"])
                st.info(f"Evidence: {f['evidence_excerpt']}")
                st.write(f"**Next:** {f['recommended_next_step']}")
        re = rep.get("rent_estimate")
        if re:
            st.markdown("#### Rent benchmark (demo data)")
            if re.get("sufficient_data"):
                st.success(
                    f"₹{re['rent_min_inr']:,} – ₹{re['rent_max_inr']:,}/mo "
                    f"(median ₹{re['rent_median_inr']:,})"
                )
            else:
                st.warning("Not enough comparables — no market guess.")
        with st.expander("Full JSON"):
            st.json(rep)

elif page == "Tenant stories":
    st.subheader("Anonymous tenant experiences")
    loc_f = st.text_input("Locality", value="Koramangala", key="comm_loc")
    if st.button("Search", type="primary"):
        st.session_state.comm_search = True
    if st.session_state.get("comm_search") or loc_f:
        res = search_anonymous_experiences(locality=loc_f.strip() or None)
        if not res["items"]:
            st.warning("No posts. Use sidebar **Load demo database**, then search **Koramangala**.")
        for item in res["items"]:
            with st.container(border=True):
                st.markdown(f"**{item['locality']}** · {item['category']} · {item['sentiment']}")
                st.write(item["experience_text"])

    with st.form("exp_form"):
        st.markdown("#### Submit experience")
        eloc = st.text_input("Locality", "HSR Layout")
        eptype = st.text_input("Property type", "apartment")
        ecat = st.selectbox(
            "Category",
            ["Deposit and refund", "Maintenance", "Communication", "General rental experience"],
        )
        esent = st.selectbox("Sentiment", ["positive", "neutral", "negative"])
        etext = st.text_area("Your story (min 20 chars, no phone/email)", height=100)
        if st.form_submit_button("Submit"):
            try:
                out = create_anonymous_experience(
                    AnonymousExperienceInput(
                        locality=eloc,
                        property_type=eptype,
                        category=ecat,
                        sentiment=esent,
                        experience_text=etext,
                    )
                )
                if out["success"]:
                    st.success(f"Status: {out['moderation_status']}")
                    st.code(out["edit_token"])
                else:
                    st.error(out.get("message", "Rejected"))
            except Exception as exc:
                st.error(str(exc))

elif page == "Rooms vacating soon":
    st.subheader("Available rooms")
    vloc = st.text_input("Locality", value="Whitefield", key="vac_loc")
    if st.button("Search rooms", type="primary"):
        st.session_state.vac_search = True
    if st.session_state.get("vac_search") or vloc:
        rooms = search_available_rooms(locality=vloc.strip() or None)
        if not rooms["items"]:
            st.warning("No rooms. Sidebar → **Load demo database**, then **Whitefield**.")
        for r in rooms["items"]:
            with st.container(border=True):
                st.markdown(f"**{r['locality']}** · {r['room_type']} · ₹{r['monthly_rent_inr']:,}/mo")
                st.write(r["description"])

elif page == "Before you sign":
    st.subheader("Karnataka rental checklist")
    for item in build_rental_checklist():
        with st.expander(item.title):
            st.write(item.description)
    for ref in get_karnataka_rental_guidance():
        st.markdown(f"- [{ref.title}]({ref.url})")

else:
    st.markdown(
        "Hackathon demo for Bengaluru renters. Not legal advice. "
        "For AI chat: `adk web adk_agent` with Ollama or Gemini."
    )
