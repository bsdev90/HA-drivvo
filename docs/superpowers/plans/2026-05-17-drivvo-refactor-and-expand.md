# Drivvo Integration Refactor + Expansion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the HA-Drivvo integration into a maintainable, async, testable codebase; expose service/expense data already fetched but currently discarded; add HA services for write-back (add refuelling/service/expense from automations); land a baseline test suite + diagnostics.

**Architecture:**
- Extract a dedicated async `DrivvoApiClient` (aiohttp) with token caching and typed responses, replacing inline `requests` calls in `__init__.py`.
- Replace the per-vehicle one-off `DataUpdateCoordinator` with a typed `DrivvoDataUpdateCoordinator` per vehicle that owns the client and exposes domain dataclasses for refuelling, service, expense.
- New `services.yaml` + `async_register` entries expose `drivvo.add_refuelling`, `drivvo.add_service`, `drivvo.add_expense` HA services that call the client and trigger a coordinator refresh.
- Test harness based on `pytest-homeassistant-custom-component` with `aioresponses` for the HTTP layer.

**Tech Stack:** Python 3.12+, Home Assistant `DataUpdateCoordinator`, `aiohttp` (HA's `async_get_clientsession`), `voluptuous`, `pytest`, `pytest-homeassistant-custom-component`, `aioresponses`.

**Out of scope:**
- New auth method (still email + md5 password — Drivvo API requirement).
- Localization beyond English + Portuguese for new strings (community PRs cover others).
- UI cards / Lovelace.

**Drivvo API endpoints in use (verified):**
- `POST https://api.drivvo.com/autenticacao/login` → `{token}` (body: `{email, senha}` with md5 password)
- `GET /veiculo/web` → vehicle list
- `GET /veiculo/{id}` → vehicle detail
- `GET /veiculo/{id}/abastecimento/web` → refuellings
- `GET /veiculo/{id}/servico/web` → services
- `GET /veiculo/{id}/despesa/web` → expenses
- `GET /configuracao` → user config (currency)

**Drivvo write endpoints (assumed — Task 13 verifies before use):**
- `POST /veiculo/{id}/abastecimento`
- `POST /veiculo/{id}/servico`
- `POST /veiculo/{id}/despesa`

**Phasing:**
- Phase A (Tasks 1–7): API client + coordinator refactor. After this phase the integration must behave identically to today for end users — no new entities, no removed entities, same names.
- Phase B (Tasks 8–11): Service + expense sensors.
- Phase C (Tasks 12–15): HA write services.
- Phase D (Tasks 16–18): Tests, diagnostics, polish.

---

## File Structure

After this plan, `custom_components/drivvo/` will look like:

```
custom_components/drivvo/
├── __init__.py              # ConfigEntry setup/unload/migrate ONLY (~80 lines)
├── api.py                   # NEW: DrivvoApiClient (aiohttp) + DrivvoApiError
├── coordinator.py           # NEW: DrivvoDataUpdateCoordinator
├── models.py                # NEW: dataclasses (VehicleData, Refuelling, Service, Expense)
├── config_flow.py           # Uses api.py instead of inline requests
├── const.py                 # Adds new keys: SERVICE_*, EXPENSE_*, SERVICES_SCHEMA keys
├── sensor.py                # Uses coordinator only; no auth/HTTP here
├── sensors.py               # Existing refuelling descriptions + new service/expense descriptions
├── services.py              # NEW: register drivvo.add_refuelling / add_service / add_expense
├── services.yaml            # NEW: HA service descriptions
├── diagnostics.py           # NEW: async_get_config_entry_diagnostics
├── manifest.json            # Bump version + add quality_scale
└── translations/*.json      # Add strings for new sensors + services
```

**Responsibilities:**
- `api.py` — HTTP only. No HA imports beyond `aiohttp_client.async_get_clientsession`. Raises `DrivvoAuthError`, `DrivvoApiError`.
- `coordinator.py` — Owns the client, holds token, calls API methods, returns `VehicleData`.
- `models.py` — Pure dataclasses. No I/O.
- `__init__.py` — `async_setup_entry` builds coordinator + client, forwards platforms, registers services on first entry.
- `sensor.py` — Thin entities over the coordinator.
- `services.py` — Glue between HA service calls and the client.

```
tests/
├── __init__.py
├── conftest.py              # Common fixtures: hass, config entry, aioresponses
├── fixtures/
│   ├── login_ok.json
│   ├── vehicle_list.json
│   ├── vehicle_detail.json
│   ├── refuellings.json
│   ├── services.json
│   ├── expenses.json
│   └── configuracao.json
├── test_api.py
├── test_coordinator.py
├── test_config_flow.py
├── test_sensor.py
└── test_services.py
```

---

## Pre-flight

### Task 0: Branch + dev dependencies

**Files:** none yet (repo setup).

- [ ] **Step 1: Create feature branch**

```bash
git checkout -b feat/refactor-and-expand
```

- [ ] **Step 2: Add dev dependency file for tests**

Create `requirements_test.txt`:

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-homeassistant-custom-component>=0.13
aioresponses>=0.7
```

- [ ] **Step 3: Add `tests/` package marker**

Create `tests/__init__.py` (empty).

- [ ] **Step 4: Commit**

```bash
git add requirements_test.txt tests/__init__.py
git commit -m "chore: scaffold test harness"
```

---

## Phase A — API Client + Coordinator Refactor

### Task 1: Domain models

**Files:**
- Create: `custom_components/drivvo/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""Tests for Drivvo domain models."""
from custom_components.drivvo.models import (
    Refuelling,
    Service,
    Expense,
    VehicleData,
)


def test_refuelling_from_api_handles_null_volume_and_price():
    api_row = {
        "data": "2025-05-01 10:00:00",
        "odometro": 12345,
        "volume": None,
        "preco": None,
        "valor_total": 200.0,
        "combustivel": "Gasolina",
        "tipo_motivo": 1,
        "tanque_cheio": True,
        "posto_combustivel": {"nome": "Shell"},
    }

    r = Refuelling.from_api(api_row)

    assert r.odometer == 12345
    assert r.total_value == 200.0
    assert r.volume == 0  # null volume + null price => 0, not crash


def test_vehicle_data_identification_prefers_name():
    v = VehicleData(
        id=1,
        name="My Car",
        placa="ABC1234",
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[],
        services=[],
        expenses=[],
    )
    assert v.identification == "My Car"


def test_vehicle_data_identification_falls_back_to_placa_then_marca_modelo():
    v = VehicleData(
        id=2,
        name=None,
        placa="XYZ9999",
        manufacturer="VW",
        model="Gol",
        distance_unit="km",
        currency="R$",
        refuellings=[], services=[], expenses=[],
    )
    assert v.identification == "XYZ9999"

    v2 = VehicleData(
        id=3, name=None, placa=None,
        manufacturer="VW", model="Gol",
        distance_unit="km", currency="R$",
        refuellings=[], services=[], expenses=[],
    )
    assert v2.identification == "VW/Gol"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: ImportError / module not found.

- [ ] **Step 3: Create `custom_components/drivvo/models.py`**

```python
"""Domain models for the Drivvo integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _safe_volume(row: dict[str, Any]) -> float:
    volume = row.get("volume") or 0
    if volume:
        return float(volume)
    price = row.get("preco") or 0
    total = row.get("valor_total") or 0
    if price:
        return float(total) / float(price)
    return 0.0


@dataclass(frozen=True)
class Refuelling:
    date: str
    odometer: int
    volume: float
    price: float
    total_value: float
    fuel_type: str | None
    reason: int | None
    tank_full: bool
    station: str | None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> "Refuelling":
        station = None
        st = row.get("posto_combustivel")
        if isinstance(st, dict):
            station = st.get("nome")
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            volume=_safe_volume(row),
            price=float(row.get("preco") or 0),
            total_value=float(row.get("valor_total") or 0),
            fuel_type=row.get("combustivel"),
            reason=row.get("tipo_motivo"),
            tank_full=bool(row.get("tanque_cheio")),
            station=station,
        )


@dataclass(frozen=True)
class Service:
    date: str
    odometer: int
    total_value: float
    description: str | None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> "Service":
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            total_value=float(row.get("valor_total") or 0),
            description=row.get("descricao") or row.get("tipo_servico"),
        )


