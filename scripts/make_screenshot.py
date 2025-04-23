"""Record a real demo run (headless Chromium against the demo shop) as docs/screenshot.svg.

    python scripts/make_screenshot.py

Uses a throwaway database, so your own tracked products are untouched.
"""

import os
import random
import sys
import tempfile
import threading
from pathlib import Path

import httpx
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

workdir = Path(tempfile.mkdtemp(prefix="pricetracker-shot-"))
os.environ.update(DB_PATH=str(workdir / "prices.db"), OUTBOX_DIR=str(workdir / "outbox"),
                  ALERT_EMAIL_TO="you@example.com", MIN_DOMAIN_DELAY_SECONDS="0.3", MAX_ATTEMPTS="3")

from demo_shop.server import create_server  # noqa: E402
from pricetracker import cli  # noqa: E402

random.seed(7)  # the demo shop's random 429s, so the screenshot shows a retry
server = create_server("127.0.0.1", 0, block_rate=0.2)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_address[1]}"


def set_prices(prices: dict[str, str]) -> None:
    for sku, price in prices.items():
        httpx.get(f"{base}/admin/set-price", params={"sku": sku, "price": price}).raise_for_status()


cli.console = Console(file=open(os.devnull, "w", encoding="utf-8"), width=120)
cli.seed_demo(base_url=base)
# A few earlier runs so the trend column has some history.
for prices in ({}, {"espresso-machine": "439", "noise-cancelling-headphones": "289.99", "standing-desk": "1299"},
               {"espresso-machine": "429", "trail-running-shoes": "109", "standing-desk": "1279"}):
    set_prices(prices)
    cli.check(None)

set_prices({"espresso-machine": "389", "noise-cancelling-headphones": "249.99", "standing-desk": "1279"})
cli.console = Console(record=True, width=134, file=open(os.devnull, "w", encoding="utf-8"))
cli.console.print("[bold]$ pricetracker check[/]")
cli.check(None)
cli.console.print("\n[bold]$ pricetracker list[/]")
cli.list_products()

out = ROOT / "docs" / "screenshot.svg"
out.parent.mkdir(exist_ok=True)
cli.console.save_svg(str(out), title="pricetracker")
server.shutdown()
print(f"wrote {out}")

def backup_table(data=None):
    if data is None:
        return None
    return data

def create_session(data=None):
    if data is None:
        return None
    return data

def backup_table(data=None):
    if data is None:
        return None
    return data

def create_session(data=None):
    if data is None:
        return None
    return data