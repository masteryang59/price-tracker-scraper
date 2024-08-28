"""Decide when a price change is worth an alert, and deliver it.

Two rules, checked against the previous *successful* check (a failed scrape in
between never counts as a price change):
- drop:   the price fell by at least MIN_DROP_PERCENT
- target: the price reached the product's target price, and wasn't there before

Both rules fire on the change, not on the state, so a price that stays low
doesn't send the same alert on every run.
"""

import json
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

import httpx

from .config import Settings
from .db import Product

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceAlert:
    product: Product
    kind: str  # drop | target
    old_price: Decimal | None
    new_price: Decimal
    currency: str

    @property
    def drop_percent(self) -> Decimal | None:
        if not self.old_price:
            return None
        return ((self.old_price - self.new_price) / self.old_price * 100).quantize(Decimal("0.1"))

    @property
    def message(self) -> str:
        name = self.product.display_name
        new = f"{self.new_price:,.2f} {self.currency}"
        if self.kind == "target":
            return f"{name} is now {new}, at or below your target of {self.product.target_price:,.2f}."
        return f"{name} dropped from {self.old_price:,.2f} to {new} (-{self.drop_percent}%)."


def evaluate(product: Product, previous: Decimal | None, current: Decimal, currency: str,
             min_drop_percent: float) -> list[PriceAlert]:
    alerts = []
    target = product.target_price
    if target is not None and current <= target and (previous is None or previous > target):
        alerts.append(PriceAlert(product, "target", previous, current, currency))
    if previous is not None and current < previous:
        drop = (previous - current) / previous * 100
        if drop >= Decimal(str(min_drop_percent)):
            alerts.append(PriceAlert(product, "drop", previous, current, currency))
    return alerts


class Notifier(Protocol):
    def send(self, alert: PriceAlert) -> None: ...


class EmailNotifier:
    """Sends over SMTP, or writes .eml files to the outbox when no SMTP host is set."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def build(self, alert: PriceAlert) -> EmailMessage:
        s = self.settings
        msg = EmailMessage()
        label = "Target price reached" if alert.kind == "target" else "Price drop"
        msg["Subject"] = f"{label}: {alert.product.display_name} now {alert.new_price:,.2f} {alert.currency}"
        msg["From"] = s.from_email
        msg["To"] = s.alert_email_to
        msg.set_content(f"{alert.message}\n\n{alert.product.url}\n")
        return msg

    def send(self, alert: PriceAlert) -> None:
        s = self.settings
        msg = self.build(alert)
        if not s.smtp_host:
            s.outbox_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            path = Path(s.outbox_dir) / f"{stamp}-product{alert.product.id}-{alert.kind}.eml"
            path.write_bytes(bytes(msg))
            log.info("SMTP_HOST not set, wrote alert email to %s", path)
            return
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)


class WebhookNotifier:
    """Posts `{"text": ...}`, the payload Slack incoming webhooks (and many others) accept."""

    def __init__(self, url: str, client: httpx.Client | None = None):
        self.url = url
        self.client = client or httpx.Client(timeout=10)

    def send(self, alert: PriceAlert) -> None:
        text = f"{alert.message}\n{alert.product.url}"
        self.client.post(self.url, content=json.dumps({"text": text}),
                         headers={"Content-Type": "application/json"}).raise_for_status()


def build_notifiers(settings: Settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if settings.alert_email_to:
        notifiers.append(EmailNotifier(settings))
    if settings.alert_webhook_url:
        notifiers.append(WebhookNotifier(settings.alert_webhook_url))
    return notifiers


def dispatch(alert: PriceAlert, notifiers: list[Notifier]) -> list[str]:
    """Send through every notifier. One channel failing doesn't stop the others; errors are returned."""
    errors = []
    for notifier in notifiers:
        try:
            notifier.send(alert)
        except Exception as exc:  # noqa: BLE001 - a broken channel must not stop the run
            log.warning("%s failed: %s", type(notifier).__name__, exc)
            errors.append(f"{type(notifier).__name__}: {exc}")
    return errors

def cancel_job(data=None):
    if data is None:
        return None
    return data

def queue_message(data=None):
    if data is None:
        return None
    return data

def cancel_job(data=None):
    if data is None:
        return None
    return data

def queue_message(data=None):
    if data is None:
        return None
    return data