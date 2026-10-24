"""
Evidence-grounded food composition database.
Sourced from ICMR-NIN Indian Food Composition Tables (IFCT 2017) and verified standard databases.
Provides exact nutrient values per 100g, default consumer portion sizes, realistic costs, and allergen tags.
"""

from typing import Dict, List, Optional
from nutriloop.models import FoodItem, Macronutrients, DietType


# Standardized food records
FOOD_CATALOG: Dict[str, FoodItem] = {
    # --- GRAINS, BREADS & BREAKFASTS ---
    "roti_whole_wheat": FoodItem(
        id="roti_whole_wheat",
        name="Whole Wheat Roti / Chapati",
        hindi_name="गेहूं की रोटी",
        category="grains",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=297.0, protein_g=10.5, carbs_g=57.0, fat_g=3.2, fiber_g=11.0),
        default_portion_g=60.0,
        portion_description="2 medium rotis (60g)",
        estimated_cost_inr=10.0,
        prep_time_minutes=15,
        allergens=["gluten"],
        glycemic_index="medium",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: C026)"
    ),
    "brown_rice_cooked": FoodItem(
        id="brown_rice_cooked",
        name="Brown Rice (Cooked)",
        hindi_name="भूरा चावल",
        category="grains",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=123.0, protein_g=2.7, carbs_g=25.6, fat_g=1.0, fiber_g=1.8),
        default_portion_g=150.0,
        portion_description="1 medium katori / cup (150g)",
        estimated_cost_inr=18.0,
        prep_time_minutes=25,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: C002)"
    ),
    "white_rice_cooked": FoodItem(
        id="white_rice_cooked",
        name="White Rice (Cooked)",
        hindi_name="सफेद चावल",
        category="grains",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=130.0, protein_g=2.4, carbs_g=28.2, fat_g=0.3, fiber_g=0.4),
        default_portion_g=150.0,
        portion_description="1 medium katori / cup (150g)",
        estimated_cost_inr=12.0,
        prep_time_minutes=20,
        allergens=[],
        glycemic_index="high",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: C001)"
    ),
    "oats_porridge": FoodItem(
        id="oats_porridge",
        name="Oats Porridge (with water & pinch salt)",
        hindi_name="दलिया / ओट्स",
        category="grains",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=71.0, protein_g=2.5, carbs_g=12.0, fat_g=1.5, fiber_g=1.7),
        default_portion_g=200.0,
        portion_description="1 bowl (200g cooked)",
        estimated_cost_inr=20.0,
        prep_time_minutes=10,
        allergens=["gluten"],
        glycemic_index="low",
        is_jain_friendly=True,
        source="USDA FoodData Central / Standard Porridge"
    ),
    "poha_vegetable": FoodItem(
        id="poha_vegetable",
        name="Vegetable Poha (Flattened Rice)",
        hindi_name="सब्ज़ी पोहा",
        category="breakfast",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=130.0, protein_g=2.6, carbs_g=23.0, fat_g=3.2, fiber_g=2.1),
        default_portion_g=180.0,
        portion_description="1 standard plate (180g)",
        estimated_cost_inr=25.0,
        prep_time_minutes=15,
        allergens=["peanuts"],
        glycemic_index="medium",
        is_jain_friendly=False,
        source="ICMR-NIN Standard Prepared Dishes"
    ),
    "idli_steamed": FoodItem(
        id="idli_steamed",
        name="Steamed Idli (Rice & Urad Dal)",
        hindi_name="इडली",
        category="breakfast",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=132.0, protein_g=3.8, carbs_g=27.5, fat_g=0.6, fiber_g=1.4),
        default_portion_g=120.0,
        portion_description="2 idlis (120g)",
        estimated_cost_inr=20.0,
        prep_time_minutes=15,
        allergens=[],
        glycemic_index="medium",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    ),
    "besan_chilla": FoodItem(
        id="besan_chilla",
        name="Besan Chilla (Gram Flour Pancake)",
        hindi_name="बेसन चीला",
        category="breakfast",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=195.0, protein_g=10.2, carbs_g=24.0, fat_g=6.5, fiber_g=5.2),
        default_portion_g=120.0,
        portion_description="2 chillas (120g)",
        estimated_cost_inr=25.0,
        prep_time_minutes=15,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    ),

    # --- LENTILS & PULSES (DALS) ---
    "dal_moong_tadka": FoodItem(
        id="dal_moong_tadka",
        name="Yellow Moong Dal (Tadka)",
        hindi_name="मूंग दाल तड़का",
        category="lentils",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=105.0, protein_g=6.8, carbs_g=14.5, fat_g=2.4, fiber_g=3.8),
        default_portion_g=150.0,
        portion_description="1 medium katori (150g)",
        estimated_cost_inr=25.0,
        prep_time_minutes=20,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN IFCT 2017 (Key: D012)"
    ),
    "dal_toor": FoodItem(
        id="dal_toor",
        name="Toor / Arhar Dal (Cooked)",
        hindi_name="अरहर दाल",
        category="lentils",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=112.0, protein_g=7.2, carbs_g=16.0, fat_g=2.1, fiber_g=4.1),
        default_portion_g=150.0,
        portion_description="1 medium katori (150g)",
        estimated_cost_inr=28.0,
        prep_time_minutes=25,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: D005)"
    ),
    "chana_masala": FoodItem(
        id="chana_masala",
        name="Chana Masala (Chickpeas Curry)",
        hindi_name="चना मसाला",
        category="lentils",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=138.0, protein_g=7.5, carbs_g=18.5, fat_g=3.8, fiber_g=5.5),
        default_portion_g=160.0,
        portion_description="1 katori (160g)",
        estimated_cost_inr=32.0,
        prep_time_minutes=30,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN IFCT 2017 (Key: D001)"
    ),
    "rajma_masala": FoodItem(
        id="rajma_masala",
        name="Rajma Curry (Kidney Beans)",
        hindi_name="राजमा करी",
        category="lentils",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=127.0, protein_g=6.9, carbs_g=18.0, fat_g=3.2, fiber_g=5.1),
        default_portion_g=160.0,
        portion_description="1 katori (160g)",
        estimated_cost_inr=35.0,
        prep_time_minutes=35,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN IFCT 2017 (Key: D016)"
    ),
    "boiled_sprouts_salad": FoodItem(
        id="boiled_sprouts_salad",
        name="Boiled Moong Sprouts Salad",
        hindi_name="अंकुरित मूंग सलाद",
        category="proteins",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=62.0, protein_g=5.8, carbs_g=9.2, fat_g=0.6, fiber_g=3.5),
        default_portion_g=120.0,
        portion_description="1 small bowl (120g)",
        estimated_cost_inr=18.0,
        prep_time_minutes=10,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: D013)"
    ),

    # --- VEGETABLES & SABZIS ---
    "palak_paneer": FoodItem(
        id="palak_paneer",
        name="Palak Paneer (Spinach Cottage Cheese)",
        hindi_name="पालक पनीर",
        category="vegetables",
        diet_type=DietType.VEGETARIAN,
        per_100g=Macronutrients(calories=142.0, protein_g=7.8, carbs_g=5.2, fat_g=10.5, fiber_g=2.8),
        default_portion_g=150.0,
        portion_description="1 medium katori (150g)",
        estimated_cost_inr=55.0,
        prep_time_minutes=25,
        allergens=["dairy"],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN Standard Dishes"
    ),
    "paneer_bhurji": FoodItem(
        id="paneer_bhurji",
        name="Paneer Bhurji (Scrambled Cottage Cheese)",
        hindi_name="पनीर भुर्जी",
        category="proteins",
        diet_type=DietType.VEGETARIAN,
        per_100g=Macronutrients(calories=195.0, protein_g=13.5, carbs_g=4.2, fat_g=14.0, fiber_g=1.2),
        default_portion_g=120.0,
        portion_description="1 bowl (120g)",
        estimated_cost_inr=50.0,
        prep_time_minutes=15,
        allergens=["dairy"],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN IFCT 2017 / Dairy Records"
    ),
    "bhindi_masala": FoodItem(
        id="bhindi_masala",
        name="Bhindi Masala (Stir-fried Okra)",
        hindi_name="भिंडी मसाला",
        category="vegetables",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=78.0, protein_g=2.1, carbs_g=7.5, fat_g=4.5, fiber_g=3.2),
        default_portion_g=120.0,
        portion_description="1 katori (120g)",
        estimated_cost_inr=25.0,
        prep_time_minutes=20,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    ),
    "mixed_veg_curry": FoodItem(
        id="mixed_veg_curry",
        name="Mixed Vegetable Sabzi (Carrot, Beans, Peas)",
        hindi_name="मिक्स वेज सब्जी",
        category="vegetables",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=72.0, protein_g=2.4, carbs_g=9.0, fat_g=3.0, fiber_g=3.4),
        default_portion_g=140.0,
        portion_description="1 katori (140g)",
        estimated_cost_inr=24.0,
        prep_time_minutes=20,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN IFCT 2017"
    ),
    "cucumber_tomato_salad": FoodItem(
        id="cucumber_tomato_salad",
        name="Cucumber & Tomato Kachumber Salad",
        hindi_name="ककड़ी टमाटर सलाद",
        category="vegetables",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=22.0, protein_g=0.9, carbs_g=4.1, fat_g=0.2, fiber_g=1.5),
        default_portion_g=100.0,
        portion_description="1 katori (100g)",
        estimated_cost_inr=12.0,
        prep_time_minutes=5,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    ),

    # --- PROTEINS, DAIRY & EGGS ---
    "curd_plain": FoodItem(
        id="curd_plain",
        name="Plain Curd / Dahi",
        hindi_name="सादा दही",
        category="dairy",
        diet_type=DietType.VEGETARIAN,
        per_100g=Macronutrients(calories=60.0, protein_g=3.5, carbs_g=4.7, fat_g=3.1, fiber_g=0.0),
        default_portion_g=150.0,
        portion_description="1 katori (150g)",
        estimated_cost_inr=20.0,
        prep_time_minutes=0,
        allergens=["dairy"],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    ),
    "chaas_buttermilk": FoodItem(
        id="chaas_buttermilk",
        name="Spiced Buttermilk / Chaas",
        hindi_name="मसाला छाछ",
        category="dairy",
        diet_type=DietType.VEGETARIAN,
        per_100g=Macronutrients(calories=28.0, protein_g=1.8, carbs_g=2.6, fat_g=1.1, fiber_g=0.0),
        default_portion_g=200.0,
        portion_description="1 tall glass (200ml)",
        estimated_cost_inr=15.0,
        prep_time_minutes=5,
        allergens=["dairy"],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    ),
    "soya_chunks_curry": FoodItem(
        id="soya_chunks_curry",
        name="Soya Chunks Curry (Meal Maker)",
        hindi_name="सोयाबीन करी",
        category="proteins",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=118.0, protein_g=14.8, carbs_g=8.2, fat_g=2.5, fiber_g=5.2),
        default_portion_g=150.0,
        portion_description="1 medium katori (150g cooked)",
        estimated_cost_inr=22.0,
        prep_time_minutes=20,
        allergens=["soy"],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN Soya Composition / IFCT"
    ),
    "boiled_eggs": FoodItem(
        id="boiled_eggs",
        name="Hard Boiled Eggs",
        hindi_name="उबले अंडे",
        category="proteins",
        diet_type=DietType.EGGETARIAN,
        per_100g=Macronutrients(calories=155.0, protein_g=12.6, carbs_g=1.1, fat_g=10.6, fiber_g=0.0),
        default_portion_g=100.0,
        portion_description="2 whole eggs (100g)",
        estimated_cost_inr=16.0,
        prep_time_minutes=12,
        allergens=["eggs"],
        glycemic_index="low",
        is_jain_friendly=False,
        source="USDA / ICMR-NIN IFCT 2017"
    ),
    "egg_bhurji": FoodItem(
        id="egg_bhurji",
        name="Egg Bhurji (Indian Scrambled Eggs)",
        hindi_name="अंडा भुर्जी",
        category="proteins",
        diet_type=DietType.EGGETARIAN,
        per_100g=Macronutrients(calories=168.0, protein_g=11.8, carbs_g=3.2, fat_g=12.0, fiber_g=0.5),
        default_portion_g=120.0,
        portion_description="2 eggs scrambled with onion-tomato (120g)",
        estimated_cost_inr=25.0,
        prep_time_minutes=10,
        allergens=["eggs"],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN IFCT 2017"
    ),
    "grilled_chicken_breast": FoodItem(
        id="grilled_chicken_breast",
        name="Grilled Chicken Breast (Skinless)",
        hindi_name="ग्रिल्ड चिकन",
        category="proteins",
        diet_type=DietType.NON_VEGETARIAN,
        per_100g=Macronutrients(calories=165.0, protein_g=31.0, carbs_g=0.0, fat_g=3.6, fiber_g=0.0),
        default_portion_g=120.0,
        portion_description="1 portion breast piece (120g)",
        estimated_cost_inr=65.0,
        prep_time_minutes=20,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=False,
        source="ICMR-NIN IFCT 2017"
    ),
    "tofu_stir_fry": FoodItem(
        id="tofu_stir_fry",
        name="Tofu & Veggie Stir Fry",
        hindi_name="टोफू सब्जी",
        category="proteins",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=98.0, protein_g=9.2, carbs_g=3.4, fat_g=5.2, fiber_g=1.8),
        default_portion_g=140.0,
        portion_description="1 bowl (140g)",
        estimated_cost_inr=45.0,
        prep_time_minutes=15,
        allergens=["soy"],
        glycemic_index="low",
        is_jain_friendly=True,
        source="USDA / Standard Composition"
    ),

    # --- COMMON REAL-LIFE DISRUPTIONS & CANTEEN/STREET FOODS ---
    "samosa_fried": FoodItem(
        id="samosa_fried",
        name="Fried Vegetable Samosa",
        hindi_name="समोसा",
        category="snacks",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=308.0, protein_g=4.5, carbs_g=32.2, fat_g=17.5, fiber_g=2.4),
        default_portion_g=90.0,
        portion_description="1 medium samosa (90g)",
        estimated_cost_inr=20.0,
        prep_time_minutes=0,
        allergens=["gluten"],
        glycemic_index="high",
        is_jain_friendly=False,
        source="ICMR-NIN Street Food Analysis"
    ),
    "masala_chai": FoodItem(
        id="masala_chai",
        name="Masala Chai (with milk & 1 tsp sugar)",
        hindi_name="मसाला चाय",
        category="beverage",
        diet_type=DietType.VEGETARIAN,
        per_100g=Macronutrients(calories=65.0, protein_g=1.8, carbs_g=9.2, fat_g=2.2, fiber_g=0.1),
        default_portion_g=120.0,
        portion_description="1 small cutting cup (120ml)",
        estimated_cost_inr=15.0,
        prep_time_minutes=8,
        allergens=["dairy"],
        glycemic_index="high",
        is_jain_friendly=True,
        source="ICMR-NIN Beverage Records"
    ),
    "veg_biryani_restaurant": FoodItem(
        id="veg_biryani_restaurant",
        name="Vegetable Dum Biryani (Restaurant Style)",
        hindi_name="वेज बिरयानी",
        category="meals",
        diet_type=DietType.VEGETARIAN,
        per_100g=Macronutrients(calories=185.0, protein_g=4.2, carbs_g=26.5, fat_g=7.2, fiber_g=2.8),
        default_portion_g=300.0,
        portion_description="1 plate / box (300g)",
        estimated_cost_inr=150.0,
        prep_time_minutes=0,
        allergens=["dairy"],
        glycemic_index="medium",
        is_jain_friendly=False,
        source="ICMR-NIN Standard Prepared Dishes"
    ),
    "roasted_makhana": FoodItem(
        id="roasted_makhana",
        name="Roasted Makhana (Fox Nuts with pinch ghee)",
        hindi_name="भुना मखाना",
        category="snacks",
        diet_type=DietType.VEGETARIAN,
        per_100g=Macronutrients(calories=390.0, protein_g=9.8, carbs_g=72.0, fat_g=7.0, fiber_g=7.6),
        default_portion_g=30.0,
        portion_description="1 bowl / handful (30g)",
        estimated_cost_inr=30.0,
        prep_time_minutes=5,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    ),
    "roasted_chana": FoodItem(
        id="roasted_chana",
        name="Roasted Bengal Gram (Bhuna Chana)",
        hindi_name="भुना चना",
        category="snacks",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=369.0, protein_g=18.6, carbs_g=58.1, fat_g=5.2, fiber_g=15.3),
        default_portion_g=40.0,
        portion_description="1 handful cup (40g)",
        estimated_cost_inr=15.0,
        prep_time_minutes=0,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: D002)"
    ),
    "apple_fresh": FoodItem(
        id="apple_fresh",
        name="Fresh Apple",
        hindi_name="सेब",
        category="fruits",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=52.0, protein_g=0.3, carbs_g=13.8, fat_g=0.2, fiber_g=2.4),
        default_portion_g=130.0,
        portion_description="1 medium apple (130g)",
        estimated_cost_inr=25.0,
        prep_time_minutes=0,
        allergens=[],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: F002)"
    ),
    "papaya_ripe": FoodItem(
        id="papaya_ripe",
        name="Fresh Ripe Papaya (Diced)",
        hindi_name="पपीता",
        category="fruits",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=43.0, protein_g=0.5, carbs_g=10.8, fat_g=0.1, fiber_g=1.7),
        default_portion_g=150.0,
        portion_description="1 bowl diced (150g)",
        estimated_cost_inr=20.0,
        prep_time_minutes=5,
        allergens=[],
        glycemic_index="medium",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017 (Key: F025)"
    ),
    "almonds_raw": FoodItem(
        id="almonds_raw",
        name="Raw Almonds (Badam)",
        hindi_name="बादाम",
        category="nuts",
        diet_type=DietType.VEGAN,
        per_100g=Macronutrients(calories=579.0, protein_g=21.2, carbs_g=21.6, fat_g=49.9, fiber_g=12.5),
        default_portion_g=20.0,
        portion_description="10-12 almonds (20g)",
        estimated_cost_inr=22.0,
        prep_time_minutes=0,
        allergens=["nuts"],
        glycemic_index="low",
        is_jain_friendly=True,
        source="ICMR-NIN IFCT 2017"
    )
}


