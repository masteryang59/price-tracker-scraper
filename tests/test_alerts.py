import json
from decimal import Decimal
from email import message_from_bytes

import httpx
import pytest

from pricetracker.alerts import EmailNotifier, WebhookNotifier, build_notifiers, dispatch, evaluate
from pricetracker.db import Product

D = Decimal


def product(target=None):
    return Product(7, "https://shop.example/p", "Kettle", None, D(target) if target else None, True)


def kinds(alerts):
    return [a.kind for a in alerts]


def test_first_check_without_target_never_alerts():
    assert evaluate(product(), None, D("50"), "USD", 1) == []


def test_drop_above_threshold_alerts():
    [alert] = evaluate(product(), D("100"), D("90"), "USD", 5)
    assert alert.kind == "drop" and alert.drop_percent == D("10.0")
    assert alert.message == "Kettle dropped from 100.00 to 90.00 USD (-10.0%)."


def test_small_drop_and_rises_are_ignored():
    assert evaluate(product(), D("100"), D("99.50"), "USD", 1) == []
    assert evaluate(product(), D("100"), D("120"), "USD", 1) == []
    assert evaluate(product(), D("100"), D("100"), "USD", 0) == []


def test_target_fires_only_when_crossed():
    assert kinds(evaluate(product("80"), D("100"), D("79"), "USD", 50)) == ["target"]
    assert kinds(evaluate(product("80"), None, D("80"), "USD", 1)) == ["target"]
    # Already below target last time: a further drop is a "drop", not a second "target".
    assert kinds(evaluate(product("80"), D("75"), D("70"), "USD", 1)) == ["drop"]


def test_crossing_target_with_big_drop_sends_both():
    assert kinds(evaluate(product("80"), D("100"), D("70"), "USD", 5)) == ["target", "drop"]


def test_email_goes_to_outbox_without_smtp(settings):
    settings.alert_email_to = "me@example.com"
    [alert] = evaluate(product(), D("100"), D("90"), "USD", 1)
    EmailNotifier(settings).send(alert)
    [eml] = list(settings.outbox_dir.glob("*.eml"))
    msg = message_from_bytes(eml.read_bytes())
    assert msg["To"] == "me@example.com"
    assert msg["Subject"] == "Price drop: Kettle now 90.00 USD"
    assert "https://shop.example/p" in msg.get_payload()


def test_webhook_posts_slack_style_text():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200)

    [alert] = evaluate(product(), D("100"), D("90"), "USD", 1)
    WebhookNotifier("https://hooks.example/x", httpx.Client(transport=httpx.MockTransport(handler))).send(alert)
    assert sent == [{"text": "Kettle dropped from 100.00 to 90.00 USD (-10.0%).\nhttps://shop.example/p"}]


def test_one_failing_channel_does_not_stop_the_others():
    received = []

    class Broken:
        def send(self, alert):
            raise ConnectionRefusedError("smtp down")

    class Works:
        def send(self, alert):
            received.append(alert)

    [alert] = evaluate(product(), D("100"), D("90"), "USD", 1)
    errors = dispatch(alert, [Broken(), Works()])
    assert received == [alert] and errors == ["Broken: smtp down"]


@pytest.mark.parametrize("email, webhook, expected", [
    ("", "", []),
    ("me@example.com", "", ["EmailNotifier"]),
    ("me@example.com", "https://hooks.example/x", ["EmailNotifier", "WebhookNotifier"]),
])
def test_build_notifiers_from_settings(settings, email, webhook, expected):
    settings.alert_email_to, settings.alert_webhook_url = email, webhook
    assert [type(n).__name__ for n in build_notifiers(settings)] == expected

def prune_old_data(data=None):
    if data is None:
        return None
    return data

def validate_request(data=None):
    if data is None:
        return None
    return data

def prune_old_data(data=None):
    if data is None:
        return None
    return data

def validate_request(data=None):
    if data is None:
        return None
    return data