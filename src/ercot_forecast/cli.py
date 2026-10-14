from datetime import UTC, datetime, timedelta

import typer

from ercot_forecast.pipelines.region_data import run_region_data_pipeline

app = typer.Typer(
    help="Ingest ERCOT demand data from the EIA API."
)

EIA_PERIOD_FORMAT = "%Y-%m-%dT%H"


def validate_period(value: str) -> datetime:
    try:
        return datetime.strptime(value, EIA_PERIOD_FORMAT)
    except ValueError as error:
        raise typer.BadParameter(
            "Expected format YYYY-MM-DDTHH"
        ) from error


@app.command()
def backfill(
    start: str = typer.Option(..., help="Start in YYYY-MM-DDTHH format"),
    end: str = typer.Option(..., help="End in YYYY-MM-DDTHH format"),
) -> None:
    start_value = validate_period(start)
    end_value = validate_period(end)

    if start_value >= end_value:
        raise typer.BadParameter("start must be earlier than end")

    try:
        run_id = run_region_data_pipeline(start=start, end=end)
    except Exception as error:
        typer.echo(f"Backfill failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Backfill succeeded: run_id={run_id}")


@app.command()
def incremental(
    lookback_hours: int = typer.Option(
        6,
        min=1,
        help="Number of prior hours to reload",
    ),
    lookahead_hours: int = typer.Option(
        36,
        min=1,
        help="Number of forecast hours to load",
    ),
) -> None:
    current_hour = datetime.now(UTC).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    start = current_hour - timedelta(hours=lookback_hours)
    end = current_hour + timedelta(hours=lookahead_hours)

    try:
        run_id = run_region_data_pipeline(
            start=start.strftime(EIA_PERIOD_FORMAT),
            end=end.strftime(EIA_PERIOD_FORMAT),
        )
    except Exception as error:
        typer.echo(f"Incremental run failed: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Incremental run succeeded: run_id={run_id}")


if __name__ == "__main__":
    app()