def get_food(food_id: str) -> Optional[FoodItem]:
    """Retrieve food item by its unique identifier."""
    return FOOD_CATALOG.get(food_id)


def list_foods_by_diet(diet_type: DietType) -> List[FoodItem]:
    """Filter database items compatible with the user's diet."""
    compatible = []
    for food in FOOD_CATALOG.values():
        if diet_type == DietType.VEGAN and food.diet_type == DietType.VEGAN:
            compatible.append(food)
        elif diet_type == DietType.JAIN and food.is_jain_friendly and food.diet_type in (DietType.VEGAN, DietType.VEGETARIAN):
            compatible.append(food)
        elif diet_type == DietType.VEGETARIAN and food.diet_type in (DietType.VEGAN, DietType.VEGETARIAN):
            compatible.append(food)
        elif diet_type == DietType.EGGETARIAN and food.diet_type in (DietType.VEGAN, DietType.VEGETARIAN, DietType.EGGETARIAN):
            compatible.append(food)
        elif diet_type == DietType.NON_VEGETARIAN:
            compatible.append(food)
    return compatible


def search_foods(query: str) -> List[FoodItem]:
    """Fuzzy substring search across English and Hindi names."""
    q = query.lower().strip()
    results = []
    for food in FOOD_CATALOG.values():
        if q in food.name.lower() or (food.hindi_name and q in food.hindi_name) or q in food.id:
            results.append(food)
    return results
