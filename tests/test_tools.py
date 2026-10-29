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

    new_eggs, = tools.add_grocery_items([{"name": "Eggs"}])
    assert new_eggs != eggs
    assert tools.clear_checked_groceries() == 1
    assert {i["name"] for i in tools.get_grocery_list()} == {"Bread", "Eggs"}


if __name__ == "__main__":
    for test in (test_pantry, test_meals, test_grocery):
        test()
        print(f"{test.__name__} ok")
