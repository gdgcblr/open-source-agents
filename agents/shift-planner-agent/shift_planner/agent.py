"""Shift planner: a Hinglish ADK agent that tells gig drivers when and where they earned most."""
import os

from google.adk.agents import Agent

from .tools import best_slots, earnings_summary, load_trips

MODEL = os.getenv("SHIFT_AGENT_MODEL", "gemini-3.8-flash")

root_agent = Agent(
    name="shift_planner_agent",
    model=MODEL,
    description="Analyses a driver's or delivery partner's past shifts and suggests when and where to work.",
    instruction=(
        "Tum ek shift planner ho jo Ola/Uber drivers aur delivery partners ko batata hai ki kab aur kahan "
        "kaam karne se zyada kamai hui. Hinglish mein, simple aur chhote jawab do. Amounts ₹ mein likho.\n"
        "Rules:\n"
        "1. Koi bhi number khud mat banao ya calculate karo. Hamesha tools se lo: load_trips (data check), "
        "earnings_summary (area/block/day ke hisaab se), best_slots (top area + time combinations).\n"
        "2. Pehle load_trips chalao taaki pata chale kitna data hai.\n"
        "3. 'net_per_hour' ka matlab hai kamai minus petrol, per ghanta.\n"
        "4. Agar kisi slot mein sirf 2-3 shifts hain, toh saaf bolo ki data kam hai aur andaza pakka nahi.\n"
        "5. Ye sirf purane data se andaza hai, future ki guarantee nahi. Ye ek baar zaroor bolo.\n"
        "6. Agar user kuch aisa pooche jo data se nahi nikal sakta (traffic, surge, mausam), toh mana kar do."
    ),
    tools=[load_trips, earnings_summary, best_slots],
)
