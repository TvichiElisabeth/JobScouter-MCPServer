"""
The four tests cover the life of one cache entry:
 never saved → saved and fresh (1 s before the limit) 
→ expired at exactly the limit but kept → saved again and fresh again.

Notes: Unit tests for BoardCache. A fake clock replaces real time, so the tests
can jump an hour ahead instantly instead of waiting.

"""
from JobScouterMCP.cache import BoardCache

KEY = ("greenhouse", "anthropic")
JOBS = [{"id": "greenhouse:Anthropic:1", "title": "Engineer"}]


class FakeClock:
    """Stands in for time.monotonic: returns whatever time the test sets."""
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_unknown_board_is_not_cached():
    cache = BoardCache(ttl=3600, clock=FakeClock())
    assert cache.fresh(KEY) is None
    assert cache.stale(KEY) is None


def test_saved_board_is_fresh_before_ttl():
    clock = FakeClock()
    cache = BoardCache(ttl=3600, clock=clock)
    cache.put(KEY, JOBS)
    clock.now = 3599                      # 1 second before it expires
    assert cache.fresh(KEY) == JOBS


def test_board_expires_after_ttl_but_old_copy_is_kept():
    clock = FakeClock()
    cache = BoardCache(ttl=3600, clock=clock)
    cache.put(KEY, JOBS)
    clock.now = 3600                      # exactly one hour later
    assert cache.fresh(KEY) is None       # too old: download again
    assert cache.stale(KEY) == JOBS       # but still usable if the download fails


def test_saving_again_makes_the_board_fresh_again():
    clock = FakeClock()
    cache = BoardCache(ttl=3600, clock=clock)
    cache.put(KEY, JOBS)
    clock.now = 5000
    cache.put(KEY, JOBS)                  # re-downloaded at t=5000
    clock.now = 8000                      # 3000 s after the second save
    assert cache.fresh(KEY) == JOBS