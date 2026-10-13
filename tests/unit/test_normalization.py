import uuid
from decimal import Decimal

from ercot_forecast.pipelines.region_data import normalize_region_record


def make_row(period: str, value: str = "82104"):
    return {
        "period": period,
        "respondent": "ERCO",
        "respondent-name": "ERCOT",
        "type": "D",
        "type-name": "Demand",
        "value": value,
        "value-units": "megawatthours",
    }


def test_converts_value_to_decimal():
    record = normalize_region_record(
        make_row("2026-07-01T00", "82104.5"),
        uuid.uuid4(),
    )

    assert record["value"] == Decimal("82104.5")


def test_converts_utc_to_texas_time():
    record = normalize_region_record(
        make_row("2026-07-01T00"),
        uuid.uuid4(),
    )

    # Midnight UTC is 7 PM on the prior day during CDT.
    assert record["period_local"].isoformat() == "2026-06-30T19:00:00"


def test_fall_dst_hours_keep_distinct_utc_keys():
    run_id = uuid.uuid4()

    first = normalize_region_record(
        make_row("2026-11-01T06"),
        run_id,
    )
    second = normalize_region_record(
        make_row("2026-11-01T07"),
        run_id,
    )

    assert first["period_utc"] != second["period_utc"]
    assert first["period_local"] == second["period_local"]