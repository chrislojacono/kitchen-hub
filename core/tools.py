import json
import os
import re
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Literal, NotRequired, TypedDict

from core import db, recipes

Slot = Literal["breakfast", "lunch", "dinner", "snack"]


class PantryItemIn(TypedDict):
    name: str
    qty: NotRequired[float]
    unit: NotRequired[str]
    category: NotRequired[str]
    expires_on: NotRequired[str]


class GroceryItemIn(TypedDict):
    name: str
    qty: NotRequired[float]
    unit: NotRequired[str]


MAX_NAME_LENGTH = 80
MAX_TITLE_LENGTH = 120
MAX_RECIPE_BYTES = 100_000
STAPLES = ["Milk", "Eggs", "Bread", "Butter", "Bananas", "Apples", "Onions", "Garlic",
           "Chicken", "Rice", "Pasta", "Cheese", "Yogurt", "Coffee", "Tomatoes", "Spinach"]

SLOT_ORDER = "CASE slot WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 WHEN 'snack' THEN 2 ELSE 3 END"


@contextmanager
def _tx():
    conn = db.connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


def _text(value, limit=MAX_NAME_LENGTH):
    text = " ".join(str(value).split())
    if not text or len(text) > limit:
        raise ValueError(f"Names must be 1 to {limit} characters")
    return text


def _iso(value):
    return date.fromisoformat(value).isoformat() if value else None


def get_pantry() -> list[dict]:
    """List everything in the pantry, soonest-expiring first."""
    with _tx() as conn:
        return _rows(conn.execute(
            "SELECT * FROM pantry_items ORDER BY expires_on IS NULL, expires_on, name COLLATE NOCASE"))


def add_pantry_items(items: list[PantryItemIn], source: Literal["manual", "receipt", "agent"] = "manual") -> list[int]:
    """Add items to the pantry. Each item is a dict with name (required), qty, unit, category,
    and expires_on (YYYY-MM-DD). Returns the new item ids."""
    ids = []
    with _tx() as conn:
        for item in items:
            cur = conn.execute(
                "INSERT INTO pantry_items (name, qty, unit, category, expires_on, source) VALUES (?, ?, ?, ?, ?, ?)",
                (_text(item["name"]), 1 if item.get("qty") is None else item["qty"], item.get("unit"),
                 item.get("category"), _iso(item.get("expires_on")), source))
            ids.append(cur.lastrowid)
    return ids


