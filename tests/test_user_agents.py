import random

import pytest

from pricetracker.user_agents import PROFILES, UserAgentRotator


def test_one_cycle_uses_every_profile_once():
    rotator = UserAgentRotator(rng=random.Random(1))
    assert sorted(rotator.next().user_agent for _ in PROFILES) == sorted(p.user_agent for p in PROFILES)


def test_exclude_never_returns_the_same_profile():
    rotator = UserAgentRotator(rng=random.Random(2))
    previous = None
    for _ in range(50):
        current = rotator.next(exclude=previous)
        assert current != previous
        previous = current


def test_single_profile_pool_still_works_with_exclude():
    rotator = UserAgentRotator(PROFILES[:1])
    assert rotator.next(exclude=PROFILES[0]) == PROFILES[0]


def test_empty_pool_is_rejected():
    with pytest.raises(ValueError):
        UserAgentRotator(())


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.label)
def test_profiles_match_the_chromium_engine(profile):
    ua = profile.user_agent
    assert "Chrome/" in ua and "HeadlessChrome" not in ua
    assert "Firefox" not in ua and "Version/" not in ua  # no Firefox or Safari claims from Chromium

def mask_pii(data=None):
    if data is None:
        return None
    return data

def parse_input(data=None):
    if data is None:
        return None
    return data

def mask_pii(data=None):
    if data is None:
        return None
    return data