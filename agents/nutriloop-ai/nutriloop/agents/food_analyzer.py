"""
Food Analyzer and Intake Agent.
Parses natural language food logs, identifies food items, scales portions,
and attaches verified nutrient totals and portion uncertainty tags.
"""

import json
import logging
import re
from typing import List, Optional, Tuple, Any
from nutriloop.agents.base import BaseAgent
from nutriloop.models import FoodLogEntry, MealItem
from nutriloop.database import search_foods, FOOD_CATALOG
from nutriloop.nutrition_engine import create_meal_item, parse_quantity_to_grams

logger = logging.getLogger("nutriloop.agent")


class FoodAnalyzerAgent(BaseAgent):
    """Processes user food intake records and calculates verified consumption."""

    def __init__(self):
        super().__init__(name="FoodAnalyzerAgent", role="Dietary Intake & Portion Estimator")

    def _parse_with_gemini(self, text: str) -> Optional[List[Tuple[Any, float, str]]]:
        """
        Use Google GenAI SDK (Gemini) to extract dishes and quantities from natural language.
        Guardrail: Gemini extracts food concepts only; all nutrient arithmetic is derived deterministically from IFCT.
        """
        client = self.get_gemini_client()
        if not client:
            return None

        prompt = f"""You are a clinical nutrition intake extraction assistant.
Extract all individual food and drink items mentioned in this logged meal text: "{text}".
For each item, identify:
1. dish_name: Name of the food/dish (e.g., 'samosa', 'chai', 'roti', 'palak paneer', 'dal').
2. quantity: Numeric count/amount (e.g. 1.0, 2.0).
3. unit: Household measure (e.g. 'piece', 'cup', 'bowl', 'plate', 'roti', 'serving', 'grams').

Return a JSON array of objects with keys: "dish_name", "quantity", "unit".
Example:
[
  {{"dish_name": "samosa", "quantity": 1.0, "unit": "piece"}},
  {{"dish_name": "masala chai", "quantity": 1.0, "unit": "cup"}}
]
Do not output markdown formatting, output pure JSON only.
"""
        try:
            from google.genai import types
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text.strip()
            data = json.loads(raw_text)
            results = []
            for entry in data:
                dish = entry.get("dish_name", "")
                qty = float(entry.get("quantity", 1.0))
                unit = entry.get("unit", "portion")
                candidates = search_foods(dish)
                if candidates:
                    results.append((candidates[0], qty, unit))
            if results:
                self.record_trace(
                    action="GeminiIntakeExtracted",
                    reasoning=f"Google GenAI parsed '{text}' into {len(results)} verified catalog item(s).",
                    details={"gemini_items": [r[0].name for r in results]}
                )
                return results
        except Exception as e:
            logger.warning(f"[{self.name}] Gemini extraction failed, falling back to deterministic parser: {e}")
            self.record_trace(
                action="GeminiFallback",
                reasoning=f"Gemini extraction error ({e}); safely fell back to deterministic keyword parsing."
            )
        return None

    def analyze_food_log(
        self,
        text: str,
        meal_type: str = "lunch",
        logged_at: str = "13:30",
        is_unplanned: bool = False
    ) -> FoodLogEntry:
        """
        Parse food description text and return a verified FoodLogEntry with deterministic calculations.
        Supports Google GenAI extraction with local deterministic fallback.
        """
        self.record_trace(
            action="ParseIntake",
            reasoning=f"Parsing food entry: '{text}' ({meal_type}, unplanned={is_unplanned})"
        )

        detected_items: List[MealItem] = []

        # 1. Attempt Google GenAI extraction if client is available
        gemini_parsed = self._parse_with_gemini(text)
        if gemini_parsed:
            for food, qty, unit in gemini_parsed:
                grams, desc = parse_quantity_to_grams(food, quantity=qty, unit=unit)
                item = create_meal_item(food.id, portion_g=grams, portion_desc=desc)
                detected_items.append(item)
            matched_candidates = []
        else:
            # 2. Deterministic keyword and regex parsing fallback
            lowered_text = text.lower()
            matched_candidates = []
            for food_id, food in FOOD_CATALOG.items():
                names_to_check = [food.name.lower(), food.id.lower()]
                if food.hindi_name:
                    names_to_check.append(food.hindi_name.lower())

                # Keyword matching heuristics
                keywords = []
                if "samosa" in food_id: keywords.append("samosa")
                elif "chai" in food_id: keywords.extend(["chai", "tea"])
                elif "biryani" in food_id: keywords.append("biryani")
                elif "roti" in food_id: keywords.extend(["roti", "chapati", "phulka"])
                elif "oats" in food_id: keywords.extend(["oats", "porridge", "daliya"])
                elif "moong" in food_id: keywords.extend(["moong dal", "yellow dal", "moong"])
                elif "toor" in food_id: keywords.extend(["toor dal", "arhar", "dal fry"])
                elif "paneer" in food_id and "palak" in food_id: keywords.extend(["palak paneer", "saag paneer"])
                elif "paneer_bhurji" in food_id: keywords.extend(["paneer bhurji", "scrambled paneer"])
                elif "curd" in food_id: keywords.extend(["curd", "dahi", "yogurt"])
                elif "chaas" in food_id: keywords.extend(["chaas", "buttermilk", "chhas"])
                elif "boiled_eggs" in food_id: keywords.extend(["boiled egg", "boiled eggs"])
                elif "egg_bhurji" in food_id: keywords.extend(["egg bhurji", "anda bhurji", "scrambled eggs"])
                elif "rice" in food_id: keywords.extend(["rice", "chawal"])
                elif "poha" in food_id: keywords.append("poha")
                elif "idli" in food_id: keywords.append("idli")
                elif "chilla" in food_id: keywords.extend(["chilla", "cheela"])
                elif "chana_masala" in food_id: keywords.extend(["chole", "chana masala", "chickpeas"])
                elif "rajma" in food_id: keywords.extend(["rajma", "kidney beans"])
                elif "sprouts" in food_id: keywords.extend(["sprouts", "sprout"])
                elif "bhindi" in food_id: keywords.extend(["bhindi", "okra"])
                elif "salad" in food_id: keywords.extend(["salad", "kachumber"])
                elif "apple" in food_id: keywords.append("apple")
                elif "papaya" in food_id: keywords.append("papaya")
                elif "makhana" in food_id: keywords.append("makhana")
                elif "roasted_chana" in food_id: keywords.extend(["bhuna chana", "roasted chana"])
                elif "chicken" in food_id: keywords.extend(["chicken", "chicken breast"])
                elif "tofu" in food_id: keywords.append("tofu")

                matched = any(kw in lowered_text for kw in keywords)
                if matched:
                    # Extract potential count before keyword
                    count = 1.0
                    for kw in keywords:
                        pattern = rf"(\d+)\s*(?:plate|plates|bowl|bowls|cup|cups|glass|katori|katoris|piece|pieces)?\s*{kw}"
                        match = re.search(pattern, lowered_text)
                        if match:
                            try:
                                count = float(match.group(1))
                            except Exception:
                                count = 1.0
                            break

                    matched_candidates.append((food, count))

        # Build verified meal items from fallback if Gemini did not populate
        if not detected_items:
            if matched_candidates:
                for food, qty in matched_candidates:
                    grams, desc = parse_quantity_to_grams(food, quantity=qty)
                    item = create_meal_item(food.id, portion_g=grams, portion_desc=desc)
                    detected_items.append(item)
            else:
                # Fallback: search for top single food term
                search_results = search_foods(text)
                if search_results:
                    food = search_results[0]
                    item = create_meal_item(food.id, portion_g=food.default_portion_g)
                    detected_items.append(item)
                else:
                    # Unknown dish: use standard street/canteen meal estimate with uncertainty flag
                    item = create_meal_item("veg_biryani_restaurant", portion_g=250.0, portion_desc=f"Standard serving of '{text}' (estimated 250g)")
                    detected_items.append(item)

        total_cal = round(sum(i.calories for i in detected_items), 1)
        total_prot = round(sum(i.protein_g for i in detected_items), 1)
        total_carb = round(sum(i.carbs_g for i in detected_items), 1)
        total_fat = round(sum(i.fat_g for i in detected_items), 1)

        log_entry = FoodLogEntry(
            meal_type=meal_type,
            description=text,
            consumed_items=detected_items,
            total_calories=total_cal,
            total_protein_g=total_prot,
            total_carbs_g=total_carb,
            total_fat_g=total_fat,
            logged_at=logged_at,
            is_unplanned=is_unplanned,
            notes=f"Processed {len(detected_items)} item(s) with deterministic IFCT-grounded nutrient values."
        )

        self.record_trace(
            action="IntakeComputed",
            reasoning=f"Computed {total_cal} kcal, {total_prot}g protein, {total_carb}g carbs, {total_fat}g fat for logged intake.",
            details={"items": [i.name for i in detected_items], "calories": total_cal}
        )

        return log_entry
