import uuid
from datetime import UTC, datetime
from typing import Any, Sequence

from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from ercot_forecast.db.engine import SessionFactory
from ercot_forecast.db.models import EIARegionData, IngestionRun


def create_ingestion_run(
    *,
    run_id: uuid.UUID,
    endpoint: str,
    frequency: str,
    parameters: dict[str, Any],
    started_at: datetime,
    raw_path: str,
) -> None:
    run = IngestionRun(
        id=run_id,
        endpoint=endpoint,
        frequency=frequency,
        parameters=parameters,
        status="running",
        started_at=started_at,
        raw_path=raw_path,
    )

    # This transaction is committed before data loading starts.
    with SessionFactory.begin() as session:
        session.add(run)


def insert_region_records(
    session: Session,
    records: Sequence[dict[str, Any]],
) -> None:
    if not records:
        return

    session.execute(
        insert(EIARegionData),
        records,
    )


def mark_run_succeeded(
    *,
    run_id: uuid.UUID,
    page_count: int,
    row_count: int,
) -> None:
    with SessionFactory.begin() as session:
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status="succeeded",
                completed_at=datetime.now(UTC),
                page_count=page_count,
                row_count=row_count,
                error_message=None,
            )
        )


def mark_run_failed(
    *,
    run_id: uuid.UUID,
    error_message: str,
    page_count: int,
    row_count: int,
) -> None:
    with SessionFactory.begin() as session:
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status="failed",
                completed_at=datetime.now(UTC),
                page_count=page_count,
                row_count=row_count,
                error_message=error_message,
            )
        )