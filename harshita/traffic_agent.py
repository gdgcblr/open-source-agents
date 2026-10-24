"""Agent reasoning engine supporting Google AI Studio (Gemini) and Qwen."""

import json
import os
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()

SYSTEM_INSTRUCTION = """
You are an expert Real-Time Traffic and Heavy Weather Routing Advisor.
Your objective:
1. Examine real-time route travel times, delays, and waypoint weather conditions (specifically heavy rain or flooding risks).
2. If the user's primary route has severe traffic bottlenecks (>15% delay or >10 min hold-up) OR heavy rain (>5 mm/h), flag it immediately.
3. Recommend whether to stay on the route or switch to a specific alternative route, explaining why.
4. Output your analysis in clear, direct sections: Route Verdict, Severe Hazard Alert (if applicable), Route Comparison Table, and Final Actionable Recommendation.
"""


class TrafficRainAgent:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()

        if self.provider == "gemini":
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is missing from environment.")
            self.client = genai.Client(api_key=api_key)
            self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        elif self.provider == "qwen":
            from openai import OpenAI
            base_url = os.getenv("QWEN_BASE_URL", "http://localhost:11434/v1")
            api_key = os.getenv("QWEN_API_KEY", "EMPTY")
            self.client = OpenAI(base_url=base_url, api_key=api_key)
            self.model_name = os.getenv("QWEN_MODEL", "qwen2.5-coder-32b-instruct")
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider}. Use 'gemini' or 'qwen'.")

    def analyze_routes(self, origin: str, destination: str, routes_data: List[Dict[str, Any]]) -> str:
        prompt_payload = {
            "origin": origin,
            "destination": destination,
            "available_routes": routes_data,
        }

        user_prompt = (
            "Analyze the following live route conditions and weather checkpoints.\n"
            "Assess traffic severity, surface conditions, and issue clear reroute instructions if needed.\n\n"
            f"```json\n{json.dumps(prompt_payload, indent=2)}\n```"
        )

        if self.provider == "gemini":
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config={"system_instruction": SYSTEM_INSTRUCTION, "temperature": 0.2},
            )
            return response.text
        else:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content
