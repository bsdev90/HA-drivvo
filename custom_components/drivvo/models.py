"""Domain models for the Drivvo integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import calc
from .const import (
    DISTANCE_HOURS,
    DISTANCE_KILOMETERS,
    EFFICIENCY_KM_LITER,
    FUEL_TYPE_ELECTRIC,
    VOLUME_GALLON_UK,
    VOLUME_GALLON_US,
    VOLUME_LITER,
)
from .units import UnitOfDrivvoVolume, UnitOfFuelEfficiency

EFFICIENCY_UNITS = {
    1: UnitOfFuelEfficiency.KILOMETERS_PER_LITER,
    2: UnitOfFuelEfficiency.KILOMETERS_PER_GALLON_US,
    3: UnitOfFuelEfficiency.KILOMETERS_PER_GALLON_UK,
    4: UnitOfFuelEfficiency.LITERS_PER_100_KILOMETERS,
    5: UnitOfFuelEfficiency.GALLONS_US_PER_100_KILOMETERS,
    6: UnitOfFuelEfficiency.GALLONS_UK_PER_100_KILOMETERS,
    7: UnitOfFuelEfficiency.MILES_PER_LITER,
    8: UnitOfFuelEfficiency.MILES_PER_GALLON,
    9: UnitOfFuelEfficiency.MILES_PER_GALLON_UK,
    10: UnitOfFuelEfficiency.LITERS_PER_100_MILES,
    11: UnitOfFuelEfficiency.GALLONS_US_PER_100_MILES,
    12: UnitOfFuelEfficiency.GALLONS_UK_PER_100_MILES,
}

VOLUME_UNITS = {
    VOLUME_LITER: UnitOfDrivvoVolume.LITERS,
    VOLUME_GALLON_US: UnitOfDrivvoVolume.GALLONS_US,
    VOLUME_GALLON_UK: UnitOfDrivvoVolume.GALLONS_UK,
}

DISTANCE_UNITS = {1: "km", 2: "mi", 3: "h"}


def _safe_volume(row: dict[str, Any]) -> float:
    """Volume of a refuelling row, following Drivvo's own rule.

    Drivvo derives the volume from what was paid unless the refuelling was
    free, because the price is the value the driver actually types in.
    """
    return calc.refuelling_volume(row)


def _typed_lines(row: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Typed value lines of a service/expense row."""
    lines = row.get(key)
    return lines if isinstance(lines, list) else []


def _typed_total(row: dict[str, Any], key: str) -> float:
    """Total of a service/expense row.

    The web API returns the amount split per type in ``tipos_servico`` /
    ``tipos_despesa``; ``valor_total`` is only a fallback for other shapes.
    """
    lines = _typed_lines(row, key)
    if lines:
        return sum(float(line.get("valor") or 0) for line in lines)
    return float(row.get("valor_total") or 0)


def _typed_description(row: dict[str, Any], key: str) -> str | None:
    """Readable description of a service/expense row."""
    names = [line.get("nome") for line in _typed_lines(row, key) if line.get("nome")]
    if names:
        return ", ".join(names)
    return row.get("titulo") or row.get("descricao") or None


def _place_name(row: dict[str, Any], key: str) -> str | None:
    """Name of the nested place/station object, when present."""
    place = row.get(key)
    return place.get("nome") if isinstance(place, dict) else None


@dataclass(frozen=True)
class Refuelling:
    date: str | None
    odometer: int
    volume: float
    price: float
    total_value: float
    fuel_type: str | None
    reason: int | None
    tank_full: bool
    station: str | None
    fuel_type_id: int | None = None
    free: bool = False
    forgot_previous: bool = False
    payment: str | None = None
    battery_start: float | None = None
    battery_end: float | None = None
    duration: float | None = None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Refuelling:
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            volume=_safe_volume(row),
            price=float(row.get("preco") or 0),
            total_value=float(row.get("valor_total") or 0),
            fuel_type=row.get("combustivel"),
            reason=row.get("tipo_motivo"),
            tank_full=bool(row.get("tanque_cheio")),
            station=_place_name(row, "posto_combustivel"),
            fuel_type_id=row.get("id_tipo_combustivel"),
            free=bool(row.get("sem_custo")),
            forgot_previous=bool(row.get("esqueceu_anterior")),
            payment=row.get("forma_pagamento"),
            battery_start=calc.to_float(row.get("bateria_inicial_pct")),
            battery_end=calc.to_float(row.get("bateria_final_pct")),
            duration=calc.to_float(row.get("duracao_minutos")),
        )


