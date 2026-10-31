"""Unit tests for the pure Drivvo calculations.

`calc` has no Home Assistant imports on purpose, so the maths can be exercised
directly.
"""

import datetime

from custom_components.drivvo import calc, const

TZ = datetime.timezone(datetime.timedelta(hours=-3))  # the account timezone


def _parse(value):
    """Stand-in for the Home Assistant aware parser."""
    if not value:
        return None
    return datetime.datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=TZ
    )


def test_refuelling_volume_derived_from_price():
    # Real record from the API: volume is null, only price and total are stored.
    assert (
        round(
            calc.refuelling_volume({"volume": None, "preco": 5.79, "valor_total": 100}),
            3,
        )
        == 17.271
    )
    # A cost free refuelling reports its volume directly.
    assert (
        calc.refuelling_volume(
            {"volume": 12, "preco": 0, "valor_total": 0, "sem_custo": True}
        )
        == 12
    )
    # Neither price nor sem_custo: fall back to the informed volume.
    assert calc.refuelling_volume({"volume": 40, "preco": 0, "valor_total": 0}) == 40


def test_fuel_segments_only_span_full_tanks():
    history = [
        {"odometro": 1000, "tanque_cheio": True, "volume": 30, "sem_custo": True},
        {"odometro": 1200, "tanque_cheio": False, "volume": 10, "sem_custo": True},
        {"odometro": 1500, "tanque_cheio": True, "volume": 25, "sem_custo": True},
        {"odometro": 1800, "tanque_cheio": True, "volume": 40, "sem_custo": True},
    ]
    segments = calc.fuel_segments(history)
    # The 30 L of the opening fill are burnt before the measurement starts.
    assert [(distance, volume) for distance, volume, _cost in segments] == [
        (500, 35),
        (300, 40),
    ]


def test_fuel_segments_ignore_partial_leading_fills():
    history = [
        {"odometro": 900, "tanque_cheio": False, "volume": 20, "sem_custo": True},
        {"odometro": 1000, "tanque_cheio": True, "volume": 30, "sem_custo": True},
        {"odometro": 1400, "tanque_cheio": True, "volume": 32, "sem_custo": True},
    ]
    assert calc.fuel_segments(history) == [(400, 32, 0)]


def test_forgotten_refuelling_breaks_the_chain():
    history = [
        {"odometro": 1000, "tanque_cheio": True, "volume": 30, "sem_custo": True},
        {
            "odometro": 1400,
            "tanque_cheio": True,
            "volume": 32,
            "sem_custo": True,
            "esqueceu_anterior": True,
        },
        {"odometro": 1800, "tanque_cheio": True, "volume": 35, "sem_custo": True},
    ]
    # Only the segment after the forgotten entry is trustworthy.
    assert calc.fuel_segments(history) == [(400, 35, 0)]


def test_efficiency_matches_each_account_unit():
    km_per_liter = calc.efficiency(
        500,
        35,
        const.DISTANCE_KILOMETERS,
        const.VOLUME_LITER,
        const.EFFICIENCY_KM_LITER,
    )
    assert round(km_per_liter, 4) == 14.2857

    liters_100km = calc.efficiency(
        500,
        35,
        const.DISTANCE_KILOMETERS,
        const.VOLUME_LITER,
        const.EFFICIENCY_LITER_100KM,
    )
    assert round(liters_100km, 4) == 7.0

    mpg = calc.efficiency(
        500,
        35,
        const.DISTANCE_KILOMETERS,
        const.VOLUME_LITER,
        const.EFFICIENCY_MILE_GALLON_US,
    )
    assert round(mpg, 2) == 33.60

    # A vehicle measured in hours reports volume per hour.
    per_hour = calc.efficiency(
        10, 25, const.DISTANCE_HOURS, const.VOLUME_LITER, const.EFFICIENCY_KM_LITER
    )
    assert per_hour == 2.5

    assert calc.efficiency(0, 35, 1, 1, 1) is None
    assert calc.efficiency(500, 0, 1, 1, 1) is None


def test_gallon_accounts_convert_before_dividing():
    # 10 US gallons over 300 mi is 30 mpg regardless of the stored unit.
    mpg = calc.efficiency(
        300,
        10,
        const.DISTANCE_MILES,
        const.VOLUME_GALLON_US,
        const.EFFICIENCY_MILE_GALLON_US,
    )
    assert round(mpg, 3) == 30.0


def test_add_months_clamps_to_end_of_month():
    assert calc.add_months(
        datetime.datetime(2024, 1, 31, tzinfo=TZ), 1
    ) == datetime.datetime(2024, 2, 29, tzinfo=TZ)
    assert calc.add_months(
        datetime.datetime(2023, 1, 31, tzinfo=TZ), 1
    ) == datetime.datetime(2023, 2, 28, tzinfo=TZ)
    assert calc.add_months(
        datetime.datetime(2024, 6, 15, tzinfo=TZ), 12
    ) == datetime.datetime(2025, 6, 15, tzinfo=TZ)


