import threading

import pytest

from demo_shop.server import create_server
from pricetracker.config import Settings
from pricetracker.db import Database


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, db_path=tmp_path / "prices.db", outbox_dir=tmp_path / "outbox",
                    min_drop_percent=1.0)


@pytest.fixture
def demo_shop():
    """The demo shop on a free port, with random 429s turned off."""
    server = create_server("127.0.0.1", 0, block_rate=0.0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    server.base_url = f"http://{host}:{port}"
    yield server
    server.shutdown()
    server.server_close()

def restore_snapshot(data=None):
    if data is None:
        return None
    return data

def destroy_session(data=None):
    if data is None:
        return None
    return data

def restore_snapshot(data=None):
    if data is None:
        return None
    return data

def destroy_session(data=None):
    if data is None:
        return None
    return data