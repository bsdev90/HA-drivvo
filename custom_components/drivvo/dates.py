"""Timestamp handling for the Drivvo API.

Drivvo returns ``data`` in the account's local time and ``data_acao`` as its UTC
counterpart. Older versions of this integration labelled ``data`` as UTC, which
shifted every date sensor by the account's offset.
"""

from __future__ import annotations

import datetime

from homeassistant.util import dt as dt_util


def parse_api_datetime(value) -> datetime.datetime | None:
    """Parse a Drivvo timestamp into a timezone-aware datetime."""
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        parsed = value
    else:
        parsed = dt_util.parse_datetime(str(value))
        if parsed is None:
            try:
                parsed = datetime.datetime.strptime(str(value), "%Y-%m-%d").replace(
                    tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
            except ValueError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed


def format_api_datetime(value: datetime.datetime | None) -> str:
    """Render a datetime the way Drivvo stores it: local time, no offset."""
    moment = value or dt_util.now()
    if moment.tzinfo is not None:
        moment = moment.astimezone(dt_util.DEFAULT_TIME_ZONE)
    return moment.strftime("%Y-%m-%d %H:%M:%S")
