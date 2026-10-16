"""When each app posts: one posting day, then cycle_days - 1 days off, at a fixed Cairo time.

Every app has a phase, so posting days are those on or after anchor_date where
(day - anchor_date) % cycle_days == phase. Apps that share a phase post on the same days and must use
different times.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MIN_SAME_DAY_GAP = timedelta(minutes=60)


class Plan:
    def __init__(self, config):
        self.tz = ZoneInfo(config["timezone"])
        self.anchor = date.fromisoformat(config["anchor_date"])
        self.cycle = int(config["cycle_days"])
        self.window = timedelta(minutes=int(config["late_window_minutes"]))
        self.apps = config["apps"]

    def now(self):
        return datetime.now(self.tz)

    def enabled(self, app):
        return self.apps[app].get("enabled", True)

    def problems(self):
        issues = []
        by_phase = {}
        for app, conf in self.apps.items():
            if not 0 <= conf["phase"] < self.cycle:
                issues.append(f"{app}: phase must be between 0 and {self.cycle - 1}")
            try:
                self._time(app)
            except ValueError:
                issues.append(f"{app}: time must look like 20:00")
                continue
            if self.enabled(app):
                by_phase.setdefault(conf["phase"], []).append(app)
        for apps in by_phase.values():
            ordered = sorted(apps, key=self._time)
            for first, second in zip(ordered, ordered[1:]):
                gap = datetime.combine(date.min, self._time(second)) - datetime.combine(date.min, self._time(first))
                if gap < MIN_SAME_DAY_GAP:
                    issues.append(f"{first} and {second} post on the same days, so their times must be at least an hour apart")
        return issues

    def _time(self, app):
        hours, minutes = (int(part) for part in self.apps[app]["time"].split(":"))
        return time(hours, minutes)

    def is_post_day(self, app, day):
        return day >= self.anchor and (day - self.anchor).days % self.cycle == self.apps[app]["phase"]

    def next_post_day(self, app, start):
        """The first posting day for `app` on or after `start`."""
        day = start
        while not self.is_post_day(app, day):
            day += timedelta(days=1)
        return day

    def slot(self, app, day):
        return datetime.combine(day, self._time(app), tzinfo=self.tz)

    def due(self, app, now, last_posted):
        """(True, "") when `app` should publish now, otherwise (False, the reason)."""
        today = now.date()
        at = self.apps[app]["time"]
        if not self.enabled(app):
            return False, "paused in config.json"
        if last_posted == today:
            return False, "already posted today"
        if last_posted and (today - last_posted).days < self.cycle:
            return False, f"last posted {last_posted:%a %d %b}, resting"
        if not self.is_post_day(app, today):
            return False, f"next posting day is {self.next_post_day(app, today):%a %d %b} at {at}"
        start = self.slot(app, today)
        if now < start:
            return False, f"posts today at {at}"
        if now >= start + self.window:
            return False, f"today's {at} slot has passed"
        return True, ""

    def project(self, app, posts, now, last_posted):
        """Pairs each upcoming post with the slot it goes out in, assuming every run succeeds."""
        out = []
        day = now.date()
        for post in posts:
            day = self.next_post_day(app, day)
            while (last_posted and (day - last_posted).days < self.cycle) or (
                day == now.date() and now >= self.slot(app, day) + self.window
            ):
                day = self.next_post_day(app, day + timedelta(days=1))
            out.append((self.slot(app, day), post))
            last_posted = day
            day += timedelta(days=1)
        return out
