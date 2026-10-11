import asyncio
import datetime
import logging
import random
import re
from typing import List

logger = logging.getLogger("app.utils")


def next_wakeup(schedule: List[datetime.time]) -> tuple[datetime.timedelta, datetime.datetime]:
    """Calculate next scheduled wakeup time.

    :param schedule: Array of times to wake up at.
    :return: Tuple of seconds until wakeup and the time to wake up at.
    """

    # Sort the times in the schedule from earliest to latest.
    schedule.sort()

    now = datetime.datetime.now()

    next_wakeup = None
    for dt in schedule:
        if now.time() < dt:
            # Its before scheduled time, so schedule for today.
            next_wakeup = datetime.datetime(now.year, now.month, now.day, dt.hour, dt.minute, dt.second)
            break

    if next_wakeup is None:
        # It was past all scheduled times, so schedule for earliest time tomorrow.
        next_wakeup = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), schedule[0])

    seconds_until_wakeup = next_wakeup - now
    return seconds_until_wakeup, next_wakeup


async def retry_until_successful(func, max_retries=5):
    """Retry a function until it succeeds.

    :param func: The function to call.
    :param max_retries: Maximum number of retries.
    """
    delay = 1

    for i in range(max_retries):
        try:
            return await func()
        except Exception as e:
            logger.exception("Error:", exc_info=e)
            logger.info(f"Retrying in {delay} seconds")
            await asyncio.sleep(delay)
            delay *= 2  # Exponential backoff.
            delay = min(delay, 60 * 5)  # Limit to 5 minutes.

    raise Exception(f"Failed after {max_retries} retries")


def parse_timedelta(interval: str) -> datetime.timedelta:
    """Parse a time interval string into a timedelta.

    :param interval: The interval string. For example, "5m" for 5 minutes. Supported units are "s", "m", "h", and "d".
    :return: The timedelta.
    """
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "s":
        return datetime.timedelta(seconds=value)
    elif unit == "m":
        return datetime.timedelta(minutes=value)
    elif unit == "h":
        return datetime.timedelta(hours=value)
    elif unit == "d":
        return datetime.timedelta(days=value)
    else:
        raise ValueError(f"Invalid unit: {unit}")


def random_jitter(interval: datetime.timedelta, jitter: float = 0.1) -> datetime.timedelta:
    """Add a random jitter to a timedelta.

    :param interval: The timedelta to add jitter to.
    :param jitter: The amount of jitter to add, as a percentage of the interval.
    :return: The jittered timedelta.
    """
    return interval * (1 + (random.random() * 2 - 1) * jitter)


def parse_numeric_value(value_str):
    """Parse a numeric value from a string, stripping units.

    Strips trailing alphabetic characters and units like %, then converts to float.
    Returns original value if it's already numeric or cannot be parsed.

    :param value_str: The value to parse (can be int, float, or string with units).
    :return: Numeric value (float) or original string if not parseable.
    """
    if isinstance(value_str, (int, float)):
        return value_str
    clean_value = re.sub(r"[a-zA-Z%]+$", "", str(value_str))
    try:
        return float(clean_value)
    except ValueError:
        return value_str


def interpolate_curve(x: float, points: List[List[float]]) -> float:
    """Perform linear interpolation on a curve defined by points.

    :param x: The input value to interpolate.
    :param points: List of [x, y] coordinate pairs defining the curve.
    :return: The interpolated y value.
    """
    # Sort points by x coordinate
    points.sort(key=lambda p: p[0])

    # Clamp to edges if outside range
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]

    # Find the two points to interpolate between
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        if p1[0] <= x <= p2[0]:
            # Linear interpolation: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
            t = (x - p1[0]) / (p2[0] - p1[0])
            return p1[1] + t * (p2[1] - p1[1])

    return points[0][1]
