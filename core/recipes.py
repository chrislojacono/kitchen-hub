import html
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

MAX_PAGE_BYTES = 3_000_000
MAX_LINES = 100
MAX_LINE_LENGTH = 200
TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 3
USER_AGENT = "KitchenHub/1.0 (personal recipe import)"
REDIRECT_CODES = {301, 302, 303, 307, 308}

FRACTIONS = "½⅓⅔¼¾⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚"
QUANTITY = re.compile(rf"^(about|approximately|roughly|heaping|scant|generous)?\s*[\d{FRACTIONS}][\d{FRACTIONS}\s/.,\-–]*"
                      rf"(\s*(to|or)\s*[\d{FRACTIONS}][\d{FRACTIONS}\s/.\-–]*)?\s*", re.IGNORECASE)
UNITS = (r"cups?|tablespoons?|tbsps?|tbs|teaspoons?|tsps?|pounds?|lbs?|ounces?|oz|grams?|g|kilograms?|kg|"
         r"milliliters?|millilitres?|ml|liters?|litres?|l|quarts?|qt|pints?|pt|pinch(es)?|dash(es)?|cloves?|"
         r"cans?|jars?|packages?|pkgs?|sticks?|sprigs?|bunch(es)?|handfuls?|slices?|heads?|stalks?|pieces?|"
         r"fillets?|bottles?|bags?|boxes?|containers?")
LEADING_UNIT = re.compile(rf"^({UNITS})\.?\s+(of\s+)?", re.IGNORECASE)
LEADING_SIZE = re.compile(r"^(extra[- ]large|large|medium|small|whole|heaping|level)\s+", re.IGNORECASE)
TRAILING_NOTE = re.compile(r",.*$|\s+(plus\s+more|for|to taste|as needed|optional)\b.*$", re.IGNORECASE)
COMBINED_AMOUNT = re.compile(r"^(plus|minus)\s+", re.IGNORECASE)
STAPLE = re.compile(r"^((kosher|sea|flaky|fine|table|coarse|maldon)\s+)*salt\b|^((freshly|coarsely)\s+)?(ground\s+)?(black\s+)?pepper$|"
                    r"^((freshly|coarsely)\s+)?ground\s+(black\s+)?pepper\b|^(cold\s+|warm\s+|hot\s+)?water\b|^ice\b",
                    re.IGNORECASE)
BULLET = re.compile(r"^\s*([-*•▢□☐◦]|\d+[.)])\s+")


class _JsonLdBlocks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks, self._buffer, self._inside = [], [], False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and (dict(attrs).get("type") or "").lower() == "application/ld+json":
            self._inside, self._buffer = True, []

    def handle_endtag(self, tag):
        if tag == "script" and self._inside:
            self.blocks.append("".join(self._buffer))
            self._inside = False

    def handle_data(self, data):
        if self._inside:
            self._buffer.append(data)


def _clean(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(text))).split())


def _is_recipe(node):
    kind = node.get("@type")
    return kind == "Recipe" or (isinstance(kind, list) and "Recipe" in kind)


def _find_recipe(node):
    if isinstance(node, list):
        return next((found for item in node if (found := _find_recipe(item))), None)
    if isinstance(node, dict):
        if _is_recipe(node):
            return node
        return next((found for key in ("@graph", "mainEntity", "mainEntityOfPage")
                     if (found := _find_recipe(node.get(key)))), None)
    return None


def _steps(instructions):
    if isinstance(instructions, str):
        return [line for line in (_clean(part) for part in instructions.split("\n")) if line]
    if isinstance(instructions, list):
        return [step for item in instructions for step in _steps(item)]
    if isinstance(instructions, dict):
        if "itemListElement" in instructions:
            return _steps(instructions["itemListElement"])
        return _steps(instructions.get("text", ""))
    return []


def parse_recipe_html(page):
    parser = _JsonLdBlocks()
    parser.feed(page)
    for block in parser.blocks:
        try:
            recipe = _find_recipe(json.loads(block))
        except json.JSONDecodeError:
            continue
        if recipe:
            lines = recipe.get("recipeIngredient") or recipe.get("ingredients") or []
            return {
                "title": _clean(recipe.get("name", "")) or "Recipe",
                "lines": [line for line in (_clean(item) for item in lines) if line][:MAX_LINES],
                "steps": _steps(recipe.get("recipeInstructions")),
            }
    return None


def parse_ingredient_text(text):
    lines = []
    for raw in text.splitlines():
        line = _clean(BULLET.sub("", raw))
        if line and not line.endswith(":") and len(line) <= MAX_LINE_LENGTH:
            lines.append(line)
    return lines[:MAX_LINES]


def ingredient_name(line):
    name = re.sub(r"\([^)]*\)", " ", line)
    name = TRAILING_NOTE.sub("", " ".join(name.split()))
    name = QUANTITY.sub("", name)
    name = LEADING_UNIT.sub("", name)
    if COMBINED_AMOUNT.match(name):
        name = LEADING_UNIT.sub("", QUANTITY.sub("", COMBINED_AMOUNT.sub("", name)))
    name = LEADING_SIZE.sub("", name)
    name = re.sub(r"^of\s+", "", name, flags=re.IGNORECASE).strip(" .-–")
    if not name:
        name = line
    return (name[0].upper() + name[1:])[:80]


def is_staple(name):
    return bool(STAPLE.search(name))


def _check_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Use an http or https recipe link")
    if parts.port not in (None, 80, 443):
        raise ValueError("Recipe links must use the standard web ports")
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError("Couldn't find that website") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ValueError("That link points to a private network address")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirects)


def fetch_recipe(url):
    # ponytail: the IP check and the connection resolve DNS separately (rebinding window); pin the resolved IP if this ever faces untrusted users
    for _ in range(MAX_REDIRECTS + 1):
        _check_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        try:
            with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read(MAX_PAGE_BYTES + 1)
                charset = response.headers.get_content_charset() or "utf-8"
        except urllib.error.HTTPError as exc:
            if exc.code in REDIRECT_CODES and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                continue
            raise ValueError(f"The site refused the request (HTTP {exc.code}). Paste the ingredients instead.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValueError("Couldn't reach that website") from exc
        if body[:2] == b"\x1f\x8b":
            # Some sites gzip the page even when the request didn't ask for it.
            inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
            body = inflater.decompress(body, MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            raise ValueError("That page is too large")
        recipe = parse_recipe_html(body.decode(charset, errors="replace"))
        if recipe is None or not recipe["lines"]:
            raise ValueError("No recipe found on that page. Copy the ingredient list and paste it instead.")
        return {**recipe, "source": url}
    raise ValueError("That link redirected too many times")
