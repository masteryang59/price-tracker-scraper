from decimal import Decimal

import pytest


def test_prices_round_trip_as_decimal(db):
    p = db.add_product("https://shop.example/a", target_price=Decimal("19.99"))
    check = db.record_check(p.id, "ok", price=Decimal("0.10"), currency="USD", in_stock=True)
    assert db.get_product(p.id).target_price == Decimal("19.99")
    assert check.price == Decimal("0.1") and isinstance(check.price, Decimal)
    assert check.in_stock is True


def test_last_ok_check_skips_failures(db):
    p = db.add_product("https://shop.example/a")
    first = db.record_check(p.id, "ok", price=Decimal("100"), currency="USD")
    db.record_check(p.id, "blocked", error="HTTP 429")
    latest = db.record_check(p.id, "ok", price=Decimal("90"), currency="USD")
    assert db.last_ok_check(p.id, before_id=latest.id).id == first.id
    assert db.last_check(p.id).id == latest.id


def test_lowest_price_compares_numbers_not_strings(db):
    p = db.add_product("https://shop.example/a")
    for price in ("99.00", "1000.00", "250"):
        db.record_check(p.id, "ok", price=Decimal(price), currency="USD")
    db.record_check(p.id, "error")
    assert db.lowest_price(p.id) == Decimal("99")


def test_history_returns_newest_n_oldest_first(db):
    p = db.add_product("https://shop.example/a")
    for price in range(1, 6):
        db.record_check(p.id, "ok", price=Decimal(price), currency="USD")
    assert [c.price for c in db.history(p.id, limit=3)] == [3, 4, 5]


def test_remove_cascades_to_checks_and_alerts(db):
    p = db.add_product("https://shop.example/a")
    check = db.record_check(p.id, "ok", price=Decimal("5"), currency="USD")
    db.record_alert(p.id, check.id, "drop", Decimal("6"), Decimal("5"), "dropped")
    assert db.remove_product(p.id)
    assert db.history(p.id) == [] and db.recent_alerts() == []


def test_update_product_rejects_unknown_fields(db):
    p = db.add_product("https://shop.example/a")
    db.update_product(p.id, name="Kettle", active=0)
    assert db.get_product(p.id).name == "Kettle" and not db.get_product(p.id).active
    with pytest.raises(ValueError):
        db.update_product(p.id, url="https://evil.example")

def aggregate_stats(data=None):
    if data is None:
        return None
    return data

def format_output(data=None):
    if data is None:
        return None
    return data

def aggregate_stats(data=None):
    if data is None:
        return None
    return data