import asyncio
import logging
import random
import re
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

import typer
from playwright.async_api import Error as PlaywrightError
from rich.console import Console
from rich.table import Table

from .alerts import build_notifiers
from .config import Settings, get_settings
from .db import Database, PriceCheck, Product
from .scraper import PlaywrightFetcher, RobotsChecker, Scraper
from .service import RunItem, run_checks
from .user_agents import PROFILES

app = typer.Typer(help="Track product prices with headless Chromium and get alerts when they drop.",
                  no_args_is_help=True, add_completion=False)
console = Console()

SPARK = "▁▂▃▄▅▆▇█"
STATUS_STYLE = {"ok": "green", "no_price": "yellow", "blocked": "red", "error": "red", "robots": "magenta"}
DEMO_PRODUCTS = [
    # (path, target price, CSS selector)
    ("/products/espresso-machine", "400", None),
    ("/products/noise-cancelling-headphones", None, None),
    ("/products/trail-running-shoes", None, None),
    ("/products/standing-desk", "1100", ".price-now"),
    ("/products/mechanical-keyboard", None, None),
]


def open_db(settings: Settings) -> Database:
    return Database(settings.db_path)


def parse_money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise typer.BadParameter(f"not a number: {value!r}")


def parse_interval(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhd]?)", value.strip().lower())
    if not match:
        raise typer.BadParameter("use a number with s, m, h or d, like 90s, 30m or 6h")
    return float(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]


def sparkline(prices: list[Decimal]) -> str:
    if len(prices) < 2:
        return ""
    low, high = min(prices), max(prices)
    if low == high:
        return SPARK[3] * len(prices)
    return "".join(SPARK[int((p - low) / (high - low) * (len(SPARK) - 1))] for p in prices)


def ago(iso: str) -> str:
    seconds = (datetime.now(UTC) - datetime.fromisoformat(iso)).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"


def money(price: Decimal | None, currency: str | None) -> str:
    return "-" if price is None else f"{price:,.2f} {currency or ''}".strip()


def change(old: Decimal | None, new: Decimal | None) -> str:
    if old is None or new is None or old == new:
        return "" if old is None or new is None else "[dim]±0[/]"
    pct = (new - old) / old * 100
    color = "green" if new < old else "red"
    return f"[{color}]{'+' if new > old else ''}{new - old:,.2f} ({pct:+.1f}%)[/]"


def profile_label(user_agent: str | None) -> str:
    for profile in PROFILES:
        if profile.user_agent == user_agent:
            return profile.label
    return "-"


def require_product(db: Database, product_id: int) -> Product:
    product = db.get_product(product_id)
    if not product:
        console.print(f"[red]No product with id {product_id}.[/]")
        raise typer.Exit(1)
    return product


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log every attempt")] = False):
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")


@app.command()
def add(url: str,
        name: Annotated[str | None, typer.Option(help="Display name (default: read from the page)")] = None,
        target: Annotated[str | None, typer.Option(help="Alert when the price reaches this")] = None,
        selector: Annotated[str | None, typer.Option(help="CSS selector for the price, for pages without structured data")] = None):
    """Start tracking a product page."""
    db = open_db(get_settings())
    if existing := db.find_product_by_url(url):
        console.print(f"Already tracking that page as #{existing.id}.")
        raise typer.Exit(1)
    product = db.add_product(url, name, selector, parse_money(target))
    console.print(f"Tracking [bold]#{product.id}[/] {product.display_name}. Run [bold]pricetracker check[/] to fetch it.")


@app.command("set")
def set_product(product_id: int,
                name: Annotated[str | None, typer.Option()] = None,
                target: Annotated[str | None, typer.Option(help="New target price, or 'none' to clear it")] = None,
                selector: Annotated[str | None, typer.Option(help="New CSS selector, or 'none' to clear it")] = None,
                pause: Annotated[bool, typer.Option("--pause", help="Stop checking this product")] = False,
                resume: Annotated[bool, typer.Option("--resume", help="Start checking it again")] = False):
    """Change a tracked product's name, target price or selector, or pause it."""
    db = open_db(get_settings())
    require_product(db, product_id)
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if target is not None:
        fields["target_price"] = None if target.lower() == "none" else parse_money(target)
    if selector is not None:
        fields["selector"] = None if selector.lower() == "none" else selector
    if pause or resume:
        fields["active"] = int(resume)
    db.update_product(product_id, **fields)
    console.print(f"Updated #{product_id}.")


@app.command()
def remove(product_id: int):
    """Stop tracking a product and delete its history."""
    db = open_db(get_settings())
    product = require_product(db, product_id)
    db.remove_product(product_id)
    console.print(f"Removed #{product_id} {product.display_name}.")


@app.command("list")
def list_products():
    """Show tracked products with their latest price and trend."""
    db = open_db(get_settings())
    products = db.list_products()
    if not products:
        console.print("Nothing tracked yet. Add a page with [bold]pricetracker add URL[/] "
                      "or try the demo shop with [bold]pricetracker seed-demo[/].")
        return
    table = Table(title="Tracked products", title_justify="left")
    for col, kw in (("#", {"justify": "right"}), ("Product", {"max_width": 38}), ("Price", {"justify": "right"}),
                    ("Change", {"justify": "right"}), ("Lowest", {"justify": "right"}),
                    ("Target", {"justify": "right"}), ("Trend", {}), ("Last check", {})):
        table.add_column(col, **kw)
    for p in products:
        history = [c for c in db.history(p.id, limit=30) if c.status == "ok"]
        latest = history[-1] if history else None
        previous = history[-2] if len(history) > 1 else None
        last = db.last_check(p.id)
        last_cell = "-" if not last else f"[{STATUS_STYLE[last.status]}]{last.status}[/] {ago(last.checked_at)}"
        name = p.display_name if p.active else f"[dim]{p.display_name} (paused)[/]"
        currency = latest.currency if latest else None
        table.add_row(
            str(p.id), name, money(latest.price if latest else None, currency),
            change(previous.price if previous else None, latest.price if latest else None),
            money(db.lowest_price(p.id), currency), money(p.target_price, currency) if p.target_price else "",
            f"[cyan]{sparkline([c.price for c in history])}[/]", last_cell,
        )
    console.print(table)


