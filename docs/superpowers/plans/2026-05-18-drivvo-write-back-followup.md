# Drivvo Write-Back — Follow-up Plan (v3.1)

> Generated 2026-05-18 from live DevTools capture against web.drivvo.com.

## Why this is a follow-up

The v3.0.0 PR (#82) originally inferred POST endpoints from REST convention. Live verification proved the inferred schemas wrong. This doc captures the real schemas so a v3.1 follow-up can ship a working write-back feature.

## Real endpoints

| Op | Method | URL | Notes |
|----|--------|-----|-------|
| Add refuelling | POST | `https://api.drivvo.com/abastecimento` | No `/veiculo/{id}` prefix |
| Add expense | POST | `https://api.drivvo.com/despesa` | Same |
| Add service | POST | `https://api.drivvo.com/servico` | Same |
| Delete refuelling | DELETE | `https://api.drivvo.com/abastecimento/{id}` | |
| Delete expense | DELETE | `https://api.drivvo.com/despesa/{id}` | |
| Delete service | DELETE | `https://api.drivvo.com/servico/{id}` | |

## Required headers

```
x-token: <token>
app-platform: Web
app-version: 3
content-type: application/json
```

## Real request bodies (verified live)

### POST /abastecimento

```json
{
  "id_unico": "<uuid-v4>",
  "id_veiculo": 4611323,
  "odometro": 99999,
  "data": "2026-05-18 00:03:07",
  "id_combustivel": 19584520,
  "preco": 5,
  "valor_total": 50,
  "volume": 10.1,
  "sem_custo": false,
  "tanque_cheio": true,
  "preco_dois": 0,
  "valor_total_dois": 0,
  "volume_dois": 0,
  "preco_tres": 0,
  "valor_total_tres": 0,
  "volume_tres": 0,
  "esqueceu_anterior": false,
  "id_posto_combustivel": null,
  "id_tipo_motivo": null,
  "ids_arquivos": [],
  "id_forma_pagamento": null,
  "id_motorista": null,
  "observacao": ""
}
```

### POST /despesa

```json
{
  "id_unico": "<uuid-v4>",
  "id_veiculo": 4611323,
  "tipos_despesa": [
    {
      "id_tipo_despesa": 25201432,
      "id_unico": "<uuid-v4>",
      "valor": 7.5
    }
  ],
  "id_local": null,
  "ids_arquivos": [],
  "id_tipo_motivo": null,
  "odometro": 100000,
  "data": "2026-05-18 00:04:02",
  "observacao": "",
  "id_forma_pagamento": null,
  "id_motorista": null
}
```

### POST /servico

```json
{
  "id_unico": "<uuid-v4>",
  "id_veiculo": 4611323,
  "tipos_servico": [
    {
      "id_tipo_servico": 99302762,
      "id_unico": "<uuid-v4>",
      "valor": 15
    }
  ],
  "id_local": 2099099,
  "ids_arquivos": [],
  "odometro": 100001,
  "data": "2026-05-18 00:05:32",
  "observacao": "",
  "id_forma_pagamento": null,
  "id_motorista": null
}
```

**`id_local` is REQUIRED on service** (web UI enforces it). Nullable on expense.

## Lookup tables (needed to populate FKs)

| FK field | GET endpoint | Used by |
|----------|--------------|---------|
| `id_combustivel` | `/combustivel` | refuelling |
| `id_posto_combustivel` | `/postoCombustivel` | refuelling |
| `id_tipo_motivo` | `/tipoMotivo` | refuelling, expense |
| `id_tipo_despesa` | `/tipoDespesa` | expense |
| `id_tipo_servico` | `/tipoServico` | service |
| `id_local` | `/local` | service (req), expense |
| `id_motorista` | `/colaborador` | all |
| `id_forma_pagamento` | `/formaPagamento` | all |

## Why this can't ship in v3.0.0

The naive HA service interface (user passes a `fuel_type` string and we POST it) doesn't map onto Drivvo's FK model. A real implementation needs:

1. **Bootstrap caching** of all lookup tables (fuel types, expense types, service types, etc.) — fetch once per coordinator refresh, cache in `hass.data`.
2. **HA service interface redesign**: either
   - Accept FK IDs directly (user looks them up via a separate `drivvo.list_fuel_types` service), OR
   - Accept human-readable names and resolve internally (`fuel_type: "Gasolina"` → match in cached list → use ID), OR
   - Expose lookup tables as HA entities (`select` entity per type)
3. **UUID generation** for `id_unico` (server-side or client-side? — empirically client-generated UUIDs are accepted)
4. **Array form for expense/service** — `tipos_despesa[]` allows one record with multiple typed line items
5. **`id_local` is required on service** — service interface MUST either accept `id_local` or default to the user's only known location

## v3.1 implementation sketch

### `api.py` additions

```python
async def get_fuel_types(self) -> list[dict]:
    return await self._get_json("/combustivel")

async def get_expense_types(self) -> list[dict]:
    return await self._get_json("/tipoDespesa")

async def get_service_types(self) -> list[dict]:
    return await self._get_json("/tipoServico")

async def get_locations(self) -> list[dict]:
    return await self._get_json("/local")

async def get_gas_stations(self) -> list[dict]:
    return await self._get_json("/postoCombustivel")
```

### Fix existing add_* methods

- Drop the `/veiculo/{id}` URL prefix
- Move `vehicle_id` from URL → body as `id_veiculo`
- Add `id_unico = str(uuid.uuid4())` generation
- Accept FK IDs (`id_combustivel`) not strings (`fuel_type`)
- Pad the bi-fuel/tri-fuel zeros
- For expense/service: build `tipos_despesa`/`tipos_servico` arrays

### Coordinator changes

Add a second update path that caches lookup tables (refresh weekly, not daily — these change rarely).

### HA service redesign

Two services per category:
- `drivvo.list_fuel_types` — returns JSON for dashboards/scripts
- `drivvo.add_refuelling` — accepts `id_combustivel: int` (resolved by user from list)

Or single service with name-based resolution:
- `drivvo.add_refuelling` with `fuel_type_name: "Gasolina"` — looks up id internally, errors if name not found

Name-based is friendlier but fails on locale ambiguity. ID-based is precise.

## Verified test IDs (for this account — useful when writing the v3.1 tests)

- `id_veiculo: 4611323` (Nissan March)
- `id_combustivel: 19584520` (Gas. Aditivada — account's default)
- `id_tipo_despesa: 25201432` (Pedágio)
- `id_tipo_servico: 99302762` (Luzes)
- `id_local: 2099099` (Ari Auto Peças)

These IDs are account-specific; don't hardcode in production. Use them as fixtures only.
