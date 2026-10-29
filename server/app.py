import os
import secrets
from functools import wraps

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from core import tools

TOKEN = os.environ.get("KITCHEN_TOKEN", "")
if len(TOKEN) < 32:
    raise RuntimeError("Set KITCHEN_TOKEN to a random value of at least 32 characters (see README)")

OPEN_PATHS = {"/docs", "/openapi.json"}

TOOLS = [
    tools.get_pantry, tools.add_pantry_items, tools.use_pantry_item, tools.get_expiring,
    tools.get_meal_plan, tools.set_meal, tools.remove_meal,
    tools.get_grocery_list, tools.add_grocery_items, tools.check_grocery_item, tools.clear_checked_groceries,
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
    if request.url.path not in OPEN_PATHS:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not secrets.compare_digest(supplied.encode(), TOKEN.encode()):
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


@app.get("/api/meals")
def meals(start: str | None = None, days: int = 7):
    return tools.get_meal_plan(start, days)


@app.get("/api/grocery")
def grocery(include_checked: bool = False):
    return tools.get_grocery_list(include_checked)


@app.post("/api/grocery/{item_id}/check")
def check_grocery(item_id: int, checked: bool = True):
    return tools.check_grocery_item(item_id, checked)


@app.post("/api/grocery/clear-checked")
def clear_checked_groceries():
    return {"removed": tools.clear_checked_groceries()}


app.mount("/", mcp_app)