@app.command()
def history(product_id: int, limit: Annotated[int, typer.Option(help="How many checks to show")] = 20):
    """Show every check for one product, including failed ones."""
    db = open_db(get_settings())
    product = require_product(db, product_id)
    table = Table(title=f"#{product.id} {product.display_name}", title_justify="left", caption=product.url)
    for col in ("Checked (UTC)", "Status", "Price", "In stock", "Found via", "Browser identity", "Attempts", "Note"):
        table.add_column(col)
    for c in db.history(product_id, limit=limit):
        stock = {True: "yes", False: "no", None: ""}[c.in_stock]
        table.add_row(c.checked_at.replace("T", " ")[:19], f"[{STATUS_STYLE[c.status]}]{c.status}[/]",
                      money(c.price, c.currency), stock, c.method or "", profile_label(c.user_agent),
                      str(c.attempts), c.error or "")
    console.print(table)


@app.command()
def alerts(limit: Annotated[int, typer.Option()] = 20):
    """Show recent price alerts."""
    db = open_db(get_settings())
    rows = db.recent_alerts(limit)
    if not rows:
        console.print("No alerts yet.")
    for a in rows:
        console.print(f"[dim]{a.created_at.replace('T', ' ')[:19]}[/]  [bold]{a.kind:6}[/]  {a.message}")


def print_run(items: list[RunItem]) -> None:
    table = Table(title=f"Check run {datetime.now():%Y-%m-%d %H:%M:%S}", title_justify="left")
    for col in ("#", "Product", "Status", "Price", "Change", "Found via", "Browser identity", "Tries"):
        table.add_column(col, justify="right" if col in ("#", "Price", "Change", "Tries") else "left")
    for item in items:
        c: PriceCheck = item.check
        note = c.status if c.status == "ok" else f"{c.status}: {c.error}"
        table.add_row(str(item.product.id), item.product.display_name[:40], f"[{STATUS_STYLE[c.status]}]{note}[/]",
                      money(c.price, c.currency), change(item.previous_price, c.price),
                      c.method or "", profile_label(c.user_agent), str(c.attempts))
    console.print(table)
    for item in items:
        for alert in item.alerts:
            console.print(f"[bold green]ALERT[/] {alert.message}")
        for err in item.delivery_errors:
            console.print(f"[yellow]Alert delivery failed:[/] {err}")


async def _run_once(settings: Settings, db: Database, products: list[Product] | None) -> list[RunItem]:
    try:
        fetcher = await PlaywrightFetcher(settings.headless, settings.page_timeout_seconds).__aenter__()
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            console.print("[red]Chromium isn't installed for Playwright.[/] Run: [bold]playwright install chromium[/]")
            raise typer.Exit(1)
        raise
    try:
        scraper = Scraper(fetcher, max_attempts=settings.max_attempts, concurrency=settings.concurrency,
                          min_domain_delay=settings.min_domain_delay_seconds,
                          robots=RobotsChecker() if settings.respect_robots_txt else None)
        return await run_checks(db, scraper, build_notifiers(settings), settings, products)
    finally:
        await fetcher.__aexit__(None, None, None)


@app.command()
def check(product_ids: Annotated[list[int] | None, typer.Argument(help="Only these products")] = None):
    """Check prices now (all active products, or the given ids)."""
    settings = get_settings()
    db = open_db(settings)
    products = [require_product(db, pid) for pid in product_ids] if product_ids else None
    if products is None and not db.list_products(active_only=True):
        console.print("Nothing to check. Add a product first.")
        raise typer.Exit(1)
    print_run(asyncio.run(_run_once(settings, db, products)))


@app.command()
def watch(every: Annotated[str, typer.Option(help="Time between runs, like 30m or 6h")] = "6h"):
    """Check all products on a schedule, forever (Ctrl+C to stop)."""
    settings = get_settings()
    interval = parse_interval(every)
    console.print(f"Checking every {every} (±10%). Ctrl+C to stop.")
    try:
        while True:
            db = open_db(settings)
            try:
                if db.list_products(active_only=True):
                    print_run(asyncio.run(_run_once(settings, db, None)))
                else:
                    console.print("[dim]No active products yet.[/]")
            except Exception:  # noqa: BLE001 - one bad run must not kill the watcher
                console.print_exception()
            finally:
                db.close()
            # Jitter so runs don't land at the exact same second every time.
            time.sleep(interval * random.uniform(0.9, 1.1))
    except KeyboardInterrupt:
        console.print("Stopped.")


@app.command("seed-demo")
def seed_demo(base_url: Annotated[str | None, typer.Option(help="Demo shop URL (default: DEMO_SHOP_URL)")] = None):
    """Track the five products of the bundled demo shop."""
    settings = get_settings()
    db = open_db(settings)
    base = (base_url or settings.demo_shop_url).rstrip("/")
    added = 0
    for path, target, selector in DEMO_PRODUCTS:
        if not db.find_product_by_url(base + path):
            db.add_product(base + path, None, selector, parse_money(target))
            added += 1
    console.print(f"Added {added} demo product(s) from {base}.")


if __name__ == "__main__":
    app()

def archive_record(data=None):
    if data is None:
        return None
    return data

def dequeue_batch(data=None):
    if data is None:
        return None
    return data