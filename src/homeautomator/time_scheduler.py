"""Time-based scheduling for rules engine."""

import datetime
import logging
from typing import List, Optional

import astral
import astral.sun

from homeautomator.models import Rule, TriggerType

logger = logging.getLogger("app.time_scheduler")


class TimeScheduler:
    """Handles time-based rule scheduling with solar event support."""

    def __init__(self, city: Optional[astral.LocationInfo] = None):
        """Initialize the time scheduler.

        Args:
            city: Optional LocationInfo for solar event calculations.
        """
        self.city = city

    def get_todays_schedule(self, rules: List[Rule]) -> List[datetime.time]:
        """Get all scheduled times for today from time-based rules.

        Args:
            rules: List of all rules.

        Returns:
            Sorted list of unique times to trigger today.
        """
        times = set()
        now = datetime.datetime.now()
        day_str = now.strftime("%a")

        for rule in rules:
            if not rule.enabled:
                continue
            if rule.trigger.type != TriggerType.TIME:
                continue
            if rule.trigger.schedule is None:
                continue

            # Filter by day of week if specified
            if rule.trigger.schedule.days is not None and day_str not in rule.trigger.schedule.days:
                continue

            t = self._resolve_time(rule.trigger.schedule.at, now.date())
            if t:
                times.add(t)

        return sorted(list(times))

    def check_time_rules(self, rules: List[Rule], current_time: datetime.datetime) -> List[Rule]:
        """Check which time-based rules should trigger at the current time.

        Args:
            rules: List of all rules.
            current_time: The current datetime to check against.

        Returns:
            List of rules that should trigger now.
        """
        matching_rules = []
        current_hm = current_time.strftime("%H:%M")
        day_str = current_time.strftime("%a")

        for rule in rules:
            if not rule.enabled:
                continue
            if rule.trigger.type != TriggerType.TIME:
                continue
            if rule.trigger.schedule is None:
                continue

            # Filter by day of week if specified
            if rule.trigger.schedule.days is not None and day_str not in rule.trigger.schedule.days:
                continue

            t = self._resolve_time(rule.trigger.schedule.at, current_time.date())
            if t and t.strftime("%H:%M") == current_hm:
                matching_rules.append(rule)

        return matching_rules

    def _resolve_time(self, at_str: str, date: datetime.date) -> Optional[datetime.time]:
        """Resolve a time string to an actual time.

        Handles both absolute times (HH:MM) and solar events (sunrise, sunset, dusk).

        Args:
            at_str: Time string (e.g., "14:30", "sunrise", "sunset", "dusk").
            date: Date for which to resolve the time.

        Returns:
            Resolved time, or None if cannot be resolved.
        """
        # Try parsing as absolute time first
        try:
            return datetime.datetime.strptime(at_str, "%H:%M").time()
        except ValueError:
            pass

        # Try resolving as solar event
        if self.city:
            try:
                s = astral.sun.sun(self.city.observer, date=date, tzinfo=self.city.timezone)
                if at_str in s:
                    return datetime.time(hour=s[at_str].hour, minute=s[at_str].minute)
            except Exception:
                pass

        return None
