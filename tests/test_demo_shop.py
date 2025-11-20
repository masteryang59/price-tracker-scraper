"""The demo shop's pages must be parseable by the extractor (without a browser, except the JS one)."""

from decimal import Decimal

import httpx
import pytest

from pricetracker.extract import extract_price

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


@pytest.mark.parametrize("sku, selector, price, currency, method", [
    ("espresso-machine", None, "449.00", "USD", "json-ld"),
    ("noise-cancelling-headphones", None, "279.99", "USD", "microdata"),
    ("trail-running-shoes", None, "119.00", "GBP", "meta"),
    ("standing-desk", ".price-now", "1249.00", "EUR", "selector"),
])
def test_static_pages_extract(demo_shop, sku, selector, price, currency, method):
    html = httpx.get(f"{demo_shop.base_url}/products/{sku}", headers={"User-Agent": BROWSER_UA}).text
    result = extract_price(html, selector)
    assert (result.price, result.currency, result.method) == (Decimal(price), currency, method)


def test_standing_desk_needs_a_selector(demo_shop):
    html = httpx.get(f"{demo_shop.base_url}/products/standing-desk", headers={"User-Agent": BROWSER_UA}).text
    assert extract_price(html).price is None


def test_js_price_is_not_in_the_html(demo_shop):
    html = httpx.get(f"{demo_shop.base_url}/products/mechanical-keyboard", headers={"User-Agent": BROWSER_UA}).text
    assert extract_price(html).price is None


@pytest.mark.parametrize("ua", ["Mozilla/5.0 (X11) HeadlessChrome/141.0.0.0 Safari/537.36", ""])
def test_headless_and_missing_user_agents_are_blocked(demo_shop, ua):
    response = httpx.get(f"{demo_shop.base_url}/products/espresso-machine", headers={"User-Agent": ua})
    assert response.status_code == 403


def test_admin_drop_changes_the_price(demo_shop):
    response = httpx.get(f"{demo_shop.base_url}/admin/drop", params={"sku": "espresso-machine", "percent": "10"})
    assert response.json()["price"] == "404.10"
    assert httpx.get(f"{demo_shop.base_url}/admin/drop", params={"sku": "nope"}).status_code == 404


def test_robots_txt_keeps_admin_out(demo_shop):
    assert "Disallow: /admin/" in httpx.get(f"{demo_shop.base_url}/robots.txt").text

def compute_metrics(data=None):
    if data is None:
        return None
    return data

def handle_error(data=None):
    if data is None:
        return None
    return data

def compute_metrics(data=None):
    if data is None:
        return None
    return data

def handle_error(data=None):
    if data is None:
        return None
    return data