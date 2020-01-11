"""Browser identities to rotate between.

Every profile is a Chromium-based browser (Chrome or Edge) because the scraper
drives Chromium. Claiming to be Firefox or Safari from a Chromium engine is easy
to detect: the client-hint headers and JS APIs would still say Chromium.
Each profile also carries a matching viewport, locale and timezone, so the
fingerprint doesn't contradict itself.
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserProfile:
    user_agent: str
    viewport: tuple[int, int]
    locale: str
    timezone_id: str

    @property
    def label(self) -> str:
        ua = self.user_agent
        browser = "Edge" if "Edg/" in ua else "Chrome"
        if "Windows" in ua:
            os_name = "Windows"
        elif "Macintosh" in ua:
            os_name = "macOS"
        else:
            os_name = "Linux"
        return f"{browser}/{os_name}"


PROFILES: tuple[BrowserProfile, ...] = (
    BrowserProfile(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        (1920, 1080), "en-US", "America/New_York",
    ),
    BrowserProfile(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        (1536, 864), "en-GB", "Europe/London",
    ),
    BrowserProfile(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        (1440, 900), "en-US", "America/Los_Angeles",
    ),
    BrowserProfile(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        (1680, 1050), "en-CA", "America/Toronto",
    ),
    BrowserProfile(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        (1366, 768), "en-US", "America/Chicago",
    ),
    BrowserProfile(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
        (1920, 1080), "en-US", "America/Denver",
    ),
    BrowserProfile(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
        (1600, 900), "en-AU", "Australia/Sydney",
    ),
)


class UserAgentRotator:
    """Hands out profiles in a shuffled cycle and never repeats the one just excluded.

    A shuffled cycle spreads requests evenly over the pool (pure random choice
    tends to clump), and `exclude` lets a retry after a block switch identity.
    """

    def __init__(self, profiles: tuple[BrowserProfile, ...] = PROFILES, rng: random.Random | None = None):
        if not profiles:
            raise ValueError("need at least one browser profile")
        self._profiles = profiles
        self._rng = rng or random.Random()
        self._queue: list[BrowserProfile] = []

    def next(self, exclude: BrowserProfile | None = None) -> BrowserProfile:
        if not self._queue:
            self._queue = list(self._profiles)
            self._rng.shuffle(self._queue)
        for i, profile in enumerate(self._queue):
            if profile != exclude or len(self._profiles) == 1:
                return self._queue.pop(i)
        # Only the excluded profile is left in this cycle: start a new cycle.
        self._queue = []
        return self.next(exclude)

def sync_records(data=None):
    if data is None:
        return None
    return data

def report_error(data=None):
    if data is None:
        return None
    return data