import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ercot_forecast.eia.client import EIARegionPage


def build_run_directory(
    root: Path,
    run_id: uuid.UUID,
    run_started_at: datetime,
) -> Path:
    utc_date = run_started_at.astimezone(UTC)

    return (
        root
        / "eia"
        / "region-data"
        / f"{utc_date:%Y}"
        / f"{utc_date:%m}"
        / f"{utc_date:%d}"
        / str(run_id)
    )


def save_raw_page(
    *,
    root: Path,
    run_id: uuid.UUID,
    run_started_at: datetime,
    page_number: int,
    page: EIARegionPage,
) -> Path:
    if "api_key" in page.parameters:
        raise ValueError("Raw metadata must not contain the API key")

    run_directory = build_run_directory(
        root=root,
        run_id=run_id,
        run_started_at=run_started_at,
    )
    run_directory.mkdir(parents=True, exist_ok=True)

    destination = run_directory / f"page-{page_number:04d}.json"

    if destination.exists():
        raise FileExistsError(f"Raw page already exists: {destination}")

    retrieved_at = datetime.now(UTC)

    wrapper = {
        "run_id": str(run_id),
        "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
        "endpoint": "electricity/rto/region-data",
        "parameters": page.parameters,
        "payload": page.payload,
    }

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=run_directory,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            json.dump(wrapper, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, destination)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return destination