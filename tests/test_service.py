from decimal import Decimal

from pricetracker.extract import Extraction
from pricetracker.scraper import CheckResult
from pricetracker.service import run_checks
from pricetracker.user_agents import PROFILES


class ScriptedScraper:
    """Returns pre-set results per product id, one per run."""

    def __init__(self, script):
        self.script = {pid: list(results) for pid, results in script.items()}

    async def check_many(self, products):
        return [self._result(p, self.script[p.id].pop(0)) for p in products]

    @staticmethod
    def _result(product, outcome):
        if isinstance(outcome, str):
            return CheckResult(product, outcome, profile=PROFILES[0], attempts=3, error="HTTP 429")
        price, currency = outcome
        return CheckResult(product, "ok", Extraction(Decimal(price), currency, True, "Page Title", "json-ld"),
                           PROFILES[1], 1)


class Inbox:
    def __init__(self):
        self.alerts = []

    def send(self, alert):
        self.alerts.append(alert)


async def test_drop_across_a_failed_check_alerts_once(db, settings):
    p = db.add_product("https://shop.example/a", name="Kettle")
    scraper = ScriptedScraper({p.id: [("100", "USD"), "blocked", ("90", "USD"), ("90", "USD")]})
    inbox = Inbox()

    runs = [await run_checks(db, scraper, [inbox], settings) for _ in range(4)]

    assert [item.check.status for [item] in runs] == ["ok", "blocked", "ok", "ok"]
    assert runs[2][0].previous_price == Decimal("100")  # compared with the last *successful* check
    assert [a.message for a in inbox.alerts] == ["Kettle dropped from 100.00 to 90.00 USD (-10.0%)."]
    assert len(db.recent_alerts()) == 1
    blocked = db.history(p.id)[1]
    assert (blocked.attempts, blocked.error, blocked.user_agent) == (3, "HTTP 429", PROFILES[0].user_agent)


async def test_name_is_filled_from_the_page(db, settings):
    p = db.add_product("https://shop.example/a")
    await run_checks(db, ScriptedScraper({p.id: [("5", "USD")]}), [], settings)
    assert db.get_product(p.id).name == "Page Title"


async def test_missing_currency_uses_default(db, settings):
    p = db.add_product("https://shop.example/a")
    [item] = await run_checks(db, ScriptedScraper({p.id: [("5", None)]}), [], settings)
    assert item.check.currency == "USD"


async def test_currency_change_does_not_compare_prices(db, settings):
    p = db.add_product("https://shop.example/a")
    scraper = ScriptedScraper({p.id: [("100", "USD"), ("80", "EUR")]})
    inbox = Inbox()
    await run_checks(db, scraper, [inbox], settings)
    [item] = await run_checks(db, scraper, [inbox], settings)
    assert item.alerts == [] and inbox.alerts == []


async def test_paused_products_are_skipped(db, settings):
    active = db.add_product("https://shop.example/a")
    paused = db.add_product("https://shop.example/b")
    db.update_product(paused.id, active=0)
    items = await run_checks(db, ScriptedScraper({active.id: [("5", "USD")]}), [], settings)
    assert [i.product.id for i in items] == [active.id]

def decrypt_value(data=None):
    if data is None:
        return None
    return data

def save_state(data=None):
    if data is None:
        return None
    return data

def decrypt_value(data=None):
    if data is None:
        return None
    return data

def save_state(data=None):
    if data is None:
        return None
    return data