import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from pathlib import Path

from ercot_forecast.config import settings
from ercot_forecast.db.engine import SessionFactory
from ercot_forecast.db.repository import (
    create_ingestion_run,
    insert_region_records,
    mark_run_failed,
    mark_run_succeeded,
)
from ercot_forecast.eia.client import EIAClient
from ercot_forecast.storage.raw import (
    build_run_directory,
    save_raw_page,
)

TEXAS_TIMEZONE = ZoneInfo("America/Chicago")


class NormalizationError(ValueError):
    pass


def normalize_region_record(
    row: dict[str, Any],
    run_id: uuid.UUID,
) -> dict[str, Any]:
    try:
        period_utc = datetime.strptime(
            row["period"],
            "%Y-%m-%dT%H",
        ).replace(tzinfo=UTC)

        period_local_aware = period_utc.astimezone(TEXAS_TIMEZONE)

        # The database column is DateTime(timezone=False).
        period_local = period_local_aware.replace(tzinfo=None)

        value = Decimal(row["value"])

        return {
            "run_id": run_id,
            "period_utc": period_utc,
            "period_local": period_local,
            "respondent": row["respondent"],
            "respondent_name": row["respondent-name"],
            "data_type": row["type"],
            "type_name": row["type-name"],
            "value": value,
            "value_units": row["value-units"],
        }
    except KeyError as error:
        raise NormalizationError(
            f"Missing EIA field: {error.args[0]}"
        ) from error
    except (TypeError, ValueError, InvalidOperation) as error:
        raise NormalizationError(
            "EIA record contains an invalid period or value"
        ) from error


def normalize_region_records(
    rows: list[dict[str, Any]],
    run_id: uuid.UUID,
) -> list[dict[str, Any]]:
    return [
        normalize_region_record(row, run_id)
        for row in rows
    ]


def run_region_data_pipeline(
    *,
    start: str,
    end: str,
    raw_root: Path | None = None,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    started_at = datetime.now(UTC)
    raw_root = raw_root or settings.raw_data_path

    page_count = 0
    row_count = 0
    expected_total: int | None = None

    run_directory = build_run_directory(
        root=raw_root,
        run_id=run_id,
        run_started_at=started_at,
    )

    with EIAClient(
        api_key=settings.eia_api_key.get_secret_value(),
        page_size=settings.eia_page_size,
        timeout_seconds=settings.eia_timeout_seconds,
    ) as client:
        run_parameters = client.build_region_data_parameters(
            start=start,
            end=end,
            offset=0,
        )

        create_ingestion_run(
            run_id=run_id,
            endpoint="electricity/rto/region-data",
            frequency="hourly",
            parameters=run_parameters,
            started_at=started_at,
            raw_path=str(run_directory),
        )

        try:
            # All database inserts occur in one transaction.
            with SessionFactory.begin() as session:
                for page_count, page in enumerate(
                    client.iter_region_data(start=start, end=end),
                    start=1,
                ):
                    if expected_total is None:
                        expected_total = page.total
                    elif page.total != expected_total:
                        raise RuntimeError(
                            "EIA total changed during pagination"
                        )

                    save_raw_page(
                        root=raw_root,
                        run_id=run_id,
                        run_started_at=started_at,
                        page_number=page_count,
                        page=page,
                    )

                    records = normalize_region_records(
                        page.rows,
                        run_id,
                    )

                    insert_region_records(session, records)
                    row_count += len(records)

                if expected_total is not None and row_count != expected_total:
                    raise RuntimeError(
                        f"Expected {expected_total} rows but received "
                        f"{row_count}"
                    )

            # The insertion transaction has committed successfully.
            mark_run_succeeded(
                run_id=run_id,
                page_count=page_count,
                row_count=row_count,
            )

            return run_id

        except Exception as error:
            # Database inserts roll back, but JSON files remain.
            mark_run_failed(
                run_id=run_id,
                page_count=page_count,
                row_count=row_count,
                error_message=f"{type(error).__name__}: {error}",
            )
            raise