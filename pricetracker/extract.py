"""Find the price on a product page.

Strategies, most reliable first:
1. a CSS selector saved with the product (for sites with no structured data)
2. schema.org JSON-LD (`<script type="application/ld+json">`), which most shops emit for Google
3. schema.org microdata (`itemprop="price"`)
4. Open Graph / Facebook product meta tags (`product:price:amount`)

There is deliberately no "find anything that looks like a price" fallback: on a
real page that picks up the shipping cost or a related product, and a wrong
price is worse than none because it fires false alerts.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup, Tag

CURRENCY_SYMBOLS = {
    "$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR",
    "C$": "CAD", "CA$": "CAD", "A$": "AUD", "AU$": "AUD", "CHF": "CHF", "zł": "PLN", "₺": "TRY",
}
ISO_CODE = re.compile(r"\b([A-Z]{3})\b")
NUMBER = re.compile(r"\d[\d.,'\s  ]*")


@dataclass(frozen=True)
class Extraction:
    price: Decimal | None
    currency: str | None
    in_stock: bool | None
    title: str | None
    method: str | None  # which strategy found the price


def parse_price(text: str | None) -> Decimal | None:
    """Parse a price string in US or European notation.

    "$1,299.99" -> 1299.99, "1.299,99 €" -> 1299.99, "1 299,50" -> 1299.50, "12,5" -> 12.5.
    A lone separator followed by exactly three digits ("1,299" or "1.299") is read
    as a thousands separator, which is how shops almost always mean it.
    """
    if not text:
        return None
    match = NUMBER.search(str(text))
    if not match:
        return None
    raw = re.sub(r"[\s  ']", "", match.group()).rstrip(".,")

    last_dot, last_comma = raw.rfind("."), raw.rfind(",")
    if last_dot != -1 and last_comma != -1:
        decimal_sep = "." if last_dot > last_comma else ","
    elif last_dot != -1 or last_comma != -1:
        sep = "." if last_dot != -1 else ","
        decimals = len(raw) - raw.rfind(sep) - 1
        decimal_sep = sep if raw.count(sep) == 1 and decimals != 3 else None
    else:
        decimal_sep = None

    if decimal_sep:
        whole, _, frac = raw.rpartition(decimal_sep)
        normalized = re.sub(r"[.,]", "", whole) + "." + frac
    else:
        normalized = re.sub(r"[.,]", "", raw)
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def detect_currency(text: str | None) -> str | None:
    if not text:
        return None
    if code := ISO_CODE.search(text):
        return code.group(1)
    # Longest symbols first so "C$" wins over "$".
    for symbol in sorted(CURRENCY_SYMBOLS, key=len, reverse=True):
        if symbol in text:
            return CURRENCY_SYMBOLS[symbol]
    return None


def _availability(value) -> bool | None:
    if not value:
        return None
    value = str(value).lower()
    if any(word in value for word in ("outofstock", "soldout", "discontinued", "out of stock")):
        return False
    if any(word in value for word in ("instock", "in stock", "limitedavailability", "onlineonly", "preorder")):
        return True
    return None


def _text_or_content(el: Tag) -> str:
    return el.get("content") or el.get("value") or el.get_text(" ", strip=True)


def _from_selector(soup: BeautifulSoup, selector: str):
    el = soup.select_one(selector)
    if el is None:
        return None
    text = _text_or_content(el)
    price = parse_price(text)
    return (price, detect_currency(text), None) if price is not None else None


def _walk_json_ld(node):
    """Yield every dict in a JSON-LD document, including inside @graph and lists."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_json_ld(item)
    elif isinstance(node, dict):
        yield node
        for value in node.values():
            if isinstance(value, (list, dict)):
                yield from _walk_json_ld(value)


def _is_type(node: dict, name: str) -> bool:
    types = node.get("@type")
    types = types if isinstance(types, list) else [types]
    return name in types


def _from_json_ld(soup: BeautifulSoup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in _walk_json_ld(data):
            if not (_is_type(node, "Product") or _is_type(node, "ProductGroup")):
                continue
            offers = node.get("offers")
            offers = offers if isinstance(offers, list) else [offers]
            for offer in filter(None, offers):
                if not isinstance(offer, dict):
                    continue
                # AggregateOffer (several sellers or variants) has lowPrice instead of price.
                raw = offer.get("price", offer.get("lowPrice"))
                spec = offer.get("priceSpecification")
                if raw is None and isinstance(spec, dict):
                    raw = spec.get("price")
                price = parse_price(str(raw)) if raw is not None else None
                if price is not None:
                    return price, offer.get("priceCurrency"), _availability(offer.get("availability")), node.get("name")
    return None


def _from_microdata(soup: BeautifulSoup):
    el = soup.select_one('[itemprop="price"]')
    if el is None:
        return None
    price = parse_price(_text_or_content(el))
    if price is None:
        return None
    currency_el = soup.select_one('[itemprop="priceCurrency"]')
    currency = _text_or_content(currency_el) if currency_el else detect_currency(el.get_text())
    avail_el = soup.select_one('[itemprop="availability"]')
    in_stock = _availability(avail_el.get("href") or _text_or_content(avail_el)) if avail_el else None
    return price, currency, in_stock


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        el = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if el and el.get("content"):
            return el["content"]
    return None


def _from_meta(soup: BeautifulSoup):
    price = parse_price(_meta(soup, "product:price:amount", "og:price:amount"))
    if price is None:
        return None
    currency = _meta(soup, "product:price:currency", "og:price:currency")
    return price, currency, _availability(_meta(soup, "product:availability", "og:availability"))


def _title(soup: BeautifulSoup) -> str | None:
    if title := _meta(soup, "og:title"):
        return title.strip()
    if h1 := soup.find("h1"):
        return h1.get_text(" ", strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


def extract_price(html: str, selector: str | None = None) -> Extraction:
    soup = BeautifulSoup(html, "html.parser")
    found, method, name = None, None, None

    if selector:
        found, method = _from_selector(soup, selector), "selector"
    if not found and (ld := _from_json_ld(soup)):
        *found, name = ld
        method = "json-ld"
    if not found:
        found, method = _from_microdata(soup), "microdata"
    if not found:
        found, method = _from_meta(soup), "meta"

    title = name or _title(soup)
    if not found:
        return Extraction(None, None, None, title, None)
    price, currency, in_stock = found
    return Extraction(price, (currency or "").upper() or None, in_stock, title, method)

def promote_user(data=None):
    if data is None:
        return None
    return data

def trace_request(data=None):
    if data is None:
        return None
    return data

def promote_user(data=None):
    if data is None:
        return None
    return data