SERVICES = [
    {
        "id_veiculo": 1,
        "data": "2021-11-06 12:16:46",
        "odometro": 70200,
        "tipos_servico": [{"id_tipo_servico": 99302742, "valor": 137, "nome": "Óleo"}],
    }
]


def test_reminder_repeating_by_distance():
    reminders = [
        {
            "id_lembrete": 7,
            "id_tipo_servico": 99302742,
            "tipo_servico": "Óleo",
            "unico_repetir": 0,
            "repetir_distancia": 10000,
        }
    ]
    result = calc.reminder_predictions(
        reminders,
        [],
        SERVICES,
        current_odometer=77227,
        now=datetime.datetime(2026, 8, 29, tzinfo=TZ),
        parse_datetime=_parse,
    )
    assert len(result) == 1
    assert result[0]["odometer"] == 80200  # 70200 + 10000
    assert result[0]["distance_left"] == 2973
    assert result[0]["overdue"] is False


def test_reminder_overdue_by_distance():
    reminders = [
        {
            "id_lembrete": 7,
            "id_tipo_servico": 99302742,
            "tipo_servico": "Óleo",
            "unico_repetir": 0,
            "repetir_distancia": 5000,
        }
    ]
    result = calc.reminder_predictions(
        reminders,
        [],
        SERVICES,
        current_odometer=77227,
        now=datetime.datetime(2026, 8, 29, tzinfo=TZ),
        parse_datetime=_parse,
    )
    assert result[0]["odometer"] == 75200
    assert result[0]["distance_left"] == -2027
    assert result[0]["overdue"] is True


def test_reminder_repeating_by_time_uses_the_period():
    reminders = [
        {
            "id_lembrete": 8,
            "id_tipo_servico": 99302742,
            "tipo_servico": "Óleo",
            "unico_repetir": 0,
            "repetir_tempo": 6,
            "periodo": 2,  # months
        }
    ]
    result = calc.reminder_predictions(
        reminders,
        [],
        SERVICES,
        current_odometer=77227,
        now=datetime.datetime(2026, 8, 29, tzinfo=TZ),
        parse_datetime=_parse,
    )
    assert result[0]["date"] == datetime.datetime(2022, 5, 6, 12, 16, 46, tzinfo=TZ)
    assert result[0]["overdue"] is True  # long past


def test_one_off_reminder_uses_its_own_target():
    reminders = [
        {
            "id_lembrete": 9,
            "id_tipo_servico": 99302742,
            "tipo_servico": "Revisão",
            "unico_repetir": 1,
            "odometro": 90000,
            "data": "2026-12-01 00:00:00",
        }
    ]
    result = calc.reminder_predictions(
        reminders,
        [],
        SERVICES,
        current_odometer=77227,
        now=datetime.datetime(2026, 8, 29, tzinfo=TZ),
        parse_datetime=_parse,
    )
    assert result[0]["odometer"] == 90000
    assert result[0]["date"] == datetime.datetime(2026, 12, 1, tzinfo=TZ)
    assert result[0]["days_left"] == 94
    assert result[0]["overdue"] is False


def test_route_reminders_are_not_maintenance():
    reminders = [{"id_lembrete": 10, "id_percurso": 55}]
    assert (
        calc.reminder_predictions(
            reminders,
            [],
            [],
            current_odometer=1,
            now=datetime.datetime(2026, 8, 29, tzinfo=TZ),
            parse_datetime=_parse,
        )
        == []
    )


def test_reminders_sort_closest_first():
    far = {"days_left": 300, "distance_left": 9000, "description": "far"}
    near = {"days_left": 3, "distance_left": 9000, "description": "near"}
    assert min([far, near], key=calc.sort_key_reminder) is near


def test_typed_lines_are_summed_and_named():
    record = {
        "tipos_servico": [
            {"valor": 137, "nome": "Troca de Óleo"},
            {"valor": 31, "nome": "Luzes"},
        ]
    }
    assert calc.sum_typed_values(record, "tipos_servico") == 168
    assert calc.typed_names(record, "tipos_servico") == "Troca de Óleo, Luzes"
    assert calc.typed_names({}, "tipos_servico") is None


def test_sorted_desc_puts_newest_first():
    records = [{"data": "2021-01-01"}, {"data": "2023-05-05"}, {"data": None}]
    assert calc.sorted_desc(records)[0]["data"] == "2023-05-05"


def test_to_float_tolerates_api_noise():
    assert calc.to_float(None) is None
    assert calc.to_float("") is None
    assert calc.to_float("abc") is None
    assert calc.to_float("5.5") == 5.5
    assert calc.to_float(3) == 3.0
