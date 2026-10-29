import os
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

from core import db, tools

TODAY = date.today()


def _day(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


def _fresh_db():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"


def test_pantry():
    _fresh_db()
    milk, rice, salt = tools.add_pantry_items([
        {"name": " Milk ", "qty": 2, "unit": "L", "expires_on": _day(2)},
        {"name": "Rice", "expires_on": _day(30)},
        {"name": "Salt"},
    ])
    assert [i["name"] for i in tools.get_pantry()] == ["Milk", "Rice", "Salt"]
    assert [i["name"] for i in tools.get_expiring(3)] == ["Milk"]

    assert tools.use_pantry_item(milk, 0.5)["remaining"] == 1.5
    assert tools.use_pantry_item(milk, 5)["remaining"] == 0
    assert tools.use_pantry_item(rice)["remaining"] == 0
    assert [i["id"] for i in tools.get_pantry()] == [salt]

    for bad in (lambda: tools.use_pantry_item(999), lambda: tools.use_pantry_item(salt, 0),
                lambda: tools.add_pantry_items([{"name": "x", "expires_on": "soon"}])):
        try:
            bad()
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_meals():
    _fresh_db()
    tools.set_meal(_day(0), "dinner", "Tacos")
    tools.set_meal(_day(0), "breakfast", "Oats")
    tools.set_meal(_day(0), "dinner", "Curry", {"ingredients": ["rice"], "steps": ["cook"]})
    tools.set_meal(_day(9), "lunch", "Out of range")

    plan = tools.get_meal_plan()
    assert [(m["slot"], m["title"]) for m in plan] == [("breakfast", "Oats"), ("dinner", "Curry")]
    assert plan[0]["recipe"] is None and plan[1]["recipe"]["steps"] == ["cook"]
    assert "recipe_json" not in plan[0]

    assert tools.remove_meal(_day(0), "breakfast") is True
    assert tools.remove_meal(_day(0), "breakfast") is False


def test_grocery():
    _fresh_db()
    eggs, = tools.add_grocery_items([{"name": "Eggs", "qty": 6}])
    assert tools.add_grocery_items([{"name": "eggs", "qty": 6}, {"name": "Bread"}])[0] == eggs
    items = {i["name"]: i for i in tools.get_grocery_list()}
    assert items["Eggs"]["qty"] == 12 and "Bread" in items

    tools.check_grocery_item(eggs)
    assert [i["name"] for i in tools.get_grocery_list()] == ["Bread"]
    assert len(tools.get_grocery_list(include_checked=True)) == 2

    assert tools.add_grocery_items([{"name": "Eggs", "qty": 2}]) == [eggs]
    assert {i["name"]: i["qty"] for i in tools.get_grocery_list()} == {"Bread": None, "Eggs": 2}
    tools.check_grocery_item(eggs)
    assert tools.clear_checked_groceries() == 1
    assert [i["name"] for i in tools.get_grocery_list(include_checked=True)] == ["Bread"]


def test_frequent_groceries():
    _fresh_db()
    assert tools.get_frequent_groceries(3) == ["Milk", "Eggs", "Bread"]
    tools.add_grocery_items([{"name": "Oat milk"}, {"name": "Limes"}])
    tools.add_grocery_items([{"name": "oat milk"}])
    tools.check_grocery_item(1)
    tools.clear_checked_groceries()
    frequent = tools.get_frequent_groceries(4)
    assert frequent == ["Oat milk", "Milk", "Eggs", "Bread"], frequent
    assert "Limes" not in tools.get_frequent_groceries(20)


def test_names_validated():
    _fresh_db()
    assert tools.add_grocery_items([{"name": "  Greek   yogurt "}]) == [1]
    assert tools.get_grocery_list()[0]["name"] == "Greek yogurt"
    for bad in ("", "   ", "x" * 81):
        try:
            tools.add_grocery_items([{"name": bad}])
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass


def test_dinner_plan():
    _fresh_db()
    os.environ["KITCHEN_COOKS"] = "Alex, Sam"
    assert tools.get_cooks() == ["Alex", "Sam"]
    tools.add_pantry_items([{"name": "Rice"}])
    tacos = tools.set_meal(_day(0), "dinner", "Tacos", cook="Alex",
                           recipe={"lines": ["1 lb ground beef", "2 cups rice", "Kosher salt"]})
    assert tacos["cook"] == "Alex" and tacos["takeout"] is False and tacos["recipe"]["lines"][0] == "1 lb ground beef"
    tools.set_meal(_day(2), "dinner", "Take-Out!", takeout=True)
    try:
        tools.set_meal(_day(1), "dinner", "Soup", cook="Nobody")
        raise AssertionError("accepted an unknown cook")
    except ValueError:
        pass

    assert [(i["name"], i["suggested"]) for i in tools.get_meal_ingredients(_day(0))] == [
        ("Ground beef", True), ("Rice", False), ("Kosher salt", False)]
    assert tools.get_meal_ingredients(_day(2)) == []

    moved = tools.move_meal(_day(0), _day(1))
    assert [(m["date"], m["title"]) for m in moved] == [(_day(1), "Tacos")]
    swapped = tools.move_meal(_day(1), _day(2))
    assert [(m["date"], m["title"], m["takeout"]) for m in swapped] == [
        (_day(1), "Take-Out!", True), (_day(2), "Tacos", False)]
    assert tools.get_meal_plan()[1]["cook"] == "Alex"
    try:
        tools.move_meal(_day(5), _day(6))
        raise AssertionError("moved a missing meal")
    except ValueError:
        pass


def test_old_database_upgraded():
    path = Path(tempfile.mkdtemp()) / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE meals (id INTEGER PRIMARY KEY, date TEXT NOT NULL, slot TEXT NOT NULL, "
                     "title TEXT NOT NULL, recipe_json TEXT, UNIQUE (date, slot))")
        conn.execute("INSERT INTO meals (date, slot, title) VALUES ('2026-01-01', 'dinner', 'Old meal')")
    db.DB_PATH = path
    meal = tools.get_meal_plan("2026-01-01", 1)[0]
    assert meal["title"] == "Old meal" and meal["cook"] is None and meal["takeout"] is False
    db.connect().close()


if __name__ == "__main__":
    for test in (test_pantry, test_meals, test_grocery, test_frequent_groceries, test_names_validated,
                 test_dinner_plan, test_old_database_upgraded):
        test()
        print(f"{test.__name__} ok")
