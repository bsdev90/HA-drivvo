"""Pure calculations behind the Drivvo sensors.

Everything here is deliberately free of Home Assistant imports so the maths can
be exercised on its own. The algorithms mirror what the official web app does
client-side, since the API exposes raw records and no computed report.
"""

from __future__ import annotations

import calendar
import datetime

from .const import (
    DISTANCE_HOURS,
    DISTANCE_KILOMETERS,
    DISTANCE_MILES,
    EFFICIENCY_GALLON_UK_100KM,
    EFFICIENCY_GALLON_UK_100MI,
    EFFICIENCY_GALLON_US_100KM,
    EFFICIENCY_GALLON_US_100MI,
    EFFICIENCY_KM_GALLON_UK,
    EFFICIENCY_KM_GALLON_US,
    EFFICIENCY_LITER_100KM,
    EFFICIENCY_LITER_100MI,
    EFFICIENCY_MILE_GALLON_UK,
    EFFICIENCY_MILE_GALLON_US,
    EFFICIENCY_MILE_LITER,
    GALLON_UK_PER_LITER,
    GALLON_US_PER_LITER,
    KM_PER_MILE,
    MILE_PER_KM,
    VOLUME_GALLON_UK,
    VOLUME_GALLON_US,
)


def to_float(value) -> float | None:
    """Coerce an API value to float, tolerating None and empty strings."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def add_months(value: datetime.datetime, months: int) -> datetime.datetime:
    """Add calendar months, clamping to the last day of the target month."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def sorted_desc(items: list[dict]) -> list[dict]:
    """Sort API records by date, newest first."""
    return sorted(items or [], key=lambda item: item.get("data") or "", reverse=True)


def liters(volume: float, volume_unit: int) -> float:
    """Convert a volume expressed in the account unit to liters."""
    if volume_unit == VOLUME_GALLON_US:
        return volume / GALLON_US_PER_LITER
    if volume_unit == VOLUME_GALLON_UK:
        return volume / GALLON_UK_PER_LITER
    return volume


def efficiency(
    distance: float,
    volume: float,
    distance_unit: int,
    volume_unit: int,
    efficiency_unit: int,
) -> float | None:
    """Replicate Drivvo's fuel efficiency calculation.

    ``distance`` and ``volume`` are in the account's own units, exactly as the
    API stores them.
    """
    if not distance or not volume or distance <= 0 or volume <= 0:
        return None

    # A vehicle measured in hours reports consumption per hour, not per distance.
    if distance_unit == DISTANCE_HOURS:
        return volume / distance

    volume_l = liters(volume, volume_unit)
    if volume_l <= 0:
        return None

    km = distance * KM_PER_MILE if distance_unit == DISTANCE_MILES else distance
    miles = distance * MILE_PER_KM if distance_unit == DISTANCE_KILOMETERS else distance
    gallons_us = volume_l * GALLON_US_PER_LITER
    gallons_uk = volume_l * GALLON_UK_PER_LITER

    if efficiency_unit == EFFICIENCY_KM_GALLON_US:
        return km / gallons_us
    if efficiency_unit == EFFICIENCY_KM_GALLON_UK:
        return km / gallons_uk
    if efficiency_unit == EFFICIENCY_LITER_100KM:
        return volume_l / km * 100
    if efficiency_unit == EFFICIENCY_GALLON_US_100KM:
        return gallons_us / km * 100
    if efficiency_unit == EFFICIENCY_GALLON_UK_100KM:
        return gallons_uk / km * 100
    if efficiency_unit == EFFICIENCY_MILE_LITER:
        return miles / volume_l
    if efficiency_unit == EFFICIENCY_MILE_GALLON_US:
        return miles / gallons_us
    if efficiency_unit == EFFICIENCY_MILE_GALLON_UK:
        return miles / gallons_uk
    if efficiency_unit == EFFICIENCY_LITER_100MI:
        return volume_l / miles * 100
    if efficiency_unit == EFFICIENCY_GALLON_US_100MI:
        return gallons_us / miles * 100
    if efficiency_unit == EFFICIENCY_GALLON_UK_100MI:
        return gallons_uk / miles * 100
    return km / volume_l


def refuelling_volume(refuelling: dict) -> float:
    """Volume of a refuelling, derived from the price when not informed.

    Mirrors Drivvo's ``getLitros``: a cost-free refuelling reports its volume
    directly, otherwise the volume is the amount paid divided by the unit price.
    """
    volume = to_float(refuelling.get("volume")) or 0
    if refuelling.get("sem_custo"):
        return volume
    price = to_float(refuelling.get("preco")) or 0
    total = to_float(refuelling.get("valor_total")) or 0
    if price > 0:
        return total / price
    return volume


