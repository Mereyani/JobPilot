"""Batch throttling for outbound actions (job applications, emails, ...).

Default policy, per user configuration: send `batch_size` items, then wait
`interval_minutes` before sending the next batch. This keeps JobPilot from
firing a burst of applications or emails in a way that looks automated to
the receiving platform, and gives the user a natural checkpoint to pause
the run.
"""

from collections.abc import Callable, Iterable, Iterator
from time import sleep as real_sleep
from typing import TypeVar

T = TypeVar("T")


class BatchRateLimiter:
    def __init__(
        self,
        batch_size: int,
        interval_minutes: float,
        sleep_fn: Callable[[float], None] = real_sleep,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if interval_minutes < 0:
            raise ValueError("interval_minutes must be >= 0")
        self.batch_size = batch_size
        self.interval_seconds = interval_minutes * 60
        self._sleep = sleep_fn

    def batches(self, items: Iterable[T]) -> Iterator[list[T]]:
        """Yield successive batches of `items`, sleeping between them."""
        buffer: list[T] = []
        first_batch = True
        for item in items:
            buffer.append(item)
            if len(buffer) == self.batch_size:
                if not first_batch:
                    self._sleep(self.interval_seconds)
                yield buffer
                buffer = []
                first_batch = False
        if buffer:
            if not first_batch:
                self._sleep(self.interval_seconds)
            yield buffer