@dataclass(frozen=True)
class Service:
    date: str | None
    odometer: int
    total_value: float
    description: str | None
    place: str | None = None
    type_ids: tuple[int, ...] = ()

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Service:
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            total_value=_typed_total(row, "tipos_servico"),
            description=_typed_description(row, "tipos_servico")
            or row.get("tipo_servico"),
            place=_place_name(row, "local"),
            type_ids=tuple(
                line["id_tipo_servico"]
                for line in _typed_lines(row, "tipos_servico")
                if line.get("id_tipo_servico") is not None
            ),
        )


@dataclass(frozen=True)
class Expense:
    date: str | None
    odometer: int
    total_value: float
    description: str | None
    expense_type: str | None
    type_ids: tuple[int, ...] = ()

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Expense:
        description = _typed_description(row, "tipos_despesa")
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            total_value=_typed_total(row, "tipos_despesa"),
            description=description,
            expense_type=row.get("tipo_despesa") or description,
            type_ids=tuple(
                line["id_tipo_despesa"]
                for line in _typed_lines(row, "tipos_despesa")
                if line.get("id_tipo_despesa") is not None
            ),
        )


@dataclass(frozen=True)
class Income:
    date: str | None
    odometer: int
    total_value: float
    income_type: str | None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Income:
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            total_value=float(row.get("valor") or row.get("valor_total") or 0),
            income_type=row.get("tipo_receita"),
        )


@dataclass(frozen=True)
class Route:
    date: str | None
    odometer_start: int
    odometer_end: int

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Route:
        return cls(
            date=row.get("data"),
            odometer_start=row.get("odometro_inicial") or 0,
            odometer_end=row.get("odometro_final") or 0,
        )

    @property
    def distance(self) -> int:
        if self.odometer_end > self.odometer_start:
            return self.odometer_end - self.odometer_start
        return 0


@dataclass(frozen=True)
class Reading:
    date: str | None
    odometer: int

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Reading:
        return cls(date=row.get("data"), odometer=row.get("odometro") or 0)


@dataclass(frozen=True)
class Checklist:
    date: str | None
    odometer: int
    title: str | None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Checklist:
        form = row.get("form")
        title = form.get("titulo") if isinstance(form, dict) else None
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            title=title,
        )


@dataclass(frozen=True)
class AccountConfig:
    """Units and formats configured in the Drivvo account."""

    currency: str | None = None
    distance_unit_id: int = DISTANCE_KILOMETERS
    volume_unit_id: int = VOLUME_LITER
    efficiency_id: int = EFFICIENCY_KM_LITER

    @classmethod
    def from_api(cls, row: dict[str, Any] | None) -> AccountConfig:
        row = row or {}
        return cls(
            currency=row.get("formato_valor"),
            distance_unit_id=row.get("unidade_distancia") or DISTANCE_KILOMETERS,
            volume_unit_id=row.get("unidade_medida") or VOLUME_LITER,
            efficiency_id=row.get("eficiencia_combustivel") or EFFICIENCY_KM_LITER,
        )


