import json
import tempfile
from pathlib import Path

from core import db, recipes, tools


def _page(data):
    return f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head><body></body></html>'


def _raises(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    raise AssertionError(f"{fn.__name__}{args} did not raise")


def test_parse_json_ld():
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": "Not this"},
        {"@type": ["Recipe", "NewsArticle"], "name": "Weeknight Dal &amp; Rice",
         "recipeIngredient": ["1 cup <a href='/x'>red lentils</a>", "  ", "2 tablespoons ghee"],
         "recipeInstructions": [{"@type": "HowToSection", "name": "Dal", "itemListElement": [
             {"@type": "HowToStep", "text": "Rinse the lentils."}, {"@type": "HowToStep", "text": "Simmer."}]},
             "Serve."]},
    ]}
    recipe = recipes.parse_recipe_html('<script type="application/ld+json">{broken</script>' + _page(graph))
    assert recipe["title"] == "Weeknight Dal & Rice"
    assert recipe["lines"] == ["1 cup red lentils", "2 tablespoons ghee"]
    assert recipe["steps"] == ["Rinse the lentils.", "Simmer.", "Serve."]
    assert recipes.parse_recipe_html(_page({"@type": "Article"})) is None


def test_ingredient_names():
    cases = {
        "2 tablespoons extra-virgin olive oil, plus more for drizzling": "Extra-virgin olive oil",
        "1 (14-ounce) can coconut milk": "Coconut milk",
        "3 garlic cloves, minced": "Garlic cloves",
        "½ cup chopped cilantro": "Chopped cilantro",
        "1 1/2 pounds boneless chicken thighs": "Boneless chicken thighs",
        "2 to 3 large eggs": "Eggs",
        "About 4 cups of vegetable stock": "Vegetable stock",
        "Kosher salt and black pepper": "Kosher salt and black pepper",
        "Lemon wedges, for serving": "Lemon wedges",
        "1 red bell pepper": "Red bell pepper",
        "2 cups minus 2 tablespoons cake flour (8 ½ ounces)": "Cake flour",
        "1 cup plus 2 tablespoons granulated sugar (8 ounces)": "Granulated sugar",
        "1 ½ teaspoons coarse sea salt, plus more for sprinkling": "Coarse sea salt",
        "Chopped parsley, for garnish": "Chopped parsley",
        "8 to 12 pepperoncini": "Pepperoncini",
    }
    for line, expected in cases.items():
        assert recipes.ingredient_name(line) == expected, (line, recipes.ingredient_name(line))
    assert recipes.is_staple("Kosher salt and black pepper") and recipes.is_staple("Water")
    assert recipes.is_staple("Freshly ground black pepper") and recipes.is_staple("Coarse sea salt")
    assert not recipes.is_staple("Red bell pepper") and not recipes.is_staple("Coconut milk")


def test_pasted_text_and_pantry():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    tools.add_pantry_items([{"name": "Olive oil"}])
    text = "For the dressing:\n- 3 tbsp extra-virgin olive oil\n• 1 lemon\n\n2. Kosher salt\n" + "x" * 300
    recipe = tools.read_recipe(text)
    assert recipe["source"] is None
    assert [(i["name"], i["in_pantry"], i["staple"], i["suggested"]) for i in recipe["ingredients"]] == [
        ("Extra-virgin olive oil", True, False, False),
        ("Lemon", False, False, True),
        ("Kosher salt", False, True, False),
    ]
    assert _raises(tools.read_recipe, "  \n ")


def test_unsafe_links_rejected():
    for url in ("file:///etc/passwd", "ftp://example.com/r", "http://localhost/recipe", "http://127.0.0.1/",
                "http://10.0.0.5/recipe", "http://192.168.1.41/admin", "http://169.254.169.254/latest/meta-data",
                "http://[::1]/", "http://[::ffff:127.0.0.1]/", "https://example.com:8443/recipe"):
        assert _raises(recipes.fetch_recipe, url), url


if __name__ == "__main__":
    for test in (test_parse_json_ld, test_ingredient_names, test_pasted_text_and_pantry, test_unsafe_links_rejected):
        test()
        print(f"{test.__name__} ok")