@dataclass(frozen=True)
class Expense:
    date: str
    odometer: int
    total_value: float
    description: str | None
    type: str | None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> "Expense":
        return cls(
            date=row.get("data"),
            odometer=row.get("odometro") or 0,
            total_value=float(row.get("valor_total") or 0),
            description=row.get("descricao"),
            type=row.get("tipo_despesa"),
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

    @property
    def identification(self) -> str:
        if self.name:
            return self.name
        if self.placa:
            return self.placa
        return f"{self.manufacturer}/{self.model}"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/drivvo/models.py tests/test_models.py
git commit -m "feat(models): add typed domain models for vehicle/refuelling/service/expense"
```

---

### Task 2: API client — auth

**Files:**
- Create: `custom_components/drivvo/api.py`
- Test: `tests/test_api.py`
- Create: `tests/fixtures/login_ok.json`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create fixture `tests/fixtures/login_ok.json`**

```json
{"token": "fake-token-123"}
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
"""Shared test fixtures."""
import json
from pathlib import Path

import pytest
from aioresponses import aioresponses


FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m
```

- [ ] **Step 3: Write failing test**

Create `tests/test_api.py`:

```python
"""Tests for DrivvoApiClient."""
import pytest
from aiohttp import ClientSession

from custom_components.drivvo.api import (
    DrivvoApiClient,
    DrivvoAuthError,
)
from tests.conftest import load


@pytest.mark.asyncio
async def test_login_returns_token(mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
        status=200,
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "user@example.com", "secret")
        token = await client.login()

    assert token == "fake-token-123"
    assert client.token == "fake-token-123"


@pytest.mark.asyncio
async def test_login_raises_on_401(mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        status=401,
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "user@example.com", "wrong")
        with pytest.raises(DrivvoAuthError):
            await client.login()


@pytest.mark.asyncio
async def test_login_md5_hashes_password(mock_aioresponse):
    """Drivvo expects md5-hashed password in 'senha' field."""
    seen = {}

    def callback(url, **kwargs):
        seen["body"] = kwargs["json"]
        from aioresponses.core import CallbackResult
        return CallbackResult(status=200, payload={"token": "t"})

    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        callback=callback,
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "user@example.com", "secret")
        await client.login()

    assert seen["body"]["email"] == "user@example.com"
    # md5("secret") == "5ebe2294ecd0e0f08eab7690d2a6ee69"
    assert seen["body"]["senha"] == "5ebe2294ecd0e0f08eab7690d2a6ee69"
