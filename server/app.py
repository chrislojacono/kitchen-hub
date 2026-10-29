import os
import secrets
from functools import wraps
from typing import NotRequired, TypedDict

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from core import tools
from server import phone

TOKEN = os.environ.get("KITCHEN_TOKEN", "")
if len(TOKEN) < 32:
    raise RuntimeError("Set KITCHEN_TOKEN to a random value of at least 32 characters (see README)")

OPEN_PATHS = {"/docs", "/openapi.json", "/pair", "/m", "/m/app.js", "/m/meals.js"}
BEARER_ONLY_PREFIXES = ("/api/pair", "/api/phones/")

TOOLS = [
    tools.get_pantry, tools.add_pantry_items, tools.use_pantry_item, tools.get_expiring,
    tools.get_meal_plan, tools.set_meal, tools.remove_meal,
    tools.get_grocery_list, tools.add_grocery_items, tools.check_grocery_item, tools.clear_checked_groceries,
    tools.get_frequent_groceries, tools.read_recipe,
    tools.get_cooks, tools.move_meal, tools.get_meal_ingredients,
]

mcp = MCPServer(
    "kitchen-hub",
    instructions="Household kitchen: pantry inventory with expiry dates, a meal plan, and a grocery list. "
                 "Dates are YYYY-MM-DD.",
)


def _tool(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return wrapper


for fn in TOOLS:
    mcp.add_tool(_tool(fn))

# host="0.0.0.0" turns off the SDK's localhost-only DNS-rebinding check so tailnet hostnames work; the bearer token below covers it
mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")

app = FastAPI(title="Kitchen Hub", lifespan=lambda _: mcp.session_manager.run())


@app.middleware("http")
async def require_token(request: Request, call_next):
    path = request.url.path
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
    allowed = (
        path in OPEN_PATHS
        or secrets.compare_digest(supplied.encode(), TOKEN.encode())
        or (path.startswith("/api/") and not path.startswith(BEARER_ONLY_PREFIXES)
            and phone.valid_session(request.cookies.get(phone.COOKIE)))
    )
    if not allowed:
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid token"})
    return await call_next(request)


@app.exception_handler(ValueError)
async def bad_input(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/pantry")
def pantry():
    return tools.get_pantry()


@app.get("/api/expiring")
def expiring(days: int = 3):
    return tools.get_expiring(days)


class DinnerIn(TypedDict):
    title: str
    recipe: NotRequired[dict | None]
    cook: NotRequired[str | None]
    takeout: NotRequired[bool]
    notes: NotRequired[str | None]


@app.get("/api/meals")
def meals(start: str | None = None, days: int = 7):
    return tools.get_meal_plan(start, min(days, 62))


@app.get("/api/cooks")
def cooks():
    return tools.get_cooks()


@app.put("/api/meals/{day}")
def set_dinner(day: str, dinner: DinnerIn):
    return tools.set_meal(day, "dinner", dinner["title"], dinner.get("recipe"), dinner.get("cook"),
                          dinner.get("takeout", False), dinner.get("notes"))


@app.delete("/api/meals/{day}")
def remove_dinner(day: str):
    return {"removed": tools.remove_meal(day, "dinner")}


@app.post("/api/meals/{day}/move")
def move_dinner(day: str, to: str):
    return tools.move_meal(day, to)


@app.get("/api/meals/{day}/ingredients")
def dinner_ingredients(day: str):
    return tools.get_meal_ingredients(day)


@app.get("/api/grocery")
def grocery(include_checked: bool = False):
    return tools.get_grocery_list(include_checked)


@app.post("/api/grocery")
def add_grocery(items: list[tools.GroceryItemIn]):
    return tools.add_grocery_items(items)


@app.get("/api/grocery/frequent")
def frequent_groceries(limit: int = 12):
    return tools.get_frequent_groceries(limit)


@app.post("/api/grocery/{item_id}/check")
def check_grocery(item_id: int, checked: bool = True):
    return tools.check_grocery_item(item_id, checked)


@app.post("/api/grocery/clear-checked")
def clear_checked_groceries():
    return {"removed": tools.clear_checked_groceries()}


@app.post("/api/recipes/read")
def read_recipe(link_or_text: str = Body(embed=True, max_length=20_000)):
    return tools.read_recipe(link_or_text)


app.include_router(phone.router)
app.mount("/", mcp_app)
