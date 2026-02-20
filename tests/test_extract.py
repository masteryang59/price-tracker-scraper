import json
from decimal import Decimal

import pytest

from pricetracker.extract import detect_currency, extract_price, parse_price


@pytest.mark.parametrize("text, expected", [
    ("$1,299.99", "1299.99"),
    ("1.299,99 €", "1299.99"),
    ("1 299,50 zł", "1299.50"),
    ("1 299,50", "1299.50"),
    ("CHF 1'299.00", "1299.00"),
    ("€12,5", "12.5"),
    ("£119", "119"),
    ("1,299", "1299"),          # lone separator + 3 digits = thousands
    ("1.299", "1299"),
    ("1,234,567.89", "1234567.89"),
    ("Now only 45.00!", "45.00"),
    ("0.99", "0.99"),
    ("449.00", "449.00"),
])
def test_parse_price(text, expected):
    assert parse_price(text) == Decimal(expected)


@pytest.mark.parametrize("text", [None, "", "Sold out", "Call for price"])
def test_parse_price_without_a_number(text):
    assert parse_price(text) is None


@pytest.mark.parametrize("text, expected", [
    ("$10", "USD"), ("C$10", "CAD"), ("10 €", "EUR"), ("£5", "GBP"), ("USD 10", "USD"), ("10", None),
])
def test_detect_currency(text, expected):
    assert detect_currency(text) == expected


def page(head="", body=""):
    return f"<html><head>{head}</head><body>{body}<footer>Shipping from $4.99</footer></body></html>"


def ld(data):
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def test_json_ld_product():
    html = page(ld({"@context": "https://schema.org", "@type": "Product", "name": "Espresso Machine",
                    "offers": {"@type": "Offer", "price": "449.00", "priceCurrency": "USD",
                               "availability": "https://schema.org/InStock"}}))
    result = extract_price(html)
    assert (result.price, result.currency, result.in_stock, result.title, result.method) == \
           (Decimal("449.00"), "USD", True, "Espresso Machine", "json-ld")


def test_json_ld_in_graph_with_aggregate_offer_and_type_list():
    html = page(ld({"@graph": [
        {"@type": "WebSite", "name": "Shop"},
        {"@type": ["Product", "Thing"], "name": "Kettle",
         "offers": [{"@type": "AggregateOffer", "lowPrice": 59.5, "priceCurrency": "eur",
                     "availability": "OutOfStock"}]},
    ]}))
    result = extract_price(html)
    assert (result.price, result.currency, result.in_stock) == (Decimal("59.5"), "EUR", False)


def test_broken_json_ld_falls_through_to_next_strategy():
    html = page('<script type="application/ld+json">{not json</script>'
                '<meta property="product:price:amount" content="19.99">')
    result = extract_price(html)
    assert (result.price, result.method) == (Decimal("19.99"), "meta")


def test_microdata():
    html = page(body='<h1>Headphones</h1><meta itemprop="priceCurrency" content="USD">'
                     '<span itemprop="price" content="279.99">$279.99</span>'
                     '<link itemprop="availability" href="https://schema.org/InStock">')
    result = extract_price(html)
    assert (result.price, result.currency, result.in_stock, result.title, result.method) == \
           (Decimal("279.99"), "USD", True, "Headphones", "microdata")


def test_open_graph_meta():
    html = page(head='<meta property="og:title" content="Trail Shoes">'
                     '<meta property="product:price:amount" content="119.00">'
                     '<meta property="product:price:currency" content="GBP">')
    result = extract_price(html)
    assert (result.price, result.currency, result.title, result.method) == \
           (Decimal("119.00"), "GBP", "Trail Shoes", "meta")


def test_selector_wins_over_structured_data():
    html = page(ld({"@type": "Product", "offers": {"price": "999"}}),
                '<s class="was">1.498,80 €</s><p class="now">1.249,00 €</p>')
    result = extract_price(html, selector=".now")
    assert (result.price, result.currency, result.method) == (Decimal("1249.00"), "EUR", "selector")


def test_selector_that_matches_nothing_falls_back():
    html = page(ld({"@type": "Product", "offers": {"price": "10", "priceCurrency": "USD"}}))
    assert extract_price(html, selector=".gone").method == "json-ld"


def test_no_structured_data_means_no_price():
    # The footer's "$4.99" shipping cost must not be mistaken for the product price.
    result = extract_price(page(body="<h1>Standing Desk</h1><p class='price-now'>1.249,00 €</p>"))
    assert result.price is None
    assert result.title == "Standing Desk"

def subscribe_topic(data=None):
    if data is None:
        return None
    return data

def check_status(data=None):
    if data is None:
        return None
    return data

def subscribe_topic(data=None):
    if data is None:
        return None
    return data

def check_status(data=None):
    if data is None:
        return None
    return data