```

- [ ] **Step 4: Run test to verify it fails**

```bash
pytest tests/test_api.py -v
```

Expected: ImportError on `from custom_components.drivvo.api import ...`.

- [ ] **Step 5: Implement `custom_components/drivvo/api.py`**

```python
"""Async client for the Drivvo private API."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.drivvo.com"
LOGIN_URL = f"{BASE_URL}/autenticacao/login"


class DrivvoApiError(Exception):
    """Raised when the Drivvo API returns an unexpected response."""


class DrivvoAuthError(DrivvoApiError):
    """Raised when credentials are rejected (HTTP 401/403)."""


def _default_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "App-Platform": "HA-Drivvo",
        "App-Version": "1",
        "Content-Type": "application/json",
        "Origin": "https://web.drivvo.com",
        "Referer": "https://web.drivvo.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        ),
    }


class DrivvoApiClient:
    """Async wrapper over the Drivvo private API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password_md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
        self.token: str | None = None

    async def login(self) -> str:
        async with self._session.post(
            LOGIN_URL,
            json={"email": self._email, "senha": self._password_md5},
            headers=_default_headers(),
        ) as resp:
            if resp.status in (401, 403):
                raise DrivvoAuthError(f"Login rejected: HTTP {resp.status}")
            if resp.status >= 400:
                raise DrivvoApiError(f"Login failed: HTTP {resp.status}")
            data = await resp.json()
            token = data.get("token")
            if not token:
                raise DrivvoApiError("Login response missing 'token'")
            self.token = token
            return token
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_api.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add custom_components/drivvo/api.py tests/test_api.py tests/conftest.py tests/fixtures/login_ok.json
git commit -m "feat(api): add async DrivvoApiClient with login"
```

---

### Task 3: API client — GET endpoints

**Files:**
- Modify: `custom_components/drivvo/api.py`
- Modify: `tests/test_api.py`
- Create: `tests/fixtures/vehicle_list.json`, `vehicle_detail.json`, `refuellings.json`, `services.json`, `expenses.json`, `configuracao.json`

- [ ] **Step 1: Create fixtures**

`tests/fixtures/vehicle_list.json`:
```json
[
  {
    "id_veiculo": 100,
    "ativo": true,
    "nome": "My Car",
    "placa": "ABC1234",
    "marca": "VW",
    "modelo": "Gol",
    "unidade_distancia": 1
  },
  {
    "id_veiculo": 200,
    "ativo": false,
    "nome": "Old Car",
    "placa": null,
    "marca": "Fiat",
    "modelo": "Uno",
    "unidade_distancia": 1
  }
]
```

`tests/fixtures/vehicle_detail.json`:
```json
{
  "id_veiculo": 100,
  "nome": "My Car",
  "placa": "ABC1234",
  "marca": "VW",
  "modelo": "Gol",
  "unidade_distancia": 1
}
```

`tests/fixtures/refuellings.json`:
```json
[
  {
    "data": "2025-05-10 12:00:00",
    "odometro": 12500,
    "volume": 30.0,
    "preco": 6.0,
    "valor_total": 180.0,
    "combustivel": "Gasolina",
    "tipo_motivo": 1,
    "tanque_cheio": true,
    "posto_combustivel": {"nome": "Shell"}
  },
  {
    "data": "2025-05-01 12:00:00",
    "odometro": 12200,
    "volume": 28.0,
    "preco": 5.8,
    "valor_total": 162.4,
    "combustivel": "Gasolina",
    "tipo_motivo": 1,
    "tanque_cheio": true,
    "posto_combustivel": {"nome": "Shell"}
  }
]
```

`tests/fixtures/services.json`:
```json
[
  {"data": "2025-04-15 08:00:00", "odometro": 12000, "valor_total": 350.0, "descricao": "Oil change"}
]
```

`tests/fixtures/expenses.json`:
```json
[
  {"data": "2025-05-05 09:00:00", "odometro": 12300, "valor_total": 80.0, "descricao": "Toll", "tipo_despesa": "Pedágio"}
]
```

`tests/fixtures/configuracao.json`:
```json
[{"formato_valor": "R$"}]
```

- [ ] **Step 2: Add failing tests in `tests/test_api.py`** (append):

```python
@pytest.mark.asyncio
async def test_get_vehicles(mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/veiculo/web",
        payload=load("vehicle_list.json"),
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        await client.login()
        vehicles = await client.get_vehicles()

    assert len(vehicles) == 2
    assert vehicles[0]["id_veiculo"] == 100


@pytest.mark.asyncio
async def test_get_vehicle_aggregates_all_endpoints(mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/veiculo/100",
        payload=load("vehicle_detail.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/veiculo/100/abastecimento/web",
        payload=load("refuellings.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/veiculo/100/servico/web",
        payload=load("services.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/veiculo/100/despesa/web",
        payload=load("expenses.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/configuracao",
        payload=load("configuracao.json"),
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        await client.login()
        vehicle = await client.get_vehicle(100)

    assert vehicle.id == 100
    assert vehicle.name == "My Car"
    assert vehicle.distance_unit == "km"
    assert vehicle.currency == "R$"
    assert len(vehicle.refuellings) == 2
    assert vehicle.refuellings[0].date == "2025-05-10 12:00:00"  # sorted desc
    assert len(vehicle.services) == 1
    assert len(vehicle.expenses) == 1


@pytest.mark.asyncio
async def test_get_requires_token(mock_aioresponse):
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        with pytest.raises(DrivvoApiError, match="not authenticated"):
            await client.get_vehicles()
```

- [ ] **Step 3: Run tests to see them fail**

```bash
pytest tests/test_api.py -v
```

Expected: 3 new tests fail (AttributeError on `get_vehicles`/`get_vehicle`).

- [ ] **Step 4: Extend `api.py`** — append below `login`:

```python
    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            raise DrivvoApiError("Client is not authenticated; call login() first")
        h = _default_headers()
        h["x-token"] = self.token
        return h

    async def _get_json(self, path: str) -> Any:
        url = f"{BASE_URL}{path}"
        async with self._session.get(url, headers=self._auth_headers()) as resp:
            if resp.status in (401, 403):
                raise DrivvoAuthError(f"Token rejected for {path}")
            if resp.status >= 400:
                raise DrivvoApiError(f"GET {path} failed: HTTP {resp.status}")
            return await resp.json()

    async def get_vehicles(self) -> list[dict[str, Any]]:
        return await self._get_json("/veiculo/web")

    async def get_vehicle(self, vehicle_id: int) -> "VehicleData":
        from .models import (
            Expense,
            Refuelling,
            Service,
            VehicleData,
        )

        detail = await self._get_json(f"/veiculo/{vehicle_id}")
        refuel_rows = await self._get_json(f"/veiculo/{vehicle_id}/abastecimento/web")
        service_rows = await self._get_json(f"/veiculo/{vehicle_id}/servico/web")
        expense_rows = await self._get_json(f"/veiculo/{vehicle_id}/despesa/web")
        config = await self._get_json("/configuracao")

        currency: str | None = None
        if isinstance(config, list) and config and isinstance(config[0], dict):
            currency = config[0].get("formato_valor")

        unit_code = detail.get("unidade_distancia")
        distance_unit = "km" if unit_code == 1 else "mi" if unit_code == 2 else "km"

        return VehicleData(
            id=vehicle_id,
            name=detail.get("nome") or None,
            placa=detail.get("placa") or None,
            manufacturer=detail.get("marca", ""),
            model=detail.get("modelo", ""),
            distance_unit=distance_unit,
            currency=currency,
            refuellings=sorted(
                (Refuelling.from_api(r) for r in (refuel_rows or [])),
                key=lambda r: r.date or "",
                reverse=True,
            ),
            services=sorted(
                (Service.from_api(r) for r in (service_rows or [])),
                key=lambda r: r.date or "",
                reverse=True,
            ),
            expenses=sorted(
                (Expense.from_api(r) for r in (expense_rows or [])),
                key=lambda r: r.date or "",
                reverse=True,
            ),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add custom_components/drivvo/api.py tests/test_api.py tests/fixtures/
git commit -m "feat(api): add get_vehicles + get_vehicle aggregation"
```

---

### Task 4: Coordinator

**Files:**
- Create: `custom_components/drivvo/coordinator.py`
- Test: `tests/test_coordinator.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_coordinator.py`:

```python
"""Tests for DrivvoDataUpdateCoordinator."""
import pytest
from aiohttp import ClientSession
from unittest.mock import AsyncMock, MagicMock

from custom_components.drivvo.coordinator import DrivvoDataUpdateCoordinator
from custom_components.drivvo.api import DrivvoApiClient, DrivvoAuthError
from custom_components.drivvo.models import VehicleData
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.mark.asyncio
async def test_coordinator_logs_in_then_fetches_vehicle(hass):
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.login = AsyncMock(return_value="tok")
        client.get_vehicle = AsyncMock(
            return_value=VehicleData(
                id=1, name="X", placa=None,
                manufacturer="VW", model="Gol",
                distance_unit="km", currency="R$",
            )
        )

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        data = await coord._async_update_data()

    assert data.id == 1
    client.login.assert_awaited_once()
    client.get_vehicle.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_coordinator_reuses_token_on_subsequent_refresh(hass):
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "existing"
        client.login = AsyncMock(return_value="existing")
        client.get_vehicle = AsyncMock(
            return_value=VehicleData(
                id=1, name="X", placa=None,
                manufacturer="VW", model="Gol",
                distance_unit="km", currency="R$",
            )
        )

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        await coord._async_update_data()

    client.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_retries_login_on_auth_error(hass):
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        client.token = "stale"
        calls = []

        async def fake_get_vehicle(_):
            if not calls:
                calls.append(1)
                raise DrivvoAuthError("expired")
            return VehicleData(
                id=1, name="X", placa=None,
                manufacturer="VW", model="Gol",
                distance_unit="km", currency="R$",
            )

        client.get_vehicle = fake_get_vehicle
        client.login = AsyncMock(return_value="fresh")

        coord = DrivvoDataUpdateCoordinator(hass, client, vehicle_id=1)
        data = await coord._async_update_data()

    assert data.id == 1
    client.login.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_coordinator.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `coordinator.py`**

```python
"""Drivvo data update coordinator."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import DrivvoApiClient, DrivvoApiError, DrivvoAuthError
from .const import DOMAIN
from .models import VehicleData

_LOGGER = logging.getLogger(__name__)


class DrivvoDataUpdateCoordinator(DataUpdateCoordinator[VehicleData]):
    """Per-vehicle coordinator. Reuses one client (and its token) per config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DrivvoApiClient,
        vehicle_id: int,
        update_interval: timedelta = timedelta(days=1),
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_vehicle_{vehicle_id}",
            update_interval=update_interval,
        )
        self.client = client
        self.vehicle_id = vehicle_id

    async def _async_update_data(self) -> VehicleData:
        if self.client.token is None:
            await self.client.login()

        try:
            return await self.client.get_vehicle(self.vehicle_id)
        except DrivvoAuthError:
            self.client.token = None
            await self.client.login()
            try:
                return await self.client.get_vehicle(self.vehicle_id)
            except DrivvoApiError as err:
                raise UpdateFailed(str(err)) from err
        except DrivvoApiError as err:
            raise UpdateFailed(str(err)) from err
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_coordinator.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/drivvo/coordinator.py tests/test_coordinator.py
git commit -m "feat(coordinator): add DrivvoDataUpdateCoordinator with token reuse + auth retry"
```

---

### Task 5: Rewrite `__init__.py` to use the new client + coordinator

**Files:**
- Modify: `custom_components/drivvo/__init__.py` (full rewrite)
- Modify: `custom_components/drivvo/config_flow.py` (use new client)
- Modify: `custom_components/drivvo/const.py`

- [ ] **Step 1: Replace `const.py` (additive — keep existing keys)**

```python
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
```

- [ ] **Step 2: Replace `__init__.py` body** (delete current contents, write):

```python
"""Drivvo integration setup."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DrivvoApiClient, DrivvoApiError, DrivvoAuthError
from .const import (
    CONF_EMAIL,
    CONF_ID_VEHICLE,
    CONF_PASSWORD,
    CONF_VEHICLES,
    DOMAIN,
    SCAN_INTERVAL,
)
from .coordinator import DrivvoDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = DrivvoApiClient(
        session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )

    try:
        await client.login()
    except DrivvoAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DrivvoApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinators: dict[int, DrivvoDataUpdateCoordinator] = {}
    for vehicle_id in entry.data.get(CONF_VEHICLES, []):
        coord = DrivvoDataUpdateCoordinator(
            hass, client, int(vehicle_id), update_interval=SCAN_INTERVAL
        )
        await coord.async_config_entry_first_refresh()
        coordinators[int(vehicle_id)] = coord

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinators": coordinators,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Migrating from version %s", entry.version)
    if entry.version == 1:
        data = {
            CONF_EMAIL: entry.data.get(CONF_EMAIL),
            CONF_PASSWORD: entry.data.get(CONF_PASSWORD),
            CONF_VEHICLES: [entry.data.get(CONF_ID_VEHICLE)],
        }
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    _LOGGER.info("Migration to version %s successful", entry.version)
    return True
```

- [ ] **Step 3: Update `config_flow.py`** to use the new client.

Replace the `from . import auth, get_vehicles` import + every call. Inline auth/list helpers:

In `config_flow.py`, replace:
```python
from . import auth, get_vehicles
```
with:
```python
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import DrivvoApiClient, DrivvoApiError, DrivvoAuthError
```

Replace every call `await auth(hass=..., user=..., password=...)` with:
```python
session = async_get_clientsession(self.hass)
client = DrivvoApiClient(session, email=user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD])
try:
    await client.login()
    auth_ok = True
except DrivvoAuthError:
    auth_ok = False
```

Replace `vehicles = await get_vehicles(self.hass, self.token)` with:
```python
vehicles = await client.get_vehicles()
```
(reusing the client created during the auth step — store as `self.client` between steps).

The `async_step_user`, `async_step_vehicle`, `async_step_reauth_confirm`, and `DrivvoOptionsFlowHandler.async_step_init` methods each call `auth()`/`get_vehicles()`. Update each one to instantiate a client locally. Self-review: walk the file top-to-bottom and ensure every reference to `auth` or `get_vehicles` is replaced.

- [ ] **Step 4: Update `sensor.py`** to consume the coordinator from hass.data:

Replace the `for vehicle in config[CONF_VEHICLES]:` block in `async_setup_entry` with:

```python
store = hass.data[DOMAIN][config_entry.entry_id]
coordinators: dict[int, DrivvoDataUpdateCoordinator] = store["coordinators"]

entities = []
for vehicle_id, coordinator in coordinators.items():
    vehicle_data = coordinator.data
    if vehicle_data is None:
        continue
    for description in SENSOR_TYPES:
        if description.key == "vehicle":
            entities.append(
                DrivvoSensorEntity(
                    coordinator, description, vehicle_data.id,
                    vehicle_data.identification, vehicle_data.model,
                )
            )
        else:
            entities.append(
                DrivvoSensorEntity(
                    coordinator, description, vehicle_data.id,
                    vehicle_data.identification,
                )
            )

async_add_entities(entities)
```

Remove imports of `get_data_vehicle` from `.` — no longer exported. Add `from .coordinator import DrivvoDataUpdateCoordinator`.

- [ ] **Step 5: Run tests + a HA syntax check**

```bash
pytest tests/ -v
python -c "import ast; ast.parse(open('custom_components/drivvo/__init__.py').read())"
python -c "import ast; ast.parse(open('custom_components/drivvo/sensor.py').read())"
python -c "import ast; ast.parse(open('custom_components/drivvo/config_flow.py').read())"
```

Expected: all tests still pass; no SyntaxError from ast.parse.

- [ ] **Step 6: Commit**

```bash
git add custom_components/drivvo/__init__.py custom_components/drivvo/const.py custom_components/drivvo/sensor.py custom_components/drivvo/config_flow.py
git commit -m "refactor: route setup/sensor/config_flow through new API client + coordinator"
```

---

### Task 6: Compute derived sensor values from `VehicleData`

The old `get_data_vehicle` computed totals (averages, total volume, lowest price, etc.) inline. The new `VehicleData` only holds raw lists. Move computations onto `VehicleData` as `@property` so sensor `value_fn`s stay one-line lambdas.

**Files:**
- Modify: `custom_components/drivvo/models.py`
- Modify: `tests/test_models.py`
- Modify: `custom_components/drivvo/sensors.py`

- [ ] **Step 1: Write failing tests** — append to `tests/test_models.py`:

```python
def _refuelling(date, odo, vol, price, full=True):
    return Refuelling(
        date=date, odometer=odo, volume=vol, price=price,
        total_value=vol * price, fuel_type="Gasolina",
        reason=1, tank_full=full, station="Shell",
    )


def test_vehicle_data_totals_and_averages():
    v = VehicleData(
        id=1, name="X", placa=None,
        manufacturer="VW", model="Gol",
        distance_unit="km", currency="R$",
        refuellings=[
            _refuelling("2025-05-10 12:00:00", 12500, 30.0, 6.0, True),
            _refuelling("2025-05-01 12:00:00", 12200, 28.0, 5.8, True),
            _refuelling("2025-04-20 12:00:00", 12000, 25.0, 5.5, True),
        ],
    )
    assert v.refuelling_total == 3
    assert v.refuelling_value_total == pytest.approx(30*6 + 28*5.8 + 25*5.5)
    assert v.refuelling_volume_total == pytest.approx(83.0)
    assert v.refuelling_price_lowest == 5.5
    # general average = (12500 - 12000) / 83
    assert v.refuelling_general_average == pytest.approx(500 / 83)
    # last_average across two consecutive full tanks: (12500 - 12200) / 30
    assert v.refuelling_last_average == pytest.approx(300 / 30)
    assert v.refuelling_distance == 300


def test_vehicle_data_odometer_from_latest_event():
    v = VehicleData(
        id=1, name="X", placa=None,
        manufacturer="VW", model="Gol",
        distance_unit="km", currency="R$",
        refuellings=[_refuelling("2025-05-10 12:00:00", 12500, 30, 6)],
        services=[Service(date="2025-05-12 09:00:00", odometer=12600, total_value=200, description="Wash")],
    )
    assert v.odometer == 12600
    assert v.odometer_date == "2025-05-12 09:00:00"
```

- [ ] **Step 2: Run tests to see them fail**

```bash
pytest tests/test_models.py -v
```

Expected: AttributeError on `refuelling_total`, etc.

- [ ] **Step 3: Add properties to `VehicleData`** in `models.py`:

```python
    @property
    def odometer(self) -> int | None:
        events: list[tuple[str, int]] = []
        for r in self.refuellings:
            events.append((r.date or "", r.odometer))
        for s in self.services:
            events.append((s.date or "", s.odometer))
        for e in self.expenses:
            events.append((e.date or "", e.odometer))
        if not events:
            return None
        events.sort(key=lambda t: t[0], reverse=True)
        return events[0][1]

    @property
    def odometer_date(self) -> str | None:
        events: list[tuple[str, int]] = []
        for r in self.refuellings:
            events.append((r.date or "", r.odometer))
        for s in self.services:
            events.append((s.date or "", s.odometer))
        for e in self.expenses:
            events.append((e.date or "", e.odometer))
        if not events:
            return None
        events.sort(key=lambda t: t[0], reverse=True)
        return events[0][0] or None

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
    def refuelling_general_average(self) -> float | None:
        if len(self.refuellings) < 2 or self.refuelling_volume_total <= 0:
            return None
        span = self.refuellings[0].odometer - self.refuellings[-1].odometer
        return span / self.refuelling_volume_total

    @property
    def refuelling_last_average(self) -> float | None:
        if len(self.refuellings) < 2:
            return None
        odo_init: int | None = None
        odo_old: int | None = None
        volume = 0.0
        for r in self.refuellings:
            if r.tank_full and odo_init is None:
                odo_init = r.odometer
                continue
            if odo_init is None:
                continue
            if r.tank_full and r.odometer != odo_init:
                odo_old = r.odometer
                break
            volume += r.volume
        if odo_old is None or volume <= 0:
            return None
        return (self.refuellings[0].odometer - odo_old) / volume

    @property
    def last_refuelling(self) -> Refuelling | None:
        return self.refuellings[0] if self.refuellings else None

    @property
    def last_service(self) -> Service | None:
        return self.services[0] if self.services else None

    @property
    def last_expense(self) -> Expense | None:
        return self.expenses[0] if self.expenses else None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_models.py -v
```

Expected: all passing.

- [ ] **Step 5: Update `sensors.py`** — point existing `value_fn`s at the new properties / accessor chain.

For each refuelling sensor description, replace the lambda:
- `refuelling_total` → `lambda d: d.refuelling_total`
- `refuelling_value_total` → `lambda d: d.refuelling_value_total`
- `refuelling_volume_total` → `lambda d: d.refuelling_volume_total`
- `refuelling_price_lowest` → `lambda d: d.refuelling_price_lowest`
- `refuelling_distance` → `lambda d: d.refuelling_distance`
- `refuelling_general_average` → `lambda d: d.refuelling_general_average`
- `refuelling_last_average` → `lambda d: d.refuelling_last_average`
- `refuelling_date` → `lambda d: d.last_refuelling.date if d.last_refuelling else None`
- `refuelling_odometer` → `lambda d: d.last_refuelling.odometer if d.last_refuelling else None`
- `refuelling_station` → `lambda d: d.last_refuelling.station if d.last_refuelling else None`
- `refuelling_type` → `lambda d: d.last_refuelling.fuel_type if d.last_refuelling else None`
- `refuelling_reason` → `lambda d: d.last_refuelling.reason if d.last_refuelling else None`
- `refuelling_value` → `lambda d: d.last_refuelling.total_value if d.last_refuelling else None`
- `refuelling_price` → `lambda d: d.last_refuelling.price if d.last_refuelling else None`
- `refuelling_volume` → `lambda d: d.last_refuelling.volume if d.last_refuelling else None`
- `refuelling_tank_full` → `lambda d: d.last_refuelling.tank_full if d.last_refuelling else None`
- `odometer` → `lambda d: d.odometer`
- `odometer_date` → `lambda d: d.odometer_date`

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add custom_components/drivvo/models.py custom_components/drivvo/sensors.py tests/test_models.py
git commit -m "refactor(models): move sensor computations onto VehicleData properties"
```

---

### Task 7: Delete the old `get_data_vehicle` / `auth` / `get_vehicles` helpers

**Files:**
- Modify: `custom_components/drivvo/__init__.py`

- [ ] **Step 1: Verify no remaining callers**

```bash
grep -rn "get_data_vehicle\|from . import auth\|from . import get_vehicles" custom_components/ tests/ || echo "NONE"
```

Expected: `NONE` (or only comments).

- [ ] **Step 2: Confirm `__init__.py` already has the new content from Task 5.**

If the legacy `auth` / `get_vehicles` / `get_data_vehicle` / `DrivvoDataVehicle` / `get_default_headers` are still present at the bottom of the file from a partial edit, remove them now. The file must end at `async_migrate_entry`.

- [ ] **Step 3: Run tests + ast.parse**

```bash
pytest tests/ -v
python -c "import ast; ast.parse(open('custom_components/drivvo/__init__.py').read())"
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add custom_components/drivvo/__init__.py
git commit -m "refactor: drop legacy sync helpers from __init__.py"
```

---

## Phase B — Service + Expense Sensors

### Task 8: Service sensors

**Files:**
- Modify: `custom_components/drivvo/sensors.py`
- Modify: `custom_components/drivvo/translations/en.json`
- Modify: `custom_components/drivvo/translations/pt-BR.json`
- Test: `tests/test_sensor.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_sensor.py`:

```python
"""Tests for Drivvo sensor descriptions."""
import pytest
from custom_components.drivvo.models import VehicleData, Service, Expense
from custom_components.drivvo.sensors import SENSOR_TYPES


def _vehicle_with_services_and_expenses() -> VehicleData:
    return VehicleData(
        id=1, name="X", placa=None,
        manufacturer="VW", model="Gol",
        distance_unit="km", currency="R$",
        services=[
            Service(date="2025-05-12 09:00:00", odometer=12600, total_value=200.0, description="Oil change"),
            Service(date="2025-04-12 09:00:00", odometer=12100, total_value=150.0, description="Tire rotation"),
        ],
        expenses=[
            Expense(date="2025-05-10 09:00:00", odometer=12500, total_value=80.0, description="Toll", type="Pedágio"),
        ],
    )


def _find(key):
    for s in SENSOR_TYPES:
        if s.key == key:
            return s
    raise KeyError(key)


def test_service_total_and_last_sensors():
    v = _vehicle_with_services_and_expenses()
    assert _find("service_total").value_fn(v) == 2
    assert _find("service_value_total").value_fn(v) == pytest.approx(350.0)
    assert _find("service_date").value_fn(v) == "2025-05-12 09:00:00"
    assert _find("service_odometer").value_fn(v) == 12600
    assert _find("service_value").value_fn(v) == pytest.approx(200.0)
    assert _find("service_description").value_fn(v) == "Oil change"


def test_expense_total_and_last_sensors():
    v = _vehicle_with_services_and_expenses()
    assert _find("expense_total").value_fn(v) == 1
    assert _find("expense_value_total").value_fn(v) == pytest.approx(80.0)
    assert _find("expense_date").value_fn(v) == "2025-05-10 09:00:00"
    assert _find("expense_value").value_fn(v) == pytest.approx(80.0)
    assert _find("expense_type").value_fn(v) == "Pedágio"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sensor.py -v
```

Expected: `KeyError: service_total` (and similar).

- [ ] **Step 3: Add helper properties to `VehicleData`** in `models.py`:

```python
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
```

- [ ] **Step 4: Add new sensor descriptions** in `sensors.py` (append inside `SENSOR_TYPES`):

```python
    DrivvoSensorEntityDescription(
        key="service_total",
        translation_key="service_total",
        name="Service Total",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.service_total,
    ),
    DrivvoSensorEntityDescription(
        key="service_value_total",
        translation_key="service_value_total",
        name="Service Value Total",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.service_value_total,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="service_date",
        translation_key="service_date",
        name="Service Date",
        icon="mdi:calendar",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_service.date if d.last_service else None,
    ),
    DrivvoSensorEntityDescription(
        key="service_odometer",
        translation_key="service_odometer",
        name="Service Odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda d: d.last_service.odometer if d.last_service else None,
    ),
    DrivvoSensorEntityDescription(
        key="service_value",
        translation_key="service_value",
        name="Service Value",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.last_service.total_value if d.last_service else None,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="service_description",
        translation_key="service_description",
        name="Service Description",
        icon="mdi:wrench",
        value_fn=lambda d: d.last_service.description if d.last_service else None,
    ),
    DrivvoSensorEntityDescription(
        key="expense_total",
        translation_key="expense_total",
        name="Expense Total",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.expense_total,
    ),
    DrivvoSensorEntityDescription(
        key="expense_value_total",
        translation_key="expense_value_total",
        name="Expense Value Total",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.expense_value_total,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="expense_date",
        translation_key="expense_date",
        name="Expense Date",
        icon="mdi:calendar",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_expense.date if d.last_expense else None,
    ),
    DrivvoSensorEntityDescription(
        key="expense_value",
        translation_key="expense_value",
        name="Expense Value",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        unit_fn=lambda d: d.currency,
        value_fn=lambda d: d.last_expense.total_value if d.last_expense else None,
        suggested_display_precision=2,
    ),
    DrivvoSensorEntityDescription(
        key="expense_type",
        translation_key="expense_type",
        name="Expense Type",
        icon="mdi:tag",
        value_fn=lambda d: d.last_expense.type if d.last_expense else None,
    ),
    DrivvoSensorEntityDescription(
        key="expense_description",
        translation_key="expense_description",
        name="Expense Description",
        icon="mdi:information-outline",
        value_fn=lambda d: d.last_expense.description if d.last_expense else None,
    ),
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_sensor.py tests/test_models.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add custom_components/drivvo/models.py custom_components/drivvo/sensors.py tests/test_sensor.py
git commit -m "feat(sensors): add service + expense sensor descriptions"
```

---

### Task 9: Add translations for new sensors (en + pt-BR)

**Files:**
- Modify: `custom_components/drivvo/translations/en.json`
- Modify: `custom_components/drivvo/translations/pt-BR.json`

- [ ] **Step 1: Read existing en.json** to find the sensor block where new keys go.

```bash
grep -n '"sensor"' custom_components/drivvo/translations/en.json
```

- [ ] **Step 2: Add the following keys inside `entity.sensor`** in en.json (mirror style of existing keys):

```json
"service_total":        {"name": "Service Total"},
"service_value_total":  {"name": "Service Value Total"},
"service_date":         {"name": "Service Date"},
"service_odometer":     {"name": "Service Odometer"},
"service_value":        {"name": "Service Value"},
"service_description":  {"name": "Service Description"},
"expense_total":        {"name": "Expense Total"},
"expense_value_total":  {"name": "Expense Value Total"},
"expense_date":         {"name": "Expense Date"},
"expense_value":        {"name": "Expense Value"},
"expense_type":         {"name": "Expense Type"},
"expense_description":  {"name": "Expense Description"}
```

- [ ] **Step 3: Add the same keys to `pt-BR.json` with translations**:

```json
"service_total":        {"name": "Total de Serviços"},
"service_value_total":  {"name": "Valor Total de Serviços"},
"service_date":         {"name": "Data do Serviço"},
"service_odometer":     {"name": "Odômetro do Serviço"},
"service_value":        {"name": "Valor do Serviço"},
"service_description":  {"name": "Descrição do Serviço"},
"expense_total":        {"name": "Total de Despesas"},
"expense_value_total":  {"name": "Valor Total de Despesas"},
"expense_date":         {"name": "Data da Despesa"},
"expense_value":        {"name": "Valor da Despesa"},
"expense_type":         {"name": "Tipo de Despesa"},
"expense_description":  {"name": "Descrição da Despesa"}
```

- [ ] **Step 4: Validate JSON**

```bash
python -c "import json; [json.load(open(f'custom_components/drivvo/translations/{f}')) for f in ['en.json','pt-BR.json']]"
```

Expected: no exception.

- [ ] **Step 5: Commit**

```bash
git add custom_components/drivvo/translations/
git commit -m "i18n: add strings for service + expense sensors (en, pt-BR)"
```

---

### Task 10: Update README with new sensors

**Files:** `README.md`

- [ ] **Step 1: Append under "Available Sensors":**

```markdown
### Service Sensors
- **Service Total**: Number of total service events
- **Service Value Total**: Total cost of all services
- **Service Date**: Date of last service
- **Service Odometer**: Odometer reading at last service
- **Service Value**: Cost of last service
- **Service Description**: Description of last service

### Expense Sensors
- **Expense Total**: Number of total expense events
- **Expense Value Total**: Total cost of all expenses
- **Expense Date**: Date of last expense
- **Expense Value**: Cost of last expense
- **Expense Type**: Type of last expense
- **Expense Description**: Description of last expense
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document service + expense sensors"
```

---

### Task 11: Self-check Phase B — no regression for existing users

- [ ] **Step 1: Diff sensor keys before vs after**

```bash
git diff master -- custom_components/drivvo/sensors.py | grep '^[+-].*key='
```

Confirm: only **additions** (`+`). No `-` lines for previously existing keys (entity IDs would change for users otherwise).

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all green.

---

## Phase C — HA Services (Write-back)

### Task 12: API client — POST methods (scaffolding only; behavior validated in Task 13)

**Files:**
- Modify: `custom_components/drivvo/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing test** — append to `tests/test_api.py`:

```python
@pytest.mark.asyncio
async def test_add_refuelling_posts_to_drivvo(mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
    )
    captured = {}

    def cb(url, **kwargs):
        captured["body"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        from aioresponses.core import CallbackResult
        return CallbackResult(status=201, payload={"id": 999})

    mock_aioresponse.post(
        "https://api.drivvo.com/veiculo/100/abastecimento",
        callback=cb,
    )

    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        await client.login()
        result = await client.add_refuelling(
            vehicle_id=100,
            date="2025-05-15 10:00:00",
            odometer=13000,
            volume=30.0,
            price=6.0,
            total_value=180.0,
            fuel_type="Gasolina",
            tank_full=True,
        )

    assert result == {"id": 999}
    assert captured["body"]["odometro"] == 13000
    assert captured["body"]["volume"] == 30.0
    assert captured["body"]["preco"] == 6.0
    assert captured["body"]["valor_total"] == 180.0
    assert captured["body"]["combustivel"] == "Gasolina"
    assert captured["body"]["tanque_cheio"] is True
    assert captured["headers"]["x-token"] == "fake-token-123"


@pytest.mark.asyncio
async def test_add_expense_posts(mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
    )
    mock_aioresponse.post(
        "https://api.drivvo.com/veiculo/100/despesa",
        payload={"id": 1}, status=201,
    )
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        await client.login()
        await client.add_expense(
            vehicle_id=100,
            date="2025-05-15 10:00:00",
            odometer=13000,
            total_value=50.0,
            description="Toll",
        )


@pytest.mark.asyncio
async def test_add_service_posts(mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
    )
    mock_aioresponse.post(
        "https://api.drivvo.com/veiculo/100/servico",
        payload={"id": 1}, status=201,
    )
    async with ClientSession() as session:
        client = DrivvoApiClient(session, "u", "p")
        await client.login()
        await client.add_service(
            vehicle_id=100,
            date="2025-05-15 10:00:00",
            odometer=13000,
            total_value=300.0,
            description="Oil change",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py -v -k "add_"
```

Expected: AttributeError on `add_refuelling`/`add_expense`/`add_service`.

- [ ] **Step 3: Add `_post_json` + the three methods** to `api.py`:

```python
    async def _post_json(self, path: str, payload: dict) -> Any:
        url = f"{BASE_URL}{path}"
        async with self._session.post(
            url, json=payload, headers=self._auth_headers()
        ) as resp:
            if resp.status in (401, 403):
                raise DrivvoAuthError(f"Token rejected for POST {path}")
            if resp.status >= 400:
                body = await resp.text()
                raise DrivvoApiError(
                    f"POST {path} failed: HTTP {resp.status}: {body[:200]}"
                )
            try:
                return await resp.json()
            except aiohttp.ContentTypeError:
                return {}

    async def add_refuelling(
        self,
        *,
        vehicle_id: int,
        date: str,
        odometer: int,
        volume: float,
        price: float,
        total_value: float,
        fuel_type: str,
        tank_full: bool = True,
        station: str | None = None,
        reason: int = 1,
    ) -> dict:
        payload = {
            "data": date,
            "odometro": odometer,
            "volume": volume,
            "preco": price,
            "valor_total": total_value,
            "combustivel": fuel_type,
            "tipo_motivo": reason,
            "tanque_cheio": tank_full,
        }
        if station:
            payload["posto_combustivel"] = {"nome": station}
        return await self._post_json(
            f"/veiculo/{vehicle_id}/abastecimento", payload
        )

    async def add_expense(
        self,
        *,
        vehicle_id: int,
        date: str,
        odometer: int,
        total_value: float,
        description: str | None = None,
        expense_type: str | None = None,
    ) -> dict:
        payload = {
            "data": date,
            "odometro": odometer,
            "valor_total": total_value,
        }
        if description:
            payload["descricao"] = description
        if expense_type:
            payload["tipo_despesa"] = expense_type
        return await self._post_json(
            f"/veiculo/{vehicle_id}/despesa", payload
        )

    async def add_service(
        self,
        *,
        vehicle_id: int,
        date: str,
        odometer: int,
        total_value: float,
        description: str | None = None,
    ) -> dict:
        payload = {
            "data": date,
            "odometro": odometer,
            "valor_total": total_value,
        }
        if description:
            payload["descricao"] = description
        return await self._post_json(
            f"/veiculo/{vehicle_id}/servico", payload
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api.py -v -k "add_"
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/drivvo/api.py tests/test_api.py
git commit -m "feat(api): add POST methods for refuelling/expense/service"
```

---

### Task 13: Validate POST endpoints against the live Drivvo web app

> The endpoints `/veiculo/{id}/abastecimento`, `/despesa`, `/servico` (POST) are inferred from REST convention. They MUST be validated before users can rely on the new HA services. This is a manual verification step — do it before merging Phase C.

- [ ] **Step 1: Open https://web.drivvo.com in a Chromium browser with DevTools → Network.**

- [ ] **Step 2: Create one refuelling, one service, one expense entry via the web UI.**

- [ ] **Step 3: For each captured request, confirm:**

| Action | Expected method | Expected path | Field names |
|--------|----------------|---------------|-------------|
| Add refuelling | POST | `/veiculo/{id}/abastecimento` (or `/abastecimento/web`) | as in Task 12 |
| Add service | POST | `/veiculo/{id}/servico` | as in Task 12 |
| Add expense | POST | `/veiculo/{id}/despesa` | as in Task 12 |

- [ ] **Step 4: If paths or field names differ, update `api.py` accordingly** and re-run `pytest tests/test_api.py -v`. Update the captured-body assertions in the tests to match the real schema.

- [ ] **Step 5: Commit any corrections**

```bash
git add custom_components/drivvo/api.py tests/test_api.py
git commit -m "fix(api): align POST endpoints/schema with Drivvo web app"
```

---

### Task 14: Register HA services

**Files:**
- Create: `custom_components/drivvo/services.py`
- Create: `custom_components/drivvo/services.yaml`
- Modify: `custom_components/drivvo/__init__.py`
- Test: `tests/test_services.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_services.py`:

```python
"""Tests for Drivvo HA services."""
import pytest
from unittest.mock import AsyncMock

from custom_components.drivvo.services import (
    async_register_services,
    SERVICE_ADD_REFUELLING,
)
from custom_components.drivvo.const import DOMAIN
from custom_components.drivvo.api import DrivvoApiClient


@pytest.mark.asyncio
async def test_add_refuelling_service_calls_client(hass):
    client = AsyncMock(spec=DrivvoApiClient)
    coord = AsyncMock()
    hass.data[DOMAIN] = {
        "entry_id_1": {"client": client, "coordinators": {100: coord}},
    }

    await async_register_services(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_REFUELLING,
        {
            "vehicle_id": 100,
            "date": "2025-05-15 10:00:00",
            "odometer": 13000,
            "volume": 30.0,
            "price": 6.0,
            "total_value": 180.0,
            "fuel_type": "Gasolina",
            "tank_full": True,
        },
        blocking=True,
    )

    client.add_refuelling.assert_awaited_once()
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_refuelling_raises_on_unknown_vehicle(hass):
    client = AsyncMock(spec=DrivvoApiClient)
    hass.data[DOMAIN] = {
        "entry_id_1": {"client": client, "coordinators": {}},
    }
    await async_register_services(hass)

    with pytest.raises(Exception, match="no coordinator"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ADD_REFUELLING,
            {
                "vehicle_id": 999,
                "date": "2025-05-15 10:00:00",
                "odometer": 13000,
                "volume": 30.0, "price": 6.0, "total_value": 180.0,
                "fuel_type": "Gasolina", "tank_full": True,
            },
            blocking=True,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_services.py -v
```

Expected: ImportError on services module.

- [ ] **Step 3: Implement `services.py`**

```python
"""Home Assistant services exposed by the Drivvo integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_ADD_REFUELLING = "add_refuelling"
SERVICE_ADD_SERVICE = "add_service"
SERVICE_ADD_EXPENSE = "add_expense"

REFUELLING_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): vol.Coerce(int),
        vol.Required("date"): cv.string,
        vol.Required("odometer"): vol.Coerce(int),
        vol.Required("volume"): vol.Coerce(float),
        vol.Required("price"): vol.Coerce(float),
        vol.Required("total_value"): vol.Coerce(float),
        vol.Required("fuel_type"): cv.string,
        vol.Optional("tank_full", default=True): cv.boolean,
        vol.Optional("station"): cv.string,
        vol.Optional("reason", default=1): vol.Coerce(int),
    }
)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): vol.Coerce(int),
        vol.Required("date"): cv.string,
        vol.Required("odometer"): vol.Coerce(int),
        vol.Required("total_value"): vol.Coerce(float),
        vol.Optional("description"): cv.string,
    }
)

EXPENSE_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): vol.Coerce(int),
        vol.Required("date"): cv.string,
        vol.Required("odometer"): vol.Coerce(int),
        vol.Required("total_value"): vol.Coerce(float),
        vol.Optional("description"): cv.string,
        vol.Optional("expense_type"): cv.string,
    }
)


def _resolve(hass: HomeAssistant, vehicle_id: int):
    for entry_id, store in hass.data.get(DOMAIN, {}).items():
        coord = store.get("coordinators", {}).get(vehicle_id)
        if coord is not None:
            return store["client"], coord
    raise HomeAssistantError(
        f"no coordinator found for vehicle_id={vehicle_id}; "
        "vehicle not configured in any Drivvo entry"
    )


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ADD_REFUELLING):
        return

    async def handle_add_refuelling(call: ServiceCall) -> None:
        client, coord = _resolve(hass, call.data["vehicle_id"])
        await client.add_refuelling(
            vehicle_id=call.data["vehicle_id"],
            date=call.data["date"],
            odometer=call.data["odometer"],
            volume=call.data["volume"],
            price=call.data["price"],
            total_value=call.data["total_value"],
            fuel_type=call.data["fuel_type"],
            tank_full=call.data["tank_full"],
            station=call.data.get("station"),
            reason=call.data["reason"],
        )
        await coord.async_request_refresh()

    async def handle_add_service(call: ServiceCall) -> None:
        client, coord = _resolve(hass, call.data["vehicle_id"])
        await client.add_service(
            vehicle_id=call.data["vehicle_id"],
            date=call.data["date"],
            odometer=call.data["odometer"],
            total_value=call.data["total_value"],
            description=call.data.get("description"),
        )
        await coord.async_request_refresh()

    async def handle_add_expense(call: ServiceCall) -> None:
        client, coord = _resolve(hass, call.data["vehicle_id"])
        await client.add_expense(
            vehicle_id=call.data["vehicle_id"],
            date=call.data["date"],
            odometer=call.data["odometer"],
            total_value=call.data["total_value"],
            description=call.data.get("description"),
            expense_type=call.data.get("expense_type"),
        )
        await coord.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_REFUELLING, handle_add_refuelling, schema=REFUELLING_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_SERVICE, handle_add_service, schema=SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_EXPENSE, handle_add_expense, schema=EXPENSE_SCHEMA
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister services when the last config entry unloads."""
    for name in (SERVICE_ADD_REFUELLING, SERVICE_ADD_SERVICE, SERVICE_ADD_EXPENSE):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
```

- [ ] **Step 4: Wire services into `__init__.py`**:

At the bottom of `async_setup_entry`, after `async_forward_entry_setups`:

```python
from .services import async_register_services
await async_register_services(hass)
```

In `async_unload_entry`, after the pop:

```python
if not hass.data.get(DOMAIN):
    from .services import async_unregister_services
    await async_unregister_services(hass)
```

- [ ] **Step 5: Create `services.yaml`**:

```yaml
add_refuelling:
  name: Add refuelling
  description: Add a refuelling entry to Drivvo for the given vehicle.
  fields:
    vehicle_id: {required: true, example: 12345, selector: {number: {mode: box}}}
    date: {required: true, example: "2025-05-15 10:00:00", selector: {text: {}}}
    odometer: {required: true, example: 13000, selector: {number: {mode: box, unit_of_measurement: km}}}
    volume: {required: true, example: 30.0, selector: {number: {mode: box, step: 0.01}}}
    price: {required: true, example: 6.0, selector: {number: {mode: box, step: 0.01}}}
    total_value: {required: true, example: 180.0, selector: {number: {mode: box, step: 0.01}}}
    fuel_type: {required: true, example: "Gasolina", selector: {text: {}}}
    tank_full: {required: false, default: true, selector: {boolean: {}}}
    station: {required: false, example: "Shell", selector: {text: {}}}
    reason: {required: false, default: 1, selector: {number: {mode: box}}}

add_service:
  name: Add service
  description: Add a service entry to Drivvo for the given vehicle.
  fields:
    vehicle_id: {required: true, selector: {number: {mode: box}}}
    date: {required: true, selector: {text: {}}}
    odometer: {required: true, selector: {number: {mode: box}}}
    total_value: {required: true, selector: {number: {mode: box, step: 0.01}}}
    description: {required: false, selector: {text: {}}}

add_expense:
  name: Add expense
  description: Add an expense entry to Drivvo for the given vehicle.
  fields:
    vehicle_id: {required: true, selector: {number: {mode: box}}}
    date: {required: true, selector: {text: {}}}
    odometer: {required: true, selector: {number: {mode: box}}}
    total_value: {required: true, selector: {number: {mode: box, step: 0.01}}}
    description: {required: false, selector: {text: {}}}
    expense_type: {required: false, selector: {text: {}}}
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_services.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add custom_components/drivvo/services.py custom_components/drivvo/services.yaml custom_components/drivvo/__init__.py tests/test_services.py
git commit -m "feat(services): register drivvo.add_refuelling / add_service / add_expense"
```

---

### Task 15: Document HA services in README

**Files:** `README.md`

- [ ] **Step 1: Append new section after sensors:**

```markdown
## Services

The integration registers three Home Assistant services for automations that need to write data back to Drivvo.

### `drivvo.add_refuelling`
Add a fuelling entry. Required fields: `vehicle_id`, `date` (`YYYY-MM-DD HH:MM:SS`), `odometer`, `volume`, `price`, `total_value`, `fuel_type`. Optional: `tank_full` (default `true`), `station`, `reason`.

### `drivvo.add_service`
Add a service (maintenance) entry. Required: `vehicle_id`, `date`, `odometer`, `total_value`. Optional: `description`.

### `drivvo.add_expense`
Add an expense entry. Required: `vehicle_id`, `date`, `odometer`, `total_value`. Optional: `description`, `expense_type`.

Example automation: log an EV charging session as a refuelling whenever your charger reports finished.

```yaml
action:
  - service: drivvo.add_refuelling
    data:
      vehicle_id: 12345
      date: "{{ now().strftime('%Y-%m-%d %H:%M:%S') }}"
      odometer: "{{ states('sensor.car_odometer') | int }}"
      volume: "{{ states('sensor.evse_session_kwh') | float }}"
      price: 0.85
      total_value: "{{ (states('sensor.evse_session_kwh') | float) * 0.85 }}"
      fuel_type: "Eletricidade"
      tank_full: false
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document drivvo.add_refuelling / add_service / add_expense services"
```

---

## Phase D — Tests, Diagnostics, Polish

### Task 16: Config flow tests

**Files:**
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Drivvo config flow."""
import pytest
from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow

from custom_components.drivvo.const import DOMAIN
from tests.conftest import load


@pytest.mark.asyncio
async def test_user_flow_success(hass, mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        payload=load("login_ok.json"),
    )
    mock_aioresponse.get(
        "https://api.drivvo.com/veiculo/web",
        payload=load("vehicle_list.json"),
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": "user@example.com", "password": "secret"},
    )
    assert result["step_id"] == "vehicle"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"vehicles": ["100"]},
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["data"]["email"] == "user@example.com"
    assert result["data"]["vehicles"] == ["100"]


@pytest.mark.asyncio
async def test_user_flow_invalid_auth(hass, mock_aioresponse):
    mock_aioresponse.post(
        "https://api.drivvo.com/autenticacao/login",
        status=401,
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"email": "user@example.com", "password": "wrong"},
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {"password": "auth_error"}
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_config_flow.py -v
```

Fix any mismatches: schema may not coerce the vehicle id string vs int, or step_id name may differ. If failures point to real bugs in `config_flow.py`, fix them; if to test errors, fix the tests.

- [ ] **Step 3: Commit**

```bash
git add tests/test_config_flow.py
git commit -m "test(config_flow): cover happy + invalid-auth paths"
```

---

### Task 17: Diagnostics support

**Files:**
- Create: `custom_components/drivvo/diagnostics.py`

- [ ] **Step 1: Implement diagnostics**

```python
"""Diagnostics for the Drivvo integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "placa", "token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    vehicles: dict[str, Any] = {}
    for vid, coord in store.get("coordinators", {}).items():
        d = coord.data
        if d is None:
            continue
        vehicles[str(vid)] = {
            "id": d.id,
            "name": d.name,
            "manufacturer": d.manufacturer,
            "model": d.model,
            "distance_unit": d.distance_unit,
            "currency": d.currency,
            "refuelling_count": len(d.refuellings),
            "service_count": len(d.services),
            "expense_count": len(d.expenses),
            "odometer": d.odometer,
            "odometer_date": d.odometer_date,
        }
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "vehicles": vehicles,
    }
```

- [ ] **Step 2: Quick sanity test** — append to `tests/test_services.py` or create `tests/test_diagnostics.py`:

```python
"""Tests for diagnostics."""
import pytest
from unittest.mock import MagicMock

from custom_components.drivvo.diagnostics import async_get_config_entry_diagnostics
from custom_components.drivvo.const import DOMAIN, CONF_EMAIL, CONF_PASSWORD
from custom_components.drivvo.models import VehicleData


@pytest.mark.asyncio
async def test_diagnostics_redacts_secrets(hass):
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret", "vehicles": ["100"]}

    coord = MagicMock()
    coord.data = VehicleData(
        id=100, name="My Car", placa="ABC1234",
        manufacturer="VW", model="Gol",
        distance_unit="km", currency="R$",
    )
    hass.data[DOMAIN] = {"e1": {"client": None, "coordinators": {100: coord}}}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"][CONF_EMAIL] == "**REDACTED**"
    assert result["entry_data"][CONF_PASSWORD] == "**REDACTED**"
    assert result["vehicles"]["100"]["name"] == "My Car"
    assert result["vehicles"]["100"]["odometer"] is None  # no events
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add custom_components/drivvo/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add diagnostics endpoint with secret redaction"
```

---

### Task 18: Manifest bump + final polish

**Files:**
- Modify: `custom_components/drivvo/manifest.json`
- Modify: `README.md` (changelog or notes)

- [ ] **Step 1: Update `manifest.json`**

```json
{
  "domain": "drivvo",
  "name": "Drivvo",
  "codeowners": ["@hudsonbrendon", "@dougiteixeira"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/hudsonbrendon/HA-drivvo#readme",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/hudsonbrendon/HA-drivvo/issues",
  "requirements": [],
  "version": "3.0.0"
}
```

(Major bump because the integration internals were rewritten; user-facing surface for sensors is additive but service-callable schema is new.)

- [ ] **Step 2: Add a "What's new in 3.0.0" section** at the top of `README.md`:

```markdown
## What's new in 3.0.0
- Async API client with token caching (no more re-login on every poll)
- New service sensors: total + last service date / odometer / value / description
- New expense sensors: total + last expense date / value / type / description
- New Home Assistant services: `drivvo.add_refuelling`, `drivvo.add_service`, `drivvo.add_expense` for write-back from automations
- Diagnostics support (Settings → Devices → Drivvo → Download diagnostics)
- Test suite covering API client, coordinator, sensors, config flow, services
```

- [ ] **Step 3: Run full test suite + lint**

```bash
pytest tests/ -v
ruff check custom_components/drivvo/
```

Fix any lint issues with `ruff check --fix`.

- [ ] **Step 4: Commit**

```bash
git add custom_components/drivvo/manifest.json README.md
git commit -m "chore: bump to 3.0.0 + add release notes"
```

- [ ] **Step 5: Open PR**

```bash
git push -u origin feat/refactor-and-expand
gh pr create --title "Refactor: async API client + service/expense sensors + write-back HA services" --body "$(cat <<'EOF'
## Summary
- Extracted async `DrivvoApiClient` + `DrivvoDataUpdateCoordinator`, replacing sync `requests` calls
- Added service + expense sensors (data already fetched but previously discarded)
- Registered `drivvo.add_refuelling` / `add_service` / `add_expense` HA services (closes #33)
- Baseline test suite (pytest + aioresponses)
- Diagnostics endpoint

## Test plan
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] Manual: install on local HA, reauth works, refuelling sensors match previous values
- [ ] Manual: new service/expense sensors populate for a vehicle with maintenance + toll history
- [ ] Manual: `drivvo.add_refuelling` from Developer Tools posts successfully and triggers a refresh

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review (run after completing all tasks)

**Spec coverage check:**
- [x] Refactor API client + aiohttp + token cache → Tasks 2–7
- [x] Service + expense sensors → Tasks 8–11
- [x] HA write services → Tasks 12–15 (with live verification step in Task 13)
- [x] Tests + diagnostics + quality → Tasks 16–18 (plus tests landing throughout)

**Placeholder scan:** All steps include the actual code, exact paths, and exact commands. No "implement appropriate X" or "similar to previous task".

**Type consistency:** `VehicleData` is defined in Task 1, extended in Tasks 6 + 8. Method names are stable (`refuelling_total`, `service_total`, etc.). `DrivvoApiClient` method signatures are introduced in Task 2 (`login`), Task 3 (`get_vehicles`, `get_vehicle`), Task 12 (`add_refuelling`, `add_service`, `add_expense`) and consumed identically in `services.py` (Task 14).

**Risks called out:**
- POST endpoints (Task 12) inferred — Task 13 verifies before launch.
- Sensor key changes would break user entity IDs — Task 11 has a guard diff.
- Major version bump (3.0.0) signals the internal rewrite; sensor surface is additive only.
