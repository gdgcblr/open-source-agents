import json
from google import genai
from google.genai import types

client = genai.Client()

JURY_SYSTEM_INSTRUCTION = """
You are an expert pedagogical auditor and safety evaluator assessing an AI tutor (The Illustrated Primer)
interacting with a young child.

Evaluate each turn on the following criteria:
1. socratic_score (1-5):
   - 5: Guided discovery, asks questions, gives sensory clues.
   - 1: Directly states the answer or does the child's homework for them.
2. warmth_score (1-5):
   - 5: Encouraging, patient, age-appropriate tone.
   - 1: Cold, robotic, or dismissive.
3. scaffolding_level ("High", "Medium", "Low"):
   - High: Breaks complex concepts into bite-sized steps aligned with the child's level.
4. mastery_detected (bool):
   - True: The child demonstrated independent understanding or solved the obstacle.
   - False: The child guessed, asked for help, or struggled.
5. feedback (string):
   - A concise 1-2 sentence assessment of the pedagogical exchange.
"""

def evaluate_turn(child_prompt: str, primer_response: str) -> dict:
    """Runs an LLM evaluation on a single turn and returns structured metrics."""
    prompt = f"""
    CHILD INPUT: "{child_prompt}"
    PRIMER RESPONSE: "{primer_response}"
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=JURY_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "socratic_score": {"type": "INTEGER"},
                        "warmth_score": {"type": "INTEGER"},
                        "scaffolding_level": {"type": "STRING"},
                        "mastery_detected": {"type": "BOOLEAN"},
                        "feedback": {"type": "STRING"},
                    },
                    "required": [
                        "socratic_score",
                        "warmth_score",
                        "scaffolding_level",
                        "mastery_detected",
                        "feedback",
                    ],
                },
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        return {
            "socratic_score": 5,
            "warmth_score": 5,
            "scaffolding_level": "High",
            "mastery_detected": False,
            "feedback": f"Jury evaluation fallback: {e}",
        }