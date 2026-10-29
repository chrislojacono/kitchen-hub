import json
from contextlib import contextmanager
from datetime import date, timedelta

from core import db

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


def _iso(value):
    return date.fromisoformat(value).isoformat() if value else None


def get_pantry():
    """List everything in the pantry, soonest-expiring first."""
    with _tx() as conn:
        return _rows(conn.execute(
            "SELECT * FROM pantry_items ORDER BY expires_on IS NULL, expires_on, name"))


def add_pantry_items(items, source="manual"):
    """Add items to the pantry. Each item is a dict with name (required), qty, unit, category,
    and expires_on (YYYY-MM-DD). Returns the new item ids."""
    ids = []
    with _tx() as conn:
        for item in items:
            cur = conn.execute(
                "INSERT INTO pantry_items (name, qty, unit, category, expires_on, source) VALUES (?, ?, ?, ?, ?, ?)",
                (item["name"].strip(), 1 if item.get("qty") is None else item["qty"], item.get("unit"),
                 item.get("category"), _iso(item.get("expires_on")), source))
            ids.append(cur.lastrowid)
    return ids


def use_pantry_item(item_id, qty=None):
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


def get_expiring(days=3):
    """List pantry items that expire within the given number of days, including ones already expired."""
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    with _tx() as conn:
        return _rows(conn.execute(
            "SELECT * FROM pantry_items WHERE expires_on IS NOT NULL AND expires_on <= ? ORDER BY expires_on, name",
            (cutoff,)))


def get_meal_plan(start=None, days=7):
    """List planned meals for a range of days starting at start (YYYY-MM-DD, default today)."""
    first = date.fromisoformat(start) if start else date.today()
    last = first + timedelta(days=days - 1)
    with _tx() as conn:
        meals = _rows(conn.execute(
            f"SELECT * FROM meals WHERE date BETWEEN ? AND ? ORDER BY date, {SLOT_ORDER}",
            (first.isoformat(), last.isoformat())))
    for meal in meals:
        raw = meal.pop("recipe_json")
        meal["recipe"] = json.loads(raw) if raw else None
    return meals


def set_meal(day, slot, title, recipe=None):
    """Plan a meal, replacing whatever was in that slot. day is YYYY-MM-DD, slot is breakfast, lunch,
    dinner or snack. recipe is optional: a dict such as {"ingredients": [...], "steps": [...]}."""
    with _tx() as conn:
        conn.execute(
            "INSERT INTO meals (date, slot, title, recipe_json) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (date, slot) DO UPDATE SET title = excluded.title, recipe_json = excluded.recipe_json",
            (_iso(day), slot, title.strip(), json.dumps(recipe) if recipe else None))
    return {"date": _iso(day), "slot": slot, "title": title.strip()}


def remove_meal(day, slot):
    """Remove a planned meal. Returns whether a meal was removed."""
    with _tx() as conn:
        return conn.execute("DELETE FROM meals WHERE date = ? AND slot = ?", (_iso(day), slot)).rowcount > 0


def get_grocery_list(include_checked=False):
    """List the grocery list. Checked-off items are hidden unless include_checked is true."""
    where = "" if include_checked else "WHERE checked = 0"
    with _tx() as conn:
        return _rows(conn.execute(f"SELECT * FROM grocery_items {where} ORDER BY checked, name"))


def add_grocery_items(items):
    """Add items to the grocery list. Each item is a dict with name (required), qty and unit.
    An item already on the list is merged rather than duplicated. Returns the item ids."""
    ids = []
    with _tx() as conn:
        for item in items:
            name, qty, unit = item["name"].strip(), item.get("qty"), item.get("unit")
            existing = conn.execute(
                "SELECT id, qty, unit FROM grocery_items WHERE checked = 0 AND name = ? COLLATE NOCASE",
                (name,)).fetchone()
            if existing is None:
                ids.append(conn.execute(
                    "INSERT INTO grocery_items (name, qty, unit) VALUES (?, ?, ?)", (name, qty, unit)).lastrowid)
                continue
            if existing["qty"] is not None and qty is not None and existing["unit"] == unit:
                conn.execute("UPDATE grocery_items SET qty = ? WHERE id = ?", (existing["qty"] + qty, existing["id"]))
            ids.append(existing["id"])
    return ids


def check_grocery_item(item_id, checked=True):
    """Check an item off the grocery list, or uncheck it with checked=false."""
    with _tx() as conn:
        if conn.execute("UPDATE grocery_items SET checked = ? WHERE id = ?", (int(checked), item_id)).rowcount == 0:
            raise ValueError(f"No grocery item with id {item_id}")
    return {"id": item_id, "checked": checked}


def clear_checked_groceries():
    """Delete every checked-off item from the grocery list. Returns how many were removed."""
    with _tx() as conn:
        return conn.execute("DELETE FROM grocery_items WHERE checked = 1").rowcount
