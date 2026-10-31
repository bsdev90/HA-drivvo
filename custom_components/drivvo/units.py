"""Custom units for Drivvo integration."""

from enum import StrEnum


class UnitOfFuelEfficiency(StrEnum):
    """Fuel efficiency units supported by Drivvo."""

    KILOMETERS_PER_LITER = "km/L"
    KILOMETERS_PER_GALLON_US = "km/gal"
    KILOMETERS_PER_GALLON_UK = "km/gal UK"
    LITERS_PER_100_KILOMETERS = "L/100km"
    GALLONS_US_PER_100_KILOMETERS = "gal/100km"
    GALLONS_UK_PER_100_KILOMETERS = "gal UK/100km"
    MILES_PER_LITER = "mi/L"
    MILES_PER_GALLON = "mpg"
    MILES_PER_GALLON_UK = "mpg UK"
    LITERS_PER_100_MILES = "L/100mi"
    GALLONS_US_PER_100_MILES = "gal/100mi"
    GALLONS_UK_PER_100_MILES = "gal UK/100mi"


class UnitOfDrivvoVolume(StrEnum):
    """Volume units supported by Drivvo."""

    LITERS = "L"
    GALLONS_US = "gal"
    GALLONS_UK = "gal UK"
    KILOWATT_HOURS = "kWh"
