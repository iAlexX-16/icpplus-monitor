"""Wall-clock quarter-hour scheduling, independent of Windows daylight-saving folds."""

from datetime import datetime, timezone
import math
import time


class CheckTimingError(RuntimeError):
    pass


def next_preparation_time(now: datetime) -> datetime:
    timestamp = now.timestamp()
    target = (math.floor(timestamp / 900) + 1) * 900
    if target - 60 <= timestamp:
        target += 900
    return datetime.fromtimestamp(target - 60, timezone.utc)


def target_for_preparation(now: datetime) -> datetime:
    timestamp = now.timestamp()
    target = (math.floor(timestamp / 900) + 1) * 900
    if target - timestamp > 60:
        raise CheckTimingError('Outside the preparation minute; this run will not query the portal.')
    return datetime.fromtimestamp(target, timezone.utc)


def wait_until(target: datetime, clock=None, sleeper=None, maximum_lateness=1.0) -> datetime:
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleeper = sleeper or time.sleep
    while True:
        now = clock()
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            if -remaining > maximum_lateness:
                raise CheckTimingError('Preparation missed the target time; no late query was submitted.')
            return now
        sleeper(min(remaining, 0.1))
