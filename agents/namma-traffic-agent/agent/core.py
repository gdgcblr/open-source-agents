"""
core.py - Bengaluru Traffic Copilot AI Agent
Provides tool-calling agent capabilities using Google GenAI SDK (Gemini 2.5)
with seamless deterministic offline fallback for 100% out-of-the-box reproducibility.
"""

import os
import json
import re
from typing import Dict, Any, Optional

from .tools import (
    get_route_traffic,
    check_chokepoints,
    get_metro_alternative,
    get_weather_waterlogging_alerts,
    calculate_best_departure_window,
    _normalize_name
)

# System prompt defining agent persona and Bengaluru transit domain expertise
SYSTEM_PROMPT = """You are "Namma Traffic Copilot", an elite, empathetic, and hyper-local Bengaluru traffic intelligence AI agent.
Your mission is to help commuters, tech workers, and travelers navigate Bangalore's notorious traffic with realistic, actionable advice.

You have access to specialized transit tools:
1. `get_route_traffic(origin, destination, hour, is_raining)`: Road travel times, congestion rating, and delays.
2. `check_chokepoints(junction)`: Live status for Silk Board, Tin Factory, Hebbal, Marathahalli, Ecospace, etc.
3. `get_metro_alternative(origin, destination)`: Multimodal comparison with Namma Metro (Purple, Green, Yellow lines) including time and cost saved.
4. `get_weather_waterlogging_alerts(area)`: Waterlogging in underpasses, rain impact, and BTP advisories.
5. `calculate_best_departure_window(origin, destination, target_hour)`: Analysis of best time to depart.

Guidance:
- Be direct, realistic, and use local Bengaluru context (e.g., ORR rush, Silk Board delays, Metro Purple line advantage).
- When a user asks about a route, ALWAYS compare road travel with Namma Metro if applicable.
- Warn them about known chokepoints and suggest specific departure timing.
- Keep the tone encouraging, practical, and conversational with clean markdown formatting.
"""