def fuel_segments(
    refuellings: list[dict], volume_fn=refuelling_volume
) -> list[tuple[float, float, float]]:
    """Split the refuelling history into full-tank to full-tank segments.

    Drivvo only measures consumption between two full tanks: the fuel burnt
    before the first full tank is unknown, so it is discarded, and a refuelling
    flagged ``esqueceu_anterior`` (the driver forgot to log the previous one)
    breaks the chain. Returns ``(distance, volume, cost)`` per closed segment.

    ``volume_fn`` resolves the volume of a row; pass one that simply reads the
    field when the volume has already been computed upstream.
    """
    items = sorted(refuellings or [], key=lambda item: item.get("odometro") or 0)
    segments: list[tuple[float, float, float]] = []

    start_odometer: float | None = None
    volume = 0.0
    cost = 0.0

    for item in items:
        odometer = to_float(item.get("odometro")) or 0
        full_tank = bool(item.get("tanque_cheio"))

        if item.get("esqueceu_anterior"):
            # The chain is unreliable from here; restart at this refuelling.
            start_odometer = odometer if full_tank else None
            volume = 0.0
            cost = 0.0
            continue

        if start_odometer is None:
            if full_tank:
                start_odometer = odometer
            continue

        volume += volume_fn(item)
        cost += to_float(item.get("valor_total")) or 0

        if full_tank:
            distance = odometer - start_odometer
            if distance > 0 and volume > 0:
                segments.append((distance, volume, cost))
            start_odometer = odometer
            volume = 0.0
            cost = 0.0

    return segments


def reminder_last_entry(
    reminder: dict, expenses: list[dict], services: list[dict]
) -> tuple[float, str | None]:
    """Last odometer and date logged for the type a reminder watches."""
    if reminder.get("id_tipo_despesa"):
        source, key, type_key = expenses, "tipos_despesa", "id_tipo_despesa"
        type_id = reminder.get("id_tipo_despesa")
    else:
        source, key, type_key = services, "tipos_servico", "id_tipo_servico"
        type_id = reminder.get("id_tipo_servico")

    matches = sorted_desc(
        [
            item
            for item in source or []
            if any(entry.get(type_key) == type_id for entry in (item.get(key) or []))
        ]
    )
    if not matches:
        return 0, None

    with_odometer = next(
        (item for item in matches if (to_float(item.get("odometro")) or 0) > 0), None
    )
    odometer = to_float(with_odometer.get("odometro")) if with_odometer else 0
    return odometer or 0, matches[0].get("data")


def reminder_predictions(
    reminders: list[dict],
    expenses: list[dict],
    services: list[dict],
    current_odometer: float | None,
    now: datetime.datetime,
    parse_datetime,
) -> list[dict]:
    """Compute when each reminder falls due.

    Drivvo does not store the due date: the app derives it from the last entry
    of the watched type plus the repetition interval. This mirrors that.
    """
    predictions: list[dict] = []

    for reminder in reminders or []:
        # Route based reminders belong to the trip timeline, not to maintenance.
        if reminder.get("id_percurso"):
            continue

        last_odometer, last_date = reminder_last_entry(reminder, expenses, services)
        repeats = not reminder.get("unico_repetir")
        repeat_time = to_float(reminder.get("repetir_tempo")) or 0
        repeat_distance = to_float(reminder.get("repetir_distancia")) or 0

        next_date = None
        if repeats and repeat_time > 0 and last_date:
            base = parse_datetime(last_date)
            if base is not None:
                period = reminder.get("periodo")
                if period == 1:
                    next_date = base + datetime.timedelta(days=int(repeat_time))
                elif period == 3:
                    next_date = add_months(base, int(repeat_time) * 12)
                else:
                    next_date = add_months(base, int(repeat_time))
        if next_date is None:
            next_date = parse_datetime(reminder.get("data"))

        target_odometer = to_float(reminder.get("odometro")) or 0
        if repeats and repeat_distance > 0 and last_odometer > 0:
            next_odometer = repeat_distance + last_odometer
        elif target_odometer > 0:
            next_odometer = target_odometer
        else:
            next_odometer = None

        days_left = None
        if next_date is not None:
            days_left = (next_date.date() - now.date()).days

        distance_left = None
        if next_odometer is not None and current_odometer is not None:
            distance_left = next_odometer - current_odometer

        predictions.append(
            {
                "id": reminder.get("id_lembrete"),
                "description": reminder.get("tipo_servico")
                or reminder.get("tipo_despesa")
                or reminder.get("observacao"),
                "date": next_date,
                "odometer": next_odometer,
                "days_left": days_left,
                "distance_left": distance_left,
                "overdue": bool(
                    (days_left is not None and days_left < 0)
                    or (distance_left is not None and distance_left < 0)
                ),
                "note": reminder.get("observacao"),
            }
        )

    return predictions


def sort_key_reminder(prediction: dict) -> tuple:
    """Order reminders the way the app does: closest to due first."""
    days = prediction.get("days_left")
    distance = prediction.get("distance_left")
    proximity = float("inf")
    if days is not None:
        proximity = min(proximity, days / 30)
    if distance is not None:
        proximity = min(proximity, distance / 1000)
    return (proximity, prediction.get("description") or "")


def sum_typed_values(item: dict, key: str) -> float:
    """Total of a service/expense record, which can hold several typed lines."""
    return sum(to_float(line.get("valor")) or 0 for line in item.get(key) or [])


def typed_names(item: dict, key: str) -> str | None:
    """Human readable list of the types of a service/expense record."""
    names = [line.get("nome") for line in item.get(key) or [] if line.get("nome")]
    return ", ".join(names) if names else None
