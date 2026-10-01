"""Default shelf life for fridge ingredients after purchase."""

from __future__ import annotations

from app.schemas.models import AppState, FridgeItem

# Days after purchase the ingredient stays usable (including purchase day
# through purchase_date + days). None = pantry / freezer, no buy-ahead cap.
_EXACT: dict[str, int | None] = {
    # Highly perishable produce
    "avocado": 3,
    "banana": 4,
    "basil": 4,
    "broccoli": 5,
    "cabbage": 10,
    "carrot": 14,
    "celery": 10,
    "cherry tomatoes": 5,
    "cilantro": 4,
    "corn": 4,
    "cucumber": 5,
    "edamame": 5,
    "frozen banana": None,
    "frozen berries": None,
    "garlic": 21,
    "ginger": 14,
    "kale": 5,
    "onion": 21,
    "potato": 21,
    "snap peas": 4,
    "spinach": 4,
    "sweet potato": 14,
    "zucchini": 5,
    "bell pepper": 7,
    "apple": 14,
    # Fresh / refrigerated
    "firm tofu": 7,
    "hummus": 7,
    "oat milk": 7,
    "coconut milk": 5,
    "salsa": 7,
    "wholegrain bread": 5,
    "wholewheat tortilla": 7,
    "cooked quinoa": 4,
    "cooked rice": 4,
    "vegetable broth": 5,
    "tomato passata": 5,
    "lemon juice": 14,
    "lime juice": 14,
    # Pantry / dry
    "black beans": None,
    "brown lentils": None,
    "chia seeds": None,
    "chickpeas": None,
    "chili flakes": None,
    "cinnamon": None,
    "cumin": None,
    "curry powder": None,
    "flaxseed": None,
    "granola": None,
    "hemp seeds": None,
    "maple syrup": None,
    "miso paste": None,
    "nutritional yeast": None,
    "olive oil": None,
    "oregano": None,
    "peanut butter": None,
    "red lentils": None,
    "rice noodles": None,
    "rice vinegar": None,
    "rolled oats": None,
    "rosemary": None,
    "sesame oil": None,
    "sesame seeds": None,
    "soba noodles": None,
    "soy sauce": None,
    "tahini": None,
    "walnut": None,
    "white beans": None,
    "wholewheat pasta": None,
}


def default_shelf_life_days(name: str) -> int | None:
    """Return usable days after purchase; None means non-perishable."""
    key = name.strip().lower()
    if key in _EXACT:
        return _EXACT[key]
    perishable_bits = (
        "lettuce",
        "salad",
        "berry",
        "berries",
        "tomato",
        "pepper",
        "milk",
        "yogurt",
        "tofu",
        "bread",
        "herb",
        "fresh",
    )
    if any(bit in key for bit in perishable_bits):
        return 5
    pantry_bits = (
        "oil",
        "vinegar",
        "spice",
        "seed",
        "flour",
        "pasta",
        "rice",
        "bean",
        "lentil",
        "sauce",
        "powder",
        "frozen",
    )
    if any(bit in key for bit in pantry_bits):
        return None
    return 7


def ensure_fridge_shelf_lives(state: AppState) -> AppState:
    """Backfill shelf_life_days when missing from persisted fridge rows."""
    updated: list[FridgeItem] = []
    changed = False
    for item in state.fridge:
        if "shelf_life_days" in item.model_fields_set:
            updated.append(item)
            continue
        life = default_shelf_life_days(item.name)
        updated.append(item.model_copy(update={"shelf_life_days": life}))
        changed = True
    if not changed:
        return state
    return state.model_copy(update={"fridge": updated})
