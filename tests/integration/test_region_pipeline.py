import responses
from sqlalchemy import delete, select

from ercot_forecast.db.engine import SessionFactory
from ercot_forecast.db.models import EIARegionData, IngestionRun
from ercot_forecast.eia.client import EIAClient
from ercot_forecast.pipelines.region_data import run_region_data_pipeline


@responses.activate
def test_complete_region_pipeline(tmp_path):
    responses.add(
        responses.GET,
        EIAClient.REGION_DATA_URL,
        json={
            "response": {
                "total": 2,
                "data": [
                    {
                        "period": "2026-10-01T00",
                        "respondent": "ERCO",
                        "respondent-name": "ERCOT",
                        "type": "D",
                        "type-name": "Demand",
                        "value": "50000",
                        "value-units": "megawatthours",
                    },
                    {
                        "period": "2026-10-01T00",
                        "respondent": "ERCO",
                        "respondent-name": "ERCOT",
                        "type": "DF",
                        "type-name": "Day-ahead demand forecast",
                        "value": "51000",
                        "value-units": "megawatthours",
                    },
                ],
            }
        },
        status=200,
    )

    run_id = None

    try:
        run_id = run_region_data_pipeline(
            start="2026-10-01T00",
            end="2026-10-01T01",
            raw_root=tmp_path,
        )

        with SessionFactory() as session:
            run = session.get(IngestionRun, run_id)

            rows = session.scalars(
                select(EIARegionData).where(
                    EIARegionData.run_id == run_id
                )
            ).all()

            assert run is not None
            assert run.status == "succeeded"
            assert run.row_count == 2
            assert len(rows) == 2

        raw_files = list(tmp_path.rglob("page-*.json"))
        assert len(raw_files) == 1

    finally:
        if run_id is not None:
            with SessionFactory.begin() as session:
                session.execute(
                    delete(IngestionRun).where(
                        IngestionRun.id == run_id
                    )
                )