import json
import uuid
from datetime import UTC, datetime

from ercot_forecast.eia.client import EIARegionPage
from ercot_forecast.storage.raw import save_raw_page


def test_saves_raw_page_without_api_key(tmp_path):
    run_id = uuid.uuid4()
    started_at = datetime(2026, 10, 8, 12, tzinfo=UTC)

    page = EIARegionPage(
        rows=[],
        total=0,
        offset=0,
        parameters={
            "frequency": "hourly",
            "offset": 0,
            "length": 5000,
        },
        payload={"response": {"total": 0, "data": []}},
    )

    path = save_raw_page(
        root=tmp_path,
        run_id=run_id,
        run_started_at=started_at,
        page_number=1,
        page=page,
    )

    assert path.name == "page-0001.json"
    assert "2026/10/08" in str(path)

    saved = json.loads(path.read_text())

    assert saved["run_id"] == str(run_id)
    assert "api_key" not in saved["parameters"]
    assert saved["payload"] == page.payload