class NammaTrafficAgent:
    """The central Bengaluru Traffic Copilot Agent."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.client = None
        self.model_name = "gemini-2.5-flash"
        self._init_client()

    def _init_client(self):
        """Initializes Google GenAI client if credentials exist."""
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[Warning] Could not initialize Google GenAI Client: {e}. Falling back to local heuristic mode.")
                self.client = None

    def query(self, user_prompt: str, is_raining: bool = False, target_hour: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes a user query. If Gemini API key is available, uses Gemini tool calling;
        otherwise runs local deterministic intent & tool execution.
        """
        if self.client:
            try:
                return self._run_gemini_agent(user_prompt, is_raining, target_hour)
            except Exception as e:
                # Graceful fallback if API quota or connectivity fails
                return self._run_local_heuristics(user_prompt, is_raining, target_hour, error_note=str(e))
        else:
            return self._run_local_heuristics(user_prompt, is_raining, target_hour)

    def _run_gemini_agent(self, user_prompt: str, is_raining: bool, target_hour: Optional[int]) -> Dict[str, Any]:
        """Runs tool-calling reasoning loop with Gemini 2.5 Flash."""
        from google.genai import types

        # Declare tools to Gemini
        available_tools = [
            get_route_traffic,
            check_chokepoints,
            get_metro_alternative,
            get_weather_waterlogging_alerts,
            calculate_best_departure_window
        ]

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=available_tools,
                temperature=0.2
            )
        )

        tool_calls_executed = []
        # If the model produced tool calls, execute them
        if response.function_calls:
            tool_outputs = []
            for call in response.function_calls:
                fn_name = call.name
                fn_args = dict(call.args)
                tool_calls_executed.append({"tool": fn_name, "args": fn_args})

                if fn_name == "get_route_traffic":
                    result = get_route_traffic(**fn_args)
                elif fn_name == "check_chokepoints":
                    result = check_chokepoints(**fn_args)
                elif fn_name == "get_metro_alternative":
                    result = get_metro_alternative(**fn_args)
                elif fn_name == "get_weather_waterlogging_alerts":
                    result = get_weather_waterlogging_alerts(**fn_args)
                elif fn_name == "calculate_best_departure_window":
                    result = calculate_best_departure_window(**fn_args)
                else:
                    result = {"error": f"Unknown tool {fn_name}"}

                tool_outputs.append({
                    "name": fn_name,
                    "response": {"result": result}
                })

            # Send tool outputs back to Gemini to synthesize final commuter advice
            second_response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]),
                    types.Content(role="model", parts=[types.Part.from_function_call(name=fc.name, args=fc.args) for fc in response.function_calls]),
                    types.Content(role="user", parts=[types.Part.from_function_response(name=to["name"], response=to["response"]) for to in tool_outputs])
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.3
                )
            )

            return {
                "mode": "gemini-2.5-flash-agent",
                "response": second_response.text,
                "tools_used": tool_calls_executed,
                "raw_tool_data": [to["response"]["result"] for to in tool_outputs]
            }

        return {
            "mode": "gemini-2.5-flash-direct",
            "response": response.text,
            "tools_used": [],
            "raw_tool_data": []
        }

    def _run_local_heuristics(
        self,
        prompt: str,
        is_raining: bool = False,
        target_hour: Optional[int] = None,
        error_note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Local deterministic reasoning engine. Extracts origin/destination,
        chokepoints, rain queries, and departure times, returning rich structured data.
        """
        lower = prompt.lower()
        
        # Check if rain/waterlogging query
        if any(w in lower for w in ["rain", "flood", "waterlog", "underpass", "weather", "downpour"]):
            data = get_weather_waterlogging_alerts()
            summary = (
                f"🌧️ **Bengaluru Rain & Waterlogging Advisory**\n\n"
                f"There are currently **{data['waterlogged_hotspots_count']} monitored hotspots** with standing water risks.\n"
                f"- **Kadubeesanahalli Underpass:** {data['alerts'][0]['advisory']}\n"
                f"- **Okalipuram Underpass:** {data['alerts'][1]['advisory']}\n"
                f"- **Silk Board Service Roads:** Submerged during intense rain.\n\n"
                f"💡 *Advice:* Avoid low sedan cars through railway underpasses; plan extra 30-45 mins buffer time."
            )
            return {
                "mode": "local-heuristic-engine",
                "response": summary,
                "tools_used": [{"tool": "get_weather_waterlogging_alerts", "args": {"area": "all"}}],
                "raw_tool_data": [data],
                "fallback_reason": error_note or "GEMINI_API_KEY not configured (offline mode)"
            }

        # Check if single chokepoint query
        for cp in ["silk board", "tin factory", "hebbal", "marathahalli", "ecospace", "sony world", "goraguntepalya"]:
            if cp in lower and not any(sep in lower for sep in [" to ", " from ", "->", "reach"]):
                cp_res = check_chokepoints(cp)
                summary = (
                    f"🚦 **Chokepoint Live Status: {cp_res['junction']}**\n\n"
                    f"- **Congestion Index:** {cp_res['congestion_index']}\n"
                    f"- **Typical Peak Delay:** {cp_res['base_delay_minutes']}\n"
                    f"- **Primary Cause:** {cp_res['reason']}\n"
                    f"- **Recommended Bypass:** {cp_res['best_workaround']}"
                )
                return {
                    "mode": "local-heuristic-engine",
                    "response": summary,
                    "tools_used": [{"tool": "check_chokepoints", "args": {"junction": cp}}],
                    "raw_tool_data": [cp_res],
                    "fallback_reason": error_note or "GEMINI_API_KEY not configured (offline mode)"
                }

        # Extract Origin and Destination
        origin = None
        destination = None

        # Look for "from <X> to <Y>" pattern
        from_to_match = re.search(r"from\s+([a-zA-Z\s_]+?)\s+to\s+([a-zA-Z\s_]+)", lower)
        if from_to_match:
            origin = from_to_match.group(1).strip()
            destination = from_to_match.group(2).strip()
        else:
            to_match = re.search(r"([a-zA-Z\s_]+?)\s+to\s+([a-zA-Z\s_]+)", lower)
            if to_match:
                origin = to_match.group(1).strip()
                destination = to_match.group(2).strip()

        # If not matched by regex, find detected hubs in string
        if not origin or not destination:
            from .knowledge import BENGALURU_HUBS
            detected = []
            for key in BENGALURU_HUBS.keys():
                normalized = _normalize_name(key)
                if key in lower or (normalized and normalized in lower):
                    detected.append(key)
            if len(detected) >= 2:
                origin, destination = detected[0], detected[1]

        # Default fallback route if user gave vague inquiry
        if not origin or not destination:
            origin = "koramangala"
            destination = "whitefield"

        # Check hour specification in prompt (e.g. "at 6pm", "at 18:00")
        time_match = re.search(r"at\s+(\d{1,2})(?::\d{2})?\s*(am|pm)?", lower)
        hour = target_hour
        if time_match:
            h = int(time_match.group(1))
            period = time_match.group(2)
            if period == "pm" and h < 12:
                h += 12
            elif period == "am" and h == 12:
                h = 0
            hour = h
        if hour is None:
            hour = 18 # default evening rush hour

        # Execute Tools
        traffic_data = get_route_traffic(origin, destination, hour=hour, is_raining=is_raining)
        metro_data = get_metro_alternative(origin, destination)
        departure_data = calculate_best_departure_window(origin, destination, target_hour=hour)

        # Synthesize local intelligent response
        cp_warnings = ""
        if traffic_data.get("chokepoints_on_route"):
            cps = [f"{cp['name']} (~{cp['delay_minutes']} min delay)" for cp in traffic_data["chokepoints_on_route"]]
            cp_warnings = f"⚠️ **Active Bottlenecks:** {', '.join(cps)}\n"

        metro_insight = ""
        if metro_data.get("status") == "success":
            saved_time = metro_data["comparison_with_road_cab"]["time_saved_mins"]
            saved_cost = metro_data["comparison_with_road_cab"]["money_saved_inr"]
            metro_insight = (
                f"\n🚇 **Multimodal Alternative (Namma Metro):**\n"
                f"- Board at: {metro_data['origin_boarding_station']}\n"
                f"- Deboard at: {metro_data['destination_deboarding_station']}\n"
                f"- Total Door-to-Door Time: ~{metro_data['breakdown']['total_multimodal_time_mins']} mins (vs {traffic_data['current_travel_time_mins']} mins road cab)\n"
                f"- Cost: ₹{metro_data['total_transit_cost_inr']} (Saves ₹{saved_cost} vs cab surge)\n"
                f"- **Verdict:** {metro_data['verdict']}\n"
            )

        summary = (
            f"🚗 **Bengaluru Commute Assessment: {traffic_data.get('origin', origin)} ➡️ {traffic_data.get('destination', destination)}**\n"
            f"- **Distance:** {traffic_data.get('distance_km', 'N/A')} km\n"
            f"- **Status:** {traffic_data.get('traffic_condition', 'Peak')}\n"
            f"- **Estimated Road Travel Time:** **{traffic_data.get('current_travel_time_mins', 'N/A')} minutes** (Off-peak: {traffic_data.get('off_peak_time_mins', 'N/A')} mins)\n"
            f"- **Congestion:** {traffic_data.get('congestion_category', 'Heavy')}\n"
            f"{cp_warnings}"
            f"- **Estimated Cab Fare:** ₹{traffic_data.get('cost_estimates', {}).get('cab_uber_ola_inr', '350')} (Surge: {traffic_data.get('cost_estimates', {}).get('surge_multiplier', '1.0x')})\n"
            f"{metro_insight}\n"
            f"⏱️ **Smart Departure Advice:**\n"
            f"Leaving at **{departure_data.get('golden_departure_window', 'different time')}** can save you up to **{departure_data.get('time_saved_by_timing', 'significant time')}**!"
        )

        return {
            "mode": "local-heuristic-engine",
            "response": summary,
            "tools_used": [
                {"tool": "get_route_traffic", "args": {"origin": origin, "destination": destination, "hour": hour}},
                {"tool": "get_metro_alternative", "args": {"origin": origin, "destination": destination}},
                {"tool": "calculate_best_departure_window", "args": {"origin": origin, "destination": destination, "target_hour": hour}}
            ],
            "raw_tool_data": [traffic_data, metro_data, departure_data],
            "fallback_reason": error_note or "Running in reproducible local mode (no GEMINI_API_KEY required)"
        }
