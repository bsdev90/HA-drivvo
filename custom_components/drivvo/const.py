"""Constants for the Drivvo integration."""

from datetime import timedelta

DOMAIN = "drivvo"
ICON = "mdi:gas-station"
ATTRIBUTION = "Data provided by drivvo api"

SCAN_INTERVAL = timedelta(days=1)

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_MODEL = "model"
CONF_ID_VEHICLE = "id_vehicle"
CONF_VEHICLES = "vehicles"

# Legacy constants — retained for backwards compatibility with existing imports.
# New code should import from .api instead.
LOGIN_BASE_URL = "https://api.drivvo.com/autenticacao/login"
BASE_URL = "https://api.drivvo.com/"

# --- Account configuration (/configuracao) ---------------------------------
# unidade_distancia
DISTANCE_KILOMETERS = 1
DISTANCE_MILES = 2
DISTANCE_HOURS = 3

# unidade_medida (liquid fuels)
VOLUME_LITER = 1
VOLUME_GALLON_US = 2
VOLUME_GALLON_UK = 3

# eficiencia_combustivel
EFFICIENCY_KM_LITER = 1
EFFICIENCY_KM_GALLON_US = 2
EFFICIENCY_KM_GALLON_UK = 3
EFFICIENCY_LITER_100KM = 4
EFFICIENCY_GALLON_US_100KM = 5
EFFICIENCY_GALLON_UK_100KM = 6
EFFICIENCY_MILE_LITER = 7
EFFICIENCY_MILE_GALLON_US = 8
EFFICIENCY_MILE_GALLON_UK = 9
EFFICIENCY_LITER_100MI = 10
EFFICIENCY_GALLON_US_100MI = 11
EFFICIENCY_GALLON_UK_100MI = 12

# id_tipo_combustivel
FUEL_TYPE_ELECTRIC = 4

GALLON_US_PER_LITER = 0.264172
GALLON_UK_PER_LITER = 0.219969
KM_PER_MILE = 1.609344
MILE_PER_KM = 0.621371

# --- History modules -------------------------------------------------------
# Read as /veiculo/{id}/<module>/web, written as POST /<module>.
MODULE_REFUELLING = "abastecimento"
MODULE_SERVICE = "servico"
MODULE_EXPENSE = "despesa"
MODULE_INCOME = "receita"
MODULE_ROUTE = "percurso"
MODULE_READING = "leitura"
MODULE_REMINDER = "lembrete"
MODULE_CHECKLIST = "checklist"

# --- Services --------------------------------------------------------------
SERVICE_ADD_REFUELLING = "add_refuelling"
SERVICE_ADD_READING = "add_reading"
SERVICE_ADD_EXPENSE = "add_expense"
SERVICE_ADD_SERVICE = "add_service"
SERVICE_ADD_INCOME = "add_income"
SERVICE_REFRESH = "refresh"

ATTR_VEHICLE_ID = "vehicle_id"
ATTR_ODOMETER = "odometer"
ATTR_DATE = "date"
ATTR_TOTAL_VALUE = "total_value"
ATTR_PRICE = "price"
ATTR_VOLUME = "volume"
ATTR_FULL_TANK = "full_tank"
ATTR_FUEL_NAME = "fuel"
ATTR_STATION = "station"
ATTR_TYPE = "type"
ATTR_VALUE = "value"
ATTR_PLACE = "place"
ATTR_NOTE = "note"
