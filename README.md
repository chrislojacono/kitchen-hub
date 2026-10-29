# Kitchen Hub

A kitchen assistant that runs on a Raspberry Pi with a touchscreen. It keeps track of your **pantry**, **meal plan** and **grocery list**, and lets Claude manage all three through an [MCP](https://modelcontextprotocol.io) server.

> **Status:** the grocery list works end to end today: on the touchscreen, on your phone, and through Claude. More screens, the "plan my week" agent and receipt scanning are coming next (see [Roadmap](#roadmap)).

| Kitchen touchscreen | Your phone |
|---|---|
| ![Grocery list on the 7" touchscreen](docs/grocery-screen.png) | <img src="docs/phone-page.jpg" alt="Grocery list on a phone" width="260"> |

## What it does

- **Pantry:** what you have, how much, and when it expires. Shows what to use soon.
- **Meal plan:** breakfast, lunch, dinner and snacks by day, with optional recipes.
- **Grocery list:** add and check off items. Adding something already on the list merges it instead of creating a duplicate, and re-adding something you checked off brings it back.
- **Touchscreen app:** a big-button kitchen display. Tap an item to check it off; it dims in place so nothing moves under your finger. **+ Add** shows one-tap buttons for the things you buy most.
- **Phone page:** tap **Phone** on the touchscreen and scan the QR code. Your phone gets the grocery list with a text box for adding anything, suggestion chips, and check-offs. Type `2 avocados` and it records the quantity. Save it to your home screen and it works like an app.
- **Claude integration:** any MCP client, such as Claude Code, can read and change all of the above. Ask "what's expiring this week?" or "add milk and eggs to the grocery list".

## How it works

```mermaid
flowchart LR
    CC[Claude Code / MCP client] -- /mcp --> S
    UI[Touchscreen app] -- /api --> S
    PH[Phone browser] -- /m and /api --> S
    S[FastAPI server :8000] --> T[core/tools.py]
    T --> DB[(SQLite kitchen.db)]
```

- **`core/tools.py`** holds every kitchen action (add an item, set a meal, check off a grocery). Each piece of the app calls these same functions, so the logic lives in one place.
- **`server/app.py`** is a single FastAPI server that exposes those functions two ways: as an MCP server at `/mcp` for Claude, and as a small REST API at `/api` for the touchscreen.
- **`server/phone.py`** handles pairing phones and serves the phone page (`server/static/`). Plain HTML, CSS and JavaScript, with no build step and no outside requests.
- **`ui/`** is the Kivy touchscreen app. It only talks to the server's REST API, always from a background thread so taps never freeze while the network is slow.
- **`core/db.py`** stores everything in a single SQLite file. The tables are created automatically the first time it runs.

## What you need

- **Python 3.13**
- To use it with Claude: **Claude Code**, or another MCP client that supports HTTP servers
- For the touchscreen app: **Kivy 2.3** and a screen. The project is built on a **Raspberry Pi Zero 2 W** with a 7" 1024x600 touchscreen, and also runs in a window on Windows for development.

## Setup

1. **Clone and enter the repo:**
   ```bash
   git clone <repo-url> kitchen-hub
   cd kitchen-hub
   ```

2. **Create a virtual environment and install dependencies.**

   Windows:
   ```bash
   py -3.13 -m venv venv
   venv\Scripts\python -m pip install -r requirements.txt
   ```

   Linux / Raspberry Pi:
   ```bash
   python3 -m venv venv --system-site-packages
   venv/bin/python -m pip install -r requirements.txt
   ```

3. **Create your `.env` file.** Copy `.env.example` to `.env`, then set `KITCHEN_TOKEN` to a random value:
   ```bash
   venv/Scripts/python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   `.env` is gitignored. Never commit it or paste the token anywhere public.

4. **Run the tests:**
   ```bash
   venv/Scripts/python -m tests.test_tools
   venv/Scripts/python -m tests.test_server
   ```
   Use `venv/bin/python` on Linux. Every line should end in `ok`.

5. **Start the server:**
   ```bash
   venv/Scripts/python -m uvicorn server.app:app --env-file .env --host 0.0.0.0 --port 8000
   ```
   The server refuses to start without a `KITCHEN_TOKEN` of at least 32 characters. Interactive API docs are at http://localhost:8000/docs.

6. **Start the touchscreen app** (in a second terminal, with the server running).

   Install Kivy first. It isn't in `requirements.txt` because the Pi gets it from apt:
   - Windows: `venv\Scripts\python -m pip install kivy`
   - Raspberry Pi: `sudo apt install python3-kivy` (the venv sees it through `--system-site-packages`)

   Then run:
   ```bash
   venv/Scripts/python -m ui.main
   ```
   It opens a 1024x600 window on Windows and goes fullscreen on Linux. It reads the same `.env`, so it uses your token automatically.

7. **Connect your phone.** Tap **Phone** on the touchscreen and scan the code with your phone's camera. Your phone has to be on the same network as the server (or on Tailscale). Then use your browser's "Add to Home Screen". Set `KITCHEN_PUBLIC_URL` if the QR code should use a hostname instead of the server's local IP; see [Configuration](#configuration).

![Quick add on the touchscreen](docs/quick-add.png)
![Pairing a phone](docs/phone-pairing.png)

## Connect Claude

With the server running, register it with Claude Code:

```bash
claude mcp add --transport http kitchen http://localhost:8000/mcp --header "Authorization: Bearer <your KITCHEN_TOKEN>"
```

This saves the token in your local Claude Code config, not in the repo.

From another device, replace `localhost` with the server's hostname (for example its Tailscale name). Then try:

- "Add 2 litres of milk expiring Friday to the pantry"
- "Plan dinners for this week using what's expiring"
- "What's on my grocery list?"

### MCP tools

| Tool | What it does |
|---|---|
| `get_pantry` | List pantry items, soonest-expiring first |
| `add_pantry_items` | Add items (name, qty, unit, category, expiry) |
| `use_pantry_item` | Use part of an item, or remove it entirely |
| `get_expiring` | Items expiring within N days, including already expired |
| `get_meal_plan` | Meals for a range of days |
| `set_meal` | Plan a meal in a slot, replacing what was there |
| `remove_meal` | Remove a planned meal |
| `get_grocery_list` | The grocery list, optionally including checked items |
| `add_grocery_items` | Add items, merging any already on the list |
| `check_grocery_item` | Check or uncheck an item |
| `clear_checked_groceries` | Delete checked-off items |
| `get_frequent_groceries` | Suggest items to re-add: the most bought first, then common staples |

### REST API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/pantry` | All pantry items |
| GET | `/api/expiring?days=3` | Items expiring soon |
| GET | `/api/meals?start=YYYY-MM-DD&days=7` | Meal plan (start defaults to today) |
| GET | `/api/grocery?include_checked=false` | Grocery list |
| POST | `/api/grocery` | Add items, body: `[{"name": "Milk", "qty": 2, "unit": "L"}]` |
| GET | `/api/grocery/frequent?limit=12` | Suggested items to re-add |
| POST | `/api/grocery/{id}/check?checked=true` | Check or uncheck an item |
| POST | `/api/grocery/clear-checked` | Delete checked-off items |

| POST | `/api/pair` | One-time QR pairing link for a phone (token only) |
| POST | `/api/phones/revoke-all` | Sign out every paired phone (token only) |

Every request needs the header `Authorization: Bearer <KITCHEN_TOKEN>` (or, for `/api` routes other than the two marked "token only", a paired phone's session cookie); without it you get `401`. Bad input (an unknown id, a malformed date) returns `400` with a `detail` message.

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `KITCHEN_TOKEN` | none (required) | Bearer token every REST and MCP request must send |
| `KITCHEN_DB` | `kitchen.db` in the repo folder | Where the SQLite database lives |
| `KITCHEN_API` | `http://127.0.0.1:8000` | Server address the touchscreen app talks to |
| `KITCHEN_PUBLIC_URL` | `http://<server's local IP>:8000` | Address phones use, put in the pairing QR code. Set it to the Pi's Tailscale name so phones work away from home too. |

Settings are read from `.env` (see `.env.example`).

## Security

- **Secrets stay local.** Tokens and API keys live only in `.env` (gitignored) or the Pi's service environment, never in the code or the repo.
- **Every request is authenticated.** `/api` and `/mcp` require the bearer token (compared in constant time). Only `/docs`, `/openapi.json` and the phone page's empty shell are open, and none of them contain your data.
- **Phones never see the token.** Pairing uses a random one-time code that expires after 5 minutes. Scanning it gives the phone its own session cookie (`HttpOnly`, `SameSite=Lax`), stored only as a SHA-256 hash on the server. Phone sessions can use the grocery API but not `/mcp` or pairing. If a phone is lost, sign them all out:
  ```bash
  curl -X POST -H "Authorization: Bearer <KITCHEN_TOKEN>" http://localhost:8000/api/phones/revoke-all
  ```
- **The phone page is locked down.** It has a strict Content-Security-Policy, renders item names as text and never as HTML, and refuses to be framed.
- **Input is validated.** Item names are trimmed and limited to 80 characters, and dates and meal slots are checked.
- **Network.** Even with the token, run the server only on your home network or a private network like Tailscale. Don't port-forward it to the internet.
- **Database.** `kitchen.db` is gitignored and never leaves the device except in your own backups.

## Project layout

```
core/db.py          SQLite schema and connection
core/tools.py       Every kitchen action (shared by MCP, REST and the UI)
server/app.py       FastAPI server: REST at /api, MCP at /mcp, auth
server/phone.py     Phone pairing, sessions and the phone page
server/static/      Phone page HTML, CSS and JavaScript
ui/main.py          Touchscreen app: screens, arrows, screen-name badge
ui/grocery_screen.py  Grocery list screen
ui/panels.py        Quick add and phone pairing pop-ups
ui/clock_screen.py  Clock screen
ui/api.py           Background-thread REST client for the app
ui/ui_common.py     Shared look: gradients, cards, buttons, tap debounce
tests/              Tests for the tools, auth and phone pairing (temporary databases)
docs/               Screenshots
.env.example        The settings you need, with no values
requirements.txt    Pinned Python dependencies
```

## Roadmap

- [x] Pantry, meal plan and grocery data with tests
- [x] REST API and MCP server
- [x] Touchscreen app with the grocery list and a clock
- [x] Add from your phone (QR pairing) and one-tap quick add
- [ ] More screens: today's meals, pantry, step-by-step cook mode
- [ ] "Plan my week" button: Claude builds a meal plan from what's in the pantry
- [ ] Receipt scanning: photograph a receipt and Claude adds the items to the pantry with expiry dates
- [ ] Runs as a service on the Pi, with nightly backups
- [ ] Remote access from your phone via Tailscale
