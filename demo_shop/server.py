"""A tiny fake shop to scrape, so the tracker can be demoed without hitting real retailers.

Each product page uses a different markup style the tracker has to handle:
JSON-LD, microdata, Open Graph meta tags, plain HTML with a European price
format, and a price that only appears after JavaScript runs.

It also behaves like a shop with basic bot protection:
- requests whose User-Agent says "HeadlessChrome" (Playwright's default) get 403
- a configurable share of product requests get 429 Too Many Requests

Admin endpoints change prices so you can trigger alerts:
    /admin/set-price?sku=espresso-machine&price=399
    /admin/drop?sku=espresso-machine&percent=10
    /admin/requests      (recent requests with their user agents, as JSON)
"""

import argparse
import html
import json
import os
import random
import threading
from collections import deque
from datetime import datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

INITIAL_PRODUCTS = {
    "espresso-machine": {"name": "Barista Pro Espresso Machine", "price": "449.00", "currency": "USD",
                         "in_stock": True, "style": "json-ld"},
    "noise-cancelling-headphones": {"name": "Quiet Hours ANC Headphones", "price": "279.99", "currency": "USD",
                                    "in_stock": True, "style": "microdata"},
    "trail-running-shoes": {"name": "Ridgeline Trail Running Shoes", "price": "119.00", "currency": "GBP",
                            "in_stock": True, "style": "opengraph"},
    "standing-desk": {"name": "Oak Lift Standing Desk", "price": "1249.00", "currency": "EUR",
                      "in_stock": True, "style": "plain"},
    "mechanical-keyboard": {"name": "Clack 75 Mechanical Keyboard", "price": "159.00", "currency": "USD",
                            "in_stock": False, "style": "javascript"},
}
SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}

ROBOTS_TXT = "User-agent: *\nDisallow: /admin/\nAllow: /\n"


def us_format(price: Decimal, currency: str) -> str:
    return f"{SYMBOLS.get(currency, '')}{price:,.2f}"


def eu_format(price: Decimal, currency: str) -> str:
    # 1249.00 -> "1.249,00 €"
    return f"{price:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + f" {SYMBOLS.get(currency, '')}"


class Shop:
    def __init__(self, block_rate: float = 0.0):
        self.block_rate = block_rate
        self.products = {sku: dict(p, price=Decimal(p["price"])) for sku, p in INITIAL_PRODUCTS.items()}
        self.requests: deque[dict] = deque(maxlen=100)
        self.lock = threading.Lock()

    def set_price(self, sku: str, price: Decimal) -> None:
        with self.lock:
            self.products[sku]["price"] = price.quantize(Decimal("0.01"))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title} | Demo Gear Shop</title>{head}
