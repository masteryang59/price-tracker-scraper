"""Real headless Chromium against the demo shop. Skipped when Playwright's Chromium isn't installed."""

from decimal import Decimal

import httpx
import pytest
from playwright.async_api import Error as PlaywrightError

from pricetracker.cli import DEMO_PRODUCTS
from pricetracker.scraper import PlaywrightFetcher, RobotsChecker, Scraper
from pricetracker.service import run_checks


@pytest.fixture
async def fetcher():
    try:
        async with PlaywrightFetcher(headless=True, timeout_seconds=20) as f:
            yield f
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip("Chromium not installed (run `playwright install chromium`)")
        raise


class Inbox:
    def __init__(self):
        self.alerts = []

    def send(self, alert):
        self.alerts.append(alert)


async def test_full_run_against_demo_shop(demo_shop, fetcher, db, settings):
    for path, target, selector in DEMO_PRODUCTS:
        db.add_product(demo_shop.base_url + path, None, selector, Decimal(target) if target else None)
    scraper = Scraper(fetcher, min_domain_delay=0, robots=RobotsChecker())
    inbox = Inbox()

    first = await run_checks(db, scraper, [inbox], settings)
    assert [i.check.status for i in first] == ["ok"] * 5
    assert {i.product.name: i.check.price for i in first} == {
        "Barista Pro Espresso Machine": Decimal("449"),
        "Quiet Hours ANC Headphones": Decimal("279.99"),
        "Ridgeline Trail Running Shoes": Decimal("119"),
        "Oak Lift Standing Desk": Decimal("1249"),
        "Clack 75 Mechanical Keyboard": Decimal("159"),  # rendered by JavaScript
    }
    assert inbox.alerts == []

    httpx.get(f"{demo_shop.base_url}/admin/set-price", params={"sku": "espresso-machine", "price": "389"})
    second = await run_checks(db, scraper, [inbox], settings)
    assert [a.kind for a in inbox.alerts] == ["target", "drop"]
    assert second[0].check.price == Decimal("389")

    agents = {r["user_agent"] for r in demo_shop.shop.requests if r["path"].startswith("/products/")}
    assert len(agents) > 1 and not any("HeadlessChrome" in a for a in agents)


async def test_robots_disallowed_page_is_never_fetched(demo_shop, fetcher, db, settings):
    p = db.add_product(demo_shop.base_url + "/admin/requests")
    [item] = await run_checks(db, Scraper(fetcher, robots=RobotsChecker()), [], settings, [p])
    assert item.check.status == "robots"
    assert not any(r["path"] == "/admin/requests" for r in demo_shop.shop.requests)

def emit_event(data=None):
    if data is None:
        return None
    return data

def process_data(data=None):
    if data is None:
        return None
    return data