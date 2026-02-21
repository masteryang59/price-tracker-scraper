import random

import httpx
from playwright.async_api import Error as PlaywrightError

from pricetracker.db import Product
from pricetracker.scraper import FetchResult, RobotsChecker, Scraper
from pricetracker.user_agents import UserAgentRotator

PRICE_PAGE = '<meta property="product:price:amount" content="10.00"><meta property="product:price:currency" content="USD">'
PRODUCT = Product(1, "https://shop.example/products/a", "A", None, None, True)


class FakeFetcher:
    """Plays back a list of responses (or exceptions) and records who asked."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, url, profile, selector):
        self.calls.append((url, profile, selector))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def no_sleep(_seconds):
    pass


def make_scraper(fetcher, **kwargs):
    kwargs.setdefault("sleep", no_sleep)
    return Scraper(fetcher, UserAgentRotator(rng=random.Random(0)), min_domain_delay=0, **kwargs)


async def test_ok_on_first_try():
    fetcher = FakeFetcher(FetchResult(200, PRICE_PAGE))
    result = await make_scraper(fetcher).check(PRODUCT)
    assert (result.status, str(result.extraction.price), result.attempts) == ("ok", "10.00", 1)


async def test_block_is_retried_with_a_different_user_agent():
    fetcher = FakeFetcher(FetchResult(429, "slow down"), FetchResult(403, "no"), FetchResult(200, PRICE_PAGE))
    result = await make_scraper(fetcher, max_attempts=3).check(PRODUCT)
    assert result.status == "ok" and result.attempts == 3
    agents = [profile.user_agent for _, profile, _ in fetcher.calls]
    assert agents[0] != agents[1] and agents[1] != agents[2]


async def test_gives_up_after_max_attempts():
    fetcher = FakeFetcher(*[FetchResult(429, "")] * 2)
    result = await make_scraper(fetcher, max_attempts=2).check(PRODUCT)
    assert (result.status, result.attempts) == ("blocked", 2)


async def test_challenge_page_with_200_counts_as_blocked():
    fetcher = FakeFetcher(FetchResult(200, "<h1>Please verify you are human</h1>"), FetchResult(200, PRICE_PAGE))
    result = await make_scraper(fetcher).check(PRODUCT)
    assert (result.status, result.attempts) == ("ok", 2)


async def test_captcha_script_on_a_good_page_is_not_a_block():
    fetcher = FakeFetcher(FetchResult(200, PRICE_PAGE + '<script src="/recaptcha/api.js"></script>'))
    assert (await make_scraper(fetcher).check(PRODUCT)).status == "ok"


async def test_page_without_price_is_not_retried():
    fetcher = FakeFetcher(FetchResult(200, "<h1>A</h1>"))
    result = await make_scraper(fetcher).check(PRODUCT)
    assert (result.status, result.attempts) == ("no_price", 1)


async def test_404_is_not_retried_but_500_is():
    result = await make_scraper(FakeFetcher(FetchResult(404, ""))).check(PRODUCT)
    assert (result.status, result.attempts, result.error) == ("error", 1, "HTTP 404")
    result = await make_scraper(FakeFetcher(FetchResult(500, ""), FetchResult(200, PRICE_PAGE))).check(PRODUCT)
    assert (result.status, result.attempts) == ("ok", 2)


async def test_browser_errors_are_retried():
    fetcher = FakeFetcher(PlaywrightError("net::ERR_CONNECTION_RESET\ncall log..."), FetchResult(200, PRICE_PAGE))
    assert (await make_scraper(fetcher).check(PRODUCT)).status == "ok"
    fetcher = FakeFetcher(PlaywrightError("net::ERR_NAME_NOT_RESOLVED"))
    result = await make_scraper(fetcher, max_attempts=1).check(PRODUCT)
    assert (result.status, result.error) == ("error", "Error: net::ERR_NAME_NOT_RESOLVED")


async def test_backoff_grows_between_attempts():
    waits = []

    async def record(seconds):
        waits.append(seconds)

    fetcher = FakeFetcher(*[FetchResult(503, "")] * 3)
    await make_scraper(fetcher, max_attempts=3, backoff_seconds=1, sleep=record).check(PRODUCT)
    assert len(waits) == 2 and waits[1] > waits[0]


async def test_same_domain_requests_are_spaced_out():
    waits = []

    async def record(seconds):
        waits.append(seconds)

    fetcher = FakeFetcher(*[FetchResult(200, PRICE_PAGE)] * 2)
    scraper = Scraper(fetcher, min_domain_delay=60, sleep=record)
    await scraper.check_many([PRODUCT, Product(2, "https://shop.example/products/b", None, None, None, True)])
    assert len(waits) == 1 and 55 < waits[0] <= 90


async def test_selector_is_passed_to_the_fetcher():
    fetcher = FakeFetcher(FetchResult(200, "<p class='p'>$5</p>"))
    product = Product(1, "https://shop.example/x", None, ".p", None, True)
    result = await make_scraper(fetcher).check(product)
    assert fetcher.calls[0][2] == ".p" and result.extraction.method == "selector"


def robots_client(status, body=""):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, text=body)))


async def test_robots_txt_disallow_skips_the_page():
    robots = RobotsChecker(robots_client(200, "User-agent: *\nDisallow: /products/\n"))
    fetcher = FakeFetcher()
    result = await make_scraper(fetcher, robots=robots).check(PRODUCT)
    assert result.status == "robots" and fetcher.calls == []


async def test_missing_robots_txt_allows_everything():
    assert await RobotsChecker(robots_client(404)).allowed(PRODUCT.url)
    assert not await RobotsChecker(robots_client(403)).allowed(PRODUCT.url)

def encrypt_field(data=None):
    if data is None:
        return None
    return data

def load_config(data=None):
    if data is None:
        return None
    return data

def encrypt_field(data=None):
    if data is None:
        return None
    return data

def load_config(data=None):
    if data is None:
        return None
    return data