@dataclass
class VehicleData:
    id: int
    name: str | None
    placa: str | None
    manufacturer: str
    model: str
    distance_unit: str
    currency: str | None
    refuellings: list[Refuelling] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    incomes: list[Income] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    readings: list[Reading] = field(default_factory=list)
    checklists: list[Checklist] = field(default_factory=list)
    reminders_raw: list[dict[str, Any]] = field(default_factory=list)
    config: AccountConfig = field(default_factory=AccountConfig)
    distance_unit_id: int = DISTANCE_KILOMETERS
    year: int | None = None
    chassis: str | None = None
    renavam: str | None = None
    tank_volume: float | None = None
    dual_fuel: bool | None = None
    primary: bool | None = None
    active: bool | None = None
    purchase_value: float | None = None
    sale_value: float | None = None
    note: str | None = None
    fuel_type_id: int | None = None
    driver_license_expiry: str | None = None
    reminders: list[dict[str, Any]] = field(default_factory=list)

    # --- Identity ----------------------------------------------------------

    @property
    def identification(self) -> str:
        if self.name:
            return self.name
        if self.placa:
            return self.placa
        return f"{self.manufacturer}/{self.model}"

    # --- Units -------------------------------------------------------------

    @property
    def is_electric(self) -> bool:
        return self.fuel_type_id == FUEL_TYPE_ELECTRIC

    @property
    def volume_unit(self) -> str:
        if self.is_electric:
            return str(UnitOfDrivvoVolume.KILOWATT_HOURS)
        return str(
            VOLUME_UNITS.get(self.config.volume_unit_id, UnitOfDrivvoVolume.LITERS)
        )

    @property
    def efficiency_unit(self) -> str:
        if self.distance_unit_id == DISTANCE_HOURS:
            return f"{self.volume_unit}/h"
        if self.is_electric:
            return f"{self.distance_unit}/kWh"
        return str(
            EFFICIENCY_UNITS.get(
                self.config.efficiency_id, UnitOfFuelEfficiency.KILOMETERS_PER_LITER
            )
        )

    # --- Odometer ----------------------------------------------------------

    def _latest_event(self) -> tuple[str, int] | None:
        """Most recent (date, odometer) across every module that carries one."""
        events: list[tuple[str, int]] = [
            *((r.date or "", r.odometer) for r in self.refuellings),
            *((s.date or "", s.odometer) for s in self.services),
            *((e.date or "", e.odometer) for e in self.expenses),
            *((i.date or "", i.odometer) for i in self.incomes),
            *((r.date or "", r.odometer) for r in self.readings),
            *((c.date or "", c.odometer) for c in self.checklists),
            *((r.date or "", r.odometer_end or r.odometer_start) for r in self.routes),
        ]
        events = [event for event in events if event[1]]
        if not events:
            return None
        return max(events, key=lambda t: t[0])

    @property
    def odometer(self) -> int | None:
        ev = self._latest_event()
        return ev[1] if ev else None

    @property
    def odometer_date(self) -> str | None:
        ev = self._latest_event()
        if ev is None:
            return None
        return ev[0] or None

    # --- Refuellings -------------------------------------------------------

    @property
    def refuelling_total(self) -> int:
        return len(self.refuellings)

    @property
    def refuelling_value_total(self) -> float:
        return sum(r.total_value for r in self.refuellings)

    @property
    def refuelling_volume_total(self) -> float:
        return sum(r.volume for r in self.refuellings)

    @property
    def refuelling_price_lowest(self) -> float | None:
        prices = [r.price for r in self.refuellings if r.price]
        return min(prices) if prices else None

    @property
    def refuelling_distance(self) -> int | None:
        if len(self.refuellings) < 2:
            return 0 if self.refuellings else None
        return self.refuellings[0].odometer - self.refuellings[1].odometer

    @property
    def _segments(self) -> list[tuple[float, float, float]]:
        """Full-tank to full-tank segments, the only spans with a known volume."""
        return calc.fuel_segments(
            [
                {
                    "odometro": r.odometer,
                    "volume": r.volume,
                    "valor_total": r.total_value,
                    "tanque_cheio": r.tank_full,
                    "esqueceu_anterior": r.forgot_previous,
                }
                for r in self.refuellings
            ],
            volume_fn=lambda row: row["volume"],
        )

    def _efficiency(self, distance: float, volume: float) -> float | None:
        return calc.efficiency(
            distance,
            volume,
            self.distance_unit_id,
            self.config.volume_unit_id,
            self.config.efficiency_id,
        )

    @property
    def refuelling_general_average(self) -> float | None:
        """Average over every closed full-tank segment.

        Fuel added before the first full tank is burnt over an unknown
        distance, so it is excluded — this is what the Drivvo app reports.
        """
        segments = self._segments
        if not segments:
            return None
        return self._efficiency(
            sum(item[0] for item in segments), sum(item[1] for item in segments)
        )

    @property
    def refuelling_last_average(self) -> float | None:
        """Average over the most recent closed full-tank segment."""
        segments = self._segments
        if not segments:
            return None
        distance, volume, _cost = segments[-1]
        return self._efficiency(distance, volume)

    @property
    def refuelling_cost_distance(self) -> float | None:
        """Fuel cost per unit of distance over the measured segments."""
        segments = self._segments
        if not segments:
            return None
        distance = sum(item[0] for item in segments)
        if distance <= 0:
            return None
        return sum(item[2] for item in segments) / distance

    @property
    def _volume_per_distance(self) -> float | None:
        """Raw volume burnt per unit of distance, in the account's own units."""
        segments = self._segments
        if not segments:
            return None
        distance = sum(item[0] for item in segments)
        if distance <= 0:
            return None
        return sum(item[1] for item in segments) / distance

    @property
    def last_refuelling(self) -> Refuelling | None:
        return self.refuellings[0] if self.refuellings else None

    # --- Tank estimate -----------------------------------------------------

    @property
    def fuel_remaining(self) -> float | None:
        """Volume left, estimated from the distance since the last full tank."""
        per_distance = self._volume_per_distance
        odometer = self.odometer
        if not self.tank_volume or not per_distance or not odometer:
            return None
        last_full = max(
            (r.odometer for r in self.refuellings if r.tank_full),
            default=0,
        )
        if not last_full:
            return None
        used = (odometer - last_full) * per_distance
        return max(0.0, min(self.tank_volume, self.tank_volume - used))

    @property
    def fuel_level(self) -> float | None:
        remaining = self.fuel_remaining
        if remaining is None or not self.tank_volume:
            return None
        return remaining / self.tank_volume * 100

    @property
    def fuel_range(self) -> float | None:
        remaining = self.fuel_remaining
        per_distance = self._volume_per_distance
        if remaining is None or not per_distance:
            return None
        return remaining / per_distance

    # --- Electric ----------------------------------------------------------

    @property
    def charge_energy(self) -> float | None:
        """Energy of the last charge, from the battery delta and pack size."""
        last = self.last_refuelling
        if (
            last is None
            or not self.tank_volume
            or last.battery_start is None
            or last.battery_end is None
        ):
            return None
        return (last.battery_end - last.battery_start) / 100 * self.tank_volume

    # --- Services / expenses / incomes -------------------------------------

    @property
    def last_service(self) -> Service | None:
        return self.services[0] if self.services else None

    @property
    def last_expense(self) -> Expense | None:
        return self.expenses[0] if self.expenses else None

    @property
    def last_income(self) -> Income | None:
        return self.incomes[0] if self.incomes else None

    @property
    def service_total(self) -> int:
        return len(self.services)

    @property
    def service_value_total(self) -> float:
        return sum(s.total_value for s in self.services)

    @property
    def expense_total(self) -> int:
        return len(self.expenses)

    @property
    def expense_value_total(self) -> float:
        return sum(e.total_value for e in self.expenses)

    @property
    def income_total(self) -> int:
        return len(self.incomes)

    @property
    def income_value_total(self) -> float:
        return sum(i.total_value for i in self.incomes)

    @property
    def cost_total(self) -> float:
        return (
            self.refuelling_value_total
            + self.service_value_total
            + self.expense_value_total
        )

    # --- Other modules -----------------------------------------------------

    @property
    def route_total(self) -> int:
        return len(self.routes)

    @property
    def route_distance_total(self) -> int:
        return sum(r.distance for r in self.routes)

    @property
    def reading_total(self) -> int:
        return len(self.readings)

    @property
    def last_reading(self) -> Reading | None:
        return self.readings[0] if self.readings else None

    @property
    def checklist_total(self) -> int:
        return len(self.checklists)

    @property
    def last_checklist(self) -> Checklist | None:
        return self.checklists[0] if self.checklists else None

    # --- Reminders ---------------------------------------------------------

    @property
    def reminders_total(self) -> int:
        return len(self.reminders)

    @property
    def reminders_overdue(self) -> int:
        return sum(1 for item in self.reminders if item.get("overdue"))

    @property
    def next_reminder(self) -> dict[str, Any] | None:
        return self.reminders[0] if self.reminders else None
