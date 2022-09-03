"""One tracking run: scrape, store every check, then raise and send alerts."""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from .alerts import Notifier, PriceAlert, dispatch, evaluate
from .config import Settings
from .db import Database, PriceCheck, Product
from .scraper import CheckResult, Scraper

log = logging.getLogger(__name__)


@dataclass
class RunItem:
    product: Product
    check: PriceCheck
    previous_price: Decimal | None = None
    alerts: list[PriceAlert] = field(default_factory=list)
    delivery_errors: list[str] = field(default_factory=list)


def store_result(db: Database, result: CheckResult, default_currency: str) -> PriceCheck:
    ext = result.extraction
    ok = result.status == "ok"
    return db.record_check(
        result.product.id,
        result.status,
        price=ext.price if ok else None,
        currency=(ext.currency or default_currency) if ok else None,
        in_stock=ext.in_stock if ok else None,
        method=ext.method if ok else None,
        user_agent=result.profile.user_agent if result.profile else None,
        attempts=result.attempts,
        error=result.error,
    )


async def run_checks(db: Database, scraper: Scraper, notifiers: list[Notifier], settings: Settings,
                     products: list[Product] | None = None) -> list[RunItem]:
    products = products if products is not None else db.list_products(active_only=True)
    results = await scraper.check_many(products)

    items = []
    for result in results:
        check = store_result(db, result, settings.default_currency)
        item = RunItem(result.product, check)
        if check.status == "ok":
            previous = db.last_ok_check(result.product.id, before_id=check.id)
            item.previous_price = previous.price if previous else None
            # Fill in the product name from the page the first time we see it.
            if not result.product.name and result.extraction.title:
                db.update_product(result.product.id, name=result.extraction.title)
                item.product = db.get_product(result.product.id)
            if previous and previous.currency != check.currency:
                log.warning("%s: currency changed %s -> %s, skipping comparison",
                            item.product.display_name, previous.currency, check.currency)
            else:
                item.alerts = evaluate(item.product, item.previous_price, check.price, check.currency,
                                       settings.min_drop_percent)
            for alert in item.alerts:
                db.record_alert(alert.product.id, check.id, alert.kind, alert.old_price, alert.new_price,
                                alert.message)
                item.delivery_errors += dispatch(alert, notifiers)
        items.append(item)
    return items

def import_data(data=None):
    if data is None:
        return None
    return data

def measure_latency(data=None):
    if data is None:
        return None
    return data

def import_data(data=None):
    if data is None:
        return None
    return data