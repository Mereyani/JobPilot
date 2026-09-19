from jobpilot.core.rate_limiter import BatchRateLimiter


def test_batches_of_exact_size():
    sleeps: list[float] = []
    limiter = BatchRateLimiter(batch_size=10, interval_minutes=10, sleep_fn=sleeps.append)

    batches = list(limiter.batches(range(30)))

    assert [len(b) for b in batches] == [10, 10, 10]
    # No sleep before the first batch, one sleep before each subsequent batch.
    assert sleeps == [600, 600]


def test_partial_final_batch():
    sleeps: list[float] = []
    limiter = BatchRateLimiter(batch_size=10, interval_minutes=10, sleep_fn=sleeps.append)

    batches = list(limiter.batches(range(25)))

    assert [len(b) for b in batches] == [10, 10, 5]
    assert sleeps == [600, 600]


def test_fewer_items_than_batch_size_does_not_sleep():
    sleeps: list[float] = []
    limiter = BatchRateLimiter(batch_size=10, interval_minutes=10, sleep_fn=sleeps.append)

    batches = list(limiter.batches(range(3)))

    assert [len(b) for b in batches] == [3]
    assert sleeps == []


def test_rejects_invalid_config():
    import pytest

    with pytest.raises(ValueError):
        BatchRateLimiter(batch_size=0, interval_minutes=10)
    with pytest.raises(ValueError):
        BatchRateLimiter(batch_size=10, interval_minutes=-1)
