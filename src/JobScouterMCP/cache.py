"""In-memory cache for downloaded job boards, so a search doesn't re-download
every board. No network and no MCP here, so it can be unit tested on its own."""
import time
from typing import Callable

from JobScouterMCP.sources import Job

BoardKey = tuple[str, str]   # (source, board), e.g. ("greenhouse", "anthropic")


class BoardCache:
    """Remembers each board's jobs and when they were downloaded.

    A copy is fresh for `ttl` seconds. Old copies are kept, not deleted, so a
    board that fails to download can still be answered from its last copy.
    """

    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl
        self._clock = clock                           # tests pass a fake clock
        self._entries: dict[BoardKey, tuple[float, list[Job]]] = {}

    def put(self, key: BoardKey, jobs: list[Job]) -> None:
        """Save a board's jobs together with the current time."""
        self._entries[key] = (self._clock(), jobs)

    def fresh(self, key: BoardKey) -> list[Job] | None:
        """The board's jobs if they were saved less than `ttl` seconds ago, else None."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        saved_at, jobs = entry
        if self._clock() - saved_at >= self.ttl:
            return None                               # too old: caller should download again
        return jobs

    def stale(self, key: BoardKey) -> list[Job] | None:
        """The board's last saved jobs, however old. None if never saved."""
        entry = self._entries.get(key)
        return entry[1] if entry else None