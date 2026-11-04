# Changelog

## 3.1.2 - 2026-11-04

- Fix the options flow for Home Assistant's read-only config_entry property.
- Retry setup after transient login, vehicle-list and first-refresh failures.
- Report a missing vehicle only after a successful account vehicle-list response confirms its absence.
- Wrap aiohttp connection errors and show cannot_connect in user, reauthentication and options forms.
- Add regression coverage for transport errors, options opening, setup retry/recovery and confirmed missing vehicles.

## 3.1.1 - 2026-10-31

First maintained continuation of upstream 3.1.0.

- Correct stored fuel/energy classes for fuel_remaining, preserving IDs and measurement statistics.
- Repair test-only aiohttp mocking compatibility and optional endpoint fixtures.
- Add four fuel-class regression cases: 93 tests passing.
- Retain upstream MIT license and record recovery provenance.
- Update repository links and maintenance ownership; prepare custom HACS installation.

No live write-service validation or default HACS inclusion is claimed.