def use_pantry_item(item_id: int, qty: float | None = None) -> dict:
    """Use up a pantry item. Pass qty to use part of it; omit qty to remove it entirely.
    Returns the remaining quantity (0 means the item was removed)."""
    if qty is not None and qty <= 0:
        raise ValueError("qty must be greater than 0")
    with _tx() as conn:
        row = conn.execute("SELECT qty FROM pantry_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise ValueError(f"No pantry item with id {item_id}")
        remaining = 0 if qty is None else row["qty"] - qty
        if remaining <= 0:
            conn.execute("DELETE FROM pantry_items WHERE id = ?", (item_id,))
            return {"id": item_id, "remaining": 0}
        conn.execute("UPDATE pantry_items SET qty = ? WHERE id = ?", (remaining, item_id))
        return {"id": item_id, "remaining": remaining}


def get_expiring(days: int = 3) -> list[dict]:
    """List pantry items that expire within the given number of days, including ones already expired."""
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    with _tx() as conn:
        return _rows(conn.execute(
            "SELECT * FROM pantry_items WHERE expires_on IS NOT NULL AND expires_on <= ? ORDER BY expires_on, name COLLATE NOCASE",
            (cutoff,)))


def get_cooks() -> list[str]:
    """The people a meal can be assigned to cook."""
    return [name.strip() for name in os.environ.get("KITCHEN_COOKS", "").split(",") if name.strip()]


def _meal(row):
    meal = dict(row)
    raw = meal.pop("recipe_json")
    meal["recipe"] = json.loads(raw) if raw else None
    meal["takeout"] = bool(meal["takeout"])
    return meal


def get_meal_plan(start: str | None = None, days: int = 7) -> list[dict]:
    """List planned meals for a range of days starting at start (YYYY-MM-DD, default today)."""
    first = date.fromisoformat(start) if start else date.today()
    last = first + timedelta(days=days - 1)
    with _tx() as conn:
        return [_meal(row) for row in conn.execute(
            f"SELECT * FROM meals WHERE date BETWEEN ? AND ? ORDER BY date, {SLOT_ORDER}",
            (first.isoformat(), last.isoformat()))]


def set_meal(day: str, slot: Slot, title: str, recipe: dict | None = None, cook: str | None = None,
             takeout: bool = False) -> dict:
    """Plan a meal, replacing whatever was in that slot. day is YYYY-MM-DD; slot is breakfast, lunch, dinner or
    snack (this household plans dinner only). cook is one of get_cooks() or null. takeout marks a take-out night.
    recipe is optional, e.g. {"title": ..., "source": url, "lines": ["2 cups rice", ...], "steps": [...]}."""
    cooks = get_cooks()
    if cook is not None and cook not in cooks:
        raise ValueError(f"cook must be one of: {', '.join(cooks) or 'nobody yet (set KITCHEN_COOKS)'}")
    recipe_json = json.dumps(recipe) if recipe else None
    if recipe_json and len(recipe_json) > MAX_RECIPE_BYTES:
        raise ValueError("That recipe is too large")
    with _tx() as conn:
        conn.execute(
            "INSERT INTO meals (date, slot, title, recipe_json, cook, takeout) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (date, slot) DO UPDATE SET title = excluded.title, recipe_json = excluded.recipe_json, "
            "cook = excluded.cook, takeout = excluded.takeout",
            (_iso(day), slot, _text(title, MAX_TITLE_LENGTH), recipe_json, cook, int(takeout)))
        return _meal(conn.execute("SELECT * FROM meals WHERE date = ? AND slot = ?", (_iso(day), slot)).fetchone())


def move_meal(day: str, to_day: str, slot: Slot = "dinner") -> list[dict]:
    """Move a planned meal to another day. If that day already has a meal in the slot, the two swap.
    Returns the meals on both days afterwards."""
    source, target = _iso(day), _iso(to_day)
    with _tx() as conn:
        if conn.execute("SELECT 1 FROM meals WHERE date = ? AND slot = ?", (source, slot)).fetchone() is None:
            raise ValueError(f"No {slot} planned on {source}")
        if source != target:
            conn.execute("UPDATE meals SET date = 'moving' WHERE date = ? AND slot = ?", (source, slot))
            conn.execute("UPDATE meals SET date = ? WHERE date = ? AND slot = ?", (source, target, slot))
            conn.execute("UPDATE meals SET date = ? WHERE date = 'moving' AND slot = ?", (target, slot))
        return [_meal(row) for row in conn.execute(
            "SELECT * FROM meals WHERE date IN (?, ?) AND slot = ? ORDER BY date", (source, target, slot))]


def get_meal_ingredients(day: str, slot: Slot = "dinner") -> list[dict]:
    """List a planned meal's recipe ingredients as grocery items, flagging what's already in the pantry and
    staples like salt, ready to add with add_grocery_items. Empty if the meal has no recipe."""
    with _tx() as conn:
        row = conn.execute("SELECT recipe_json FROM meals WHERE date = ? AND slot = ?", (_iso(day), slot)).fetchone()
    if row is None:
        raise ValueError(f"No {slot} planned on {_iso(day)}")
    recipe = json.loads(row["recipe_json"]) if row["recipe_json"] else {}
    lines = recipe.get("lines") or [item if isinstance(item, str) else item.get("line") or item.get("name")
                                    for item in recipe.get("ingredients", [])]
    return _flag_ingredients([line for line in lines if line])


def remove_meal(day: str, slot: Slot) -> bool:
    """Remove a planned meal. Returns whether a meal was removed."""
    with _tx() as conn:
        return conn.execute("DELETE FROM meals WHERE date = ? AND slot = ?", (_iso(day), slot)).rowcount > 0


def get_grocery_list(include_checked: bool = False) -> list[dict]:
    """List the grocery list. Checked-off items are hidden unless include_checked is true."""
    where = "" if include_checked else "WHERE checked = 0"
    with _tx() as conn:
        return _rows(conn.execute(f"SELECT * FROM grocery_items {where} ORDER BY checked, name COLLATE NOCASE"))


def add_grocery_items(items: list[GroceryItemIn]) -> list[int]:
    """Add items to the grocery list. Each item is a dict with name (required), qty and unit.
    An item already on the list is merged rather than duplicated, and a checked-off one is unchecked.
    Returns the item ids."""
    ids = []
    with _tx() as conn:
        for item in items:
            name, qty, unit = _text(item["name"]), item.get("qty"), item.get("unit")
            existing = conn.execute(
                "SELECT id, qty, unit, checked FROM grocery_items WHERE name = ? COLLATE NOCASE "
                "ORDER BY checked LIMIT 1", (name,)).fetchone()
            conn.execute(
                "INSERT INTO grocery_history (name) VALUES (?) ON CONFLICT (name) DO UPDATE SET "
                "times_added = times_added + 1, last_added = date('now', 'localtime')", (name,))
            if existing is None:
                ids.append(conn.execute(
                    "INSERT INTO grocery_items (name, qty, unit) VALUES (?, ?, ?)", (name, qty, unit)).lastrowid)
                continue
            if existing["checked"]:
                conn.execute("UPDATE grocery_items SET checked = 0, qty = ?, unit = ? WHERE id = ?",
                             (qty, unit, existing["id"]))
            elif existing["qty"] is not None and qty is not None and existing["unit"] == unit:
                conn.execute("UPDATE grocery_items SET qty = ? WHERE id = ?", (existing["qty"] + qty, existing["id"]))
            ids.append(existing["id"])
    return ids


def check_grocery_item(item_id: int, checked: bool = True) -> dict:
    """Check an item off the grocery list, or uncheck it with checked=false."""
    with _tx() as conn:
        if conn.execute("UPDATE grocery_items SET checked = ? WHERE id = ?", (int(checked), item_id)).rowcount == 0:
            raise ValueError(f"No grocery item with id {item_id}")
    return {"id": item_id, "checked": checked}


def clear_checked_groceries() -> int:
    """Delete every checked-off item from the grocery list. Returns how many were removed."""
    with _tx() as conn:
        return conn.execute("DELETE FROM grocery_items WHERE checked = 1").rowcount


def get_frequent_groceries(limit: int = 12) -> list[str]:
    """Suggest grocery items to re-add: the ones bought most often, then common staples,
    skipping anything already on the list."""
    with _tx() as conn:
        on_list = {r["name"].lower() for r in conn.execute("SELECT name FROM grocery_items WHERE checked = 0")}
        history = [r["name"] for r in conn.execute(
            "SELECT name FROM grocery_history ORDER BY times_added DESC, last_added DESC, name")]
    suggestions = []
    for name in history + STAPLES:
        if name.lower() not in on_list and name.lower() not in {s.lower() for s in suggestions}:
            suggestions.append(name)
    return suggestions[:limit]


def read_recipe(link_or_text: str) -> dict:
    """Read a recipe from a link (any site that publishes standard recipe data, like NYT Cooking) or from pasted
    ingredient lines, and list its ingredients as grocery items. Doesn't add anything: each ingredient says whether
    it's already in the pantry or is a staple like salt, and `suggested` marks the ones worth buying."""
    text = link_or_text.strip()
    if re.match(r"^https?://\S+$", text):
        recipe = recipes.fetch_recipe(text)
    else:
        recipe = {"title": "Pasted ingredients", "lines": recipes.parse_ingredient_text(text), "steps": [], "source": None}
        if not recipe["lines"]:
            raise ValueError("Paste a recipe link or at least one ingredient line")
    return {"title": recipe["title"], "source": recipe["source"], "lines": recipe["lines"],
            "ingredients": _flag_ingredients(recipe["lines"]), "steps": recipe["steps"]}


def _flag_ingredients(lines):
    with _tx() as conn:
        pantry = [r["name"].lower() for r in conn.execute("SELECT name FROM pantry_items")]
    ingredients = []
    for line in lines:
        name = recipes.ingredient_name(line)
        lowered = name.lower()
        in_pantry = any(item == lowered or (len(item) >= 3 and item in lowered) for item in pantry)
        staple = recipes.is_staple(name)
        ingredients.append({"line": line, "name": name, "in_pantry": in_pantry, "staple": staple,
                            "suggested": not (in_pantry or staple)})
    return ingredients
