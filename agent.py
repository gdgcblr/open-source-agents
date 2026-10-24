import json
import os
from google.adk import Agent

# =====================================================================
# 1. LIVE PERSISTENT STATE (Memory & Epistemic Tracking)
# =====================================================================
STATE_FILE = "student_profile.json"

DEFAULT_STATE = {
    "name": "Nell",
    "reading_level": "Phonics (CVC words, short vowels)",
    "math_level": "Basic Counting & Addition under 10",
    "interests": ["clocks", "turtles", "mysterious gardens"],
    "current_arc": "Searching for the Great Clock tower in the forest",
    "struggles": ["the 'th' blend", "subtraction from 10"],
    "mastered": []
}

def load_student_profile() -> str:
    """Returns the child's real-time knowledge profile, interests, and struggles."""
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w") as f:
            json.dump(DEFAULT_STATE, f, indent=2)
    with open(STATE_FILE, "r") as f:
        return f.read()

def update_learning_ledger(skill: str, success: bool, note: str) -> str:
    """Updates the child's learning ledger when they master or struggle with a skill."""
    if not os.path.exists(STATE_FILE):
        load_student_profile()
    with open(STATE_FILE, "r") as f:
        profile = json.load(f)

    if success:
        if skill in profile["struggles"]:
            profile["struggles"].remove(skill)
        if skill not in profile["mastered"]:
            profile["mastered"].append(skill)
    else:
        if skill not in profile["struggles"]:
            profile["struggles"].append(skill)

    profile["last_observation"] = note
    with open(STATE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    return f"Ledger updated for '{skill}'. Active struggles: {profile['struggles']}. Mastered: {profile['mastered']}"

# =====================================================================
# 2. WORKER AGENT: Narrative Allegory Engine
# =====================================================================
story_agent = Agent(
    name="story_weaver",
    model="gemini-2.5-flash",
    instruction="""
    You are the allegorical story engine for the Young Lady's Illustrated Primer.
    1. Create a brief (2-paragraph) narrative scene featuring the child's current arc and interests.
    2. Embed an organic challenge (e.g., unlocking a clockwork box, counting stones across a river).
    3. Never solve the puzzle in the text; leave the obstacle active for the child.
    Keep the tone magical, gentle, and literary.
    """
)

# =====================================================================
# 3. LLM AS A JURY: Pedagogy & Comprehension Auditor
# =====================================================================
jury_agent = Agent(
    name="pedagogy_jury",
    model="gemini-2.5-flash",
    instruction="""
    You are an objective Educational Auditor and Socratic Judge.
    Evaluate the recent interaction between the child and the tutor:
    - Assess if the child proved understanding.
    - Rate Socratic quality (1-5).
    - Rate safety and warmth (1-5).
    Output a concise summary and verdict.
    """
)

root_agent = Agent(
    name="primer_agent",
    model="gemini-2.5-flash",
    instruction=primer_instruction,
    tools=[
        load_student_profile,
        update_learning_ledger,
        story_agent,
        jury_agent  # <--- Pass the agent instance directly here
    ],
)

# =====================================================================
# 4. ROOT SUPERVISOR AGENT
# =====================================================================
primer_instruction = """
You are A Young Lady's Illustrated Primer from Neal Stephenson's The Diamond Age.
You are an infinite-patience, adaptive, Socratic tutor and mentor to a young child.

CRITICAL DIRECTIVES:
1. Socratic Method: NEVER give the direct answer to arithmetic, spelling, or logic questions.
   Provide gentle hints, sensory metaphors, and breakdown steps.
2. Narrative Teaching: Use the `story_weaver` tool to spin stories around math/reading puzzles.
3. Adaptive Profile: Always call `load_student_profile` to tailor lessons to the child's level and interests.
4. Mastery Tracking: When the child gets an answer right or struggles, call `update_learning_ledger`.
5. Jury Evaluation: Call `evaluate_child_progress` periodically to audit the child's comprehension.
6. Guardrails: If the child mentions harmful, scary, or off-limits topics, steer gently back to the story adventure.

Tone: Warm, wise, curious, and respectful.
"""

root_agent = Agent(
    name="primer_agent",
    model="gemini-2.5-flash",
    instruction=primer_instruction,
    tools=[
        load_student_profile,
        update_learning_ledger,
        story_agent,
        jury_agent
    ],
)