<style>
 body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; color: #1f2328; }}
 .price, .price-now, #price {{ font-size: 2rem; font-weight: 700; }}
 .stock {{ color: #1a7f37; }} .stock.out {{ color: #cf222e; }}
 a {{ color: #0969da; }} footer {{ margin-top: 48px; color: #59636e; font-size: .9rem; }}
</style></head>
<body><p><a href="/">&larr; Demo Gear Shop</a></p>{body}
<footer>Shipping from $4.99. Free returns within 30 days.</footer></body></html>"""


def render_product(sku: str, p: dict) -> str:
    name, price, currency, in_stock = html.escape(p["name"]), p["price"], p["currency"], p["in_stock"]
    stock = '<p class="stock">In stock</p>' if in_stock else '<p class="stock out">Out of stock</p>'
    availability = "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock"
    head, body = "", ""

    if p["style"] == "json-ld":
        data = {"@context": "https://schema.org", "@type": "Product", "name": p["name"], "sku": sku,
                "offers": {"@type": "Offer", "price": str(price), "priceCurrency": currency,
                           "availability": availability}}
        head = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        body = f"<h1>{name}</h1><p class='price'>{us_format(price, currency)}</p>{stock}"
    elif p["style"] == "microdata":
        body = (f'<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">{name}</h1>'
                f'<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
                f'<meta itemprop="priceCurrency" content="{currency}">'
                f'<span class="price" itemprop="price" content="{price}">{us_format(price, currency)}</span>'
                f'<link itemprop="availability" href="{availability}">{stock}</div></div>')
    elif p["style"] == "opengraph":
        head = (f'<meta property="og:type" content="product"><meta property="og:title" content="{name}">'
                f'<meta property="product:price:amount" content="{price}">'
                f'<meta property="product:price:currency" content="{currency}">')
        body = f"<h1>{name}</h1><p class='price'>{us_format(price, currency)}</p>{stock}"
    elif p["style"] == "plain":
        # No structured data at all: the tracker needs a CSS selector for this one.
        was = eu_format(price * Decimal("1.2"), currency)
        body = (f"<h1>{name}</h1><p>Statt <s class='price-was'>{was}</s></p>"
                f"<p class='price-now'>{eu_format(price, currency)}</p>{stock}")
    elif p["style"] == "javascript":
        # The price isn't in the HTML; it's fetched and rendered client-side.
        body = (f"<h1>{name}</h1><div id='price'>Loading price…</div>{stock}"
                f"<script>fetch('/api/products/{sku}').then(r => r.json()).then(p => {{"
                f"const el = document.getElementById('price');"
                f"el.innerHTML = `<span itemprop=\"price\" content=\"${{p.price}}\">$${{p.price}}</span>"
                f"<meta itemprop=\"priceCurrency\" content=\"${{p.currency}}\">`; }});</script>")
    return PAGE.format(title=name, head=head, body=body)


def render_index(shop: Shop) -> str:
    rows = "".join(
        f"<li><a href='/products/{sku}'>{html.escape(p['name'])}</a>, {p['style']} markup</li>"
        for sku, p in shop.products.items()
    )
    body = (f"<h1>Demo Gear Shop</h1><p>A fake shop for price-tracker-scraper.</p><ul>{rows}</ul>"
            "<p>Drop a price: <code>/admin/drop?sku=espresso-machine&amp;percent=10</code><br>"
            "Recent requests and user agents: <a href='/admin/requests'>/admin/requests</a></p>")
    return PAGE.format(title="Home", head="", body=body)


def make_handler(shop: Shop):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DemoShop/1.0"

        def log_message(self, fmt, *args):  # keep test output quiet; /admin/requests has the log
            pass

        def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8") -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if status == 429:
                self.send_header("Retry-After", "5")
            self.end_headers()
            self.wfile.write(data)
            ua = self.headers.get("User-Agent", "")
            with shop.lock:
                shop.requests.appendleft({"time": datetime.now().isoformat(timespec="seconds"),
                                          "path": self.path, "status": status, "user_agent": ua})

        def _json(self, status: int, data) -> None:
            self._send(status, json.dumps(data, indent=2, default=str), "application/json")

        def do_GET(self):
            url = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            parts = [p for p in url.path.split("/") if p]
            ua = self.headers.get("User-Agent", "")

            if url.path == "/robots.txt":
                return self._send(200, ROBOTS_TXT, "text/plain")
            if url.path == "/":
                return self._send(200, render_index(shop))
            if parts[:1] == ["admin"]:
                return self._admin(parts[1:], query)

            if parts[:1] in (["products"], ["api"]):
                if "HeadlessChrome" in ua or not ua:
                    return self._send(403, "<h1>Access denied</h1><p>Automated browser detected.</p>")
                if parts[0] == "products" and random.random() < shop.block_rate:
                    return self._send(429, "<h1>Too many requests</h1><p>Please verify you are human.</p>")
            if len(parts) == 2 and parts[0] == "products" and parts[1] in shop.products:
                return self._send(200, render_product(parts[1], shop.products[parts[1]]))
            if len(parts) == 3 and parts[:2] == ["api", "products"] and parts[2] in shop.products:
                p = shop.products[parts[2]]
                return self._json(200, {"sku": parts[2], "price": str(p["price"]), "currency": p["currency"]})
            return self._send(404, "<h1>Not found</h1>")

        def _admin(self, parts: list[str], query: dict) -> None:
            action = parts[0] if parts else ""
            if action == "requests":
                with shop.lock:
                    return self._json(200, list(shop.requests))
            sku = query.get("sku")
            if action in ("set-price", "drop") and sku not in shop.products:
                return self._json(404, {"error": f"unknown sku {sku!r}", "skus": list(shop.products)})
            try:
                if action == "set-price":
                    shop.set_price(sku, Decimal(query["price"]))
                elif action == "drop":
                    percent = Decimal(query.get("percent", "10"))
                    shop.set_price(sku, shop.products[sku]["price"] * (1 - percent / 100))
                else:
                    return self._json(404, {"error": "try /admin/set-price, /admin/drop or /admin/requests"})
            except (KeyError, ArithmeticError):
                return self._json(400, {"error": "need numeric price= or percent="})
            p = shop.products[sku]
            return self._json(200, {"sku": sku, "price": str(p["price"]), "currency": p["currency"]})

    return Handler


def create_server(host: str = "127.0.0.1", port: int = 8080, block_rate: float = 0.0) -> ThreadingHTTPServer:
    shop = Shop(block_rate)
    server = ThreadingHTTPServer((host, port), make_handler(shop))
    server.shop = shop
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the demo shop.")
    parser.add_argument("--host", default=os.environ.get("DEMO_SHOP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DEMO_SHOP_PORT", "8080")))
    parser.add_argument("--block-rate", type=float, default=float(os.environ.get("DEMO_SHOP_BLOCK_RATE", "0.15")),
                        help="share of product requests answered with 429 (default 0.15)")
    args = parser.parse_args()
    server = create_server(args.host, args.port, args.block_rate)
    print(f"Demo shop on http://{args.host}:{args.port} (429 rate {args.block_rate:.0%})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

def render_template(data=None):
    if data is None:
        return None
    return data

def classify_intent(data=None):
    if data is None:
        return None
    return data

def check_health(data=None):
    if data is None:
        return None
    return data

def render_template(data=None):
    if data is None:
        return None
    return data

def classify_intent(data=None):
    if data is None:
        return None
    return data

def check_health(data=None):
    if data is None:
        